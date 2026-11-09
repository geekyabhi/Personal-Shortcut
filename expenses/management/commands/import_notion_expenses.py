from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum

from expenses.data_layer import ExpensesDataLayer
from expenses.data_services.options import sync_from_expenses
from expenses.models import Expense
from users.models import User

# Notion's select options contain a typo; the service looks for "Quarterly".
FREQUENCY_FIXES = {"Quaterly": "Quarterly"}


def _text(prop: dict, key: str) -> str:
    return "".join(t.get("plain_text", "") for t in (prop or {}).get(key, [])).strip()


def _names(prop: dict) -> list:
    prop = prop or {}
    if prop.get("select"):
        return [prop["select"]["name"]]
    return [o["name"] for o in prop.get("multi_select", [])]


def _date_start(prop: dict) -> str:
    return ((prop or {}).get("date") or {}).get("start") or ""


def _parse_dt(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def row_to_fields(row: dict) -> dict:
    """Notion page -> Expense field values (everything except profile / mandate link)."""
    p = row.get("properties", {})

    title = ""
    for prop in p.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            title = _text(prop, "title")
            break

    start = _date_start(p.get("Date"))
    # `date` comes from the text, not the parsed datetime: converting to UTC
    # could shift a late-night expense onto the next day.
    day = start[:10] or None
    occurred_at = _parse_dt(start) if len(start) > 10 else None

    freq = (((p.get("Mandate Frequency") or {}).get("select")) or {}).get("name", "")

    return {
        "title": title[:500],
        "amount": Decimal(str(round((p.get("Amount") or {}).get("number") or 0, 2))),
        "date": day,
        "occurred_at": occurred_at,
        "occurred_offset_min": (
            int(occurred_at.utcoffset().total_seconds() // 60)
            if occurred_at and occurred_at.utcoffset() is not None else None
        ),
        "categories": [n[:100] for n in _names(p.get("Category"))],
        "sources": [n[:100] for n in _names(p.get("Source"))],
        "mode": (_names(p.get("Mode")) or [""])[0][:100],
        "comment": _text(p.get("Comment"), "rich_text"),
        "other_partner": _text(p.get("Other Partner"), "rich_text"),
        "add_to_split": bool((p.get("Add to Split") or {}).get("checkbox")),
        "from_split": bool((p.get("From Split") or {}).get("checkbox")),
        "split_added": bool((p.get("Split Added") or {}).get("checkbox")),
        "processed": bool((p.get("Processed") or {}).get("checkbox")),
        "splitwise_id": (
            int(p["Splitwise ID"]["number"])
            if (p.get("Splitwise ID") or {}).get("number") is not None else None
        ),
        "is_mandate": bool((p.get("Is Mandate") or {}).get("checkbox")),
        "mandate_frequency": FREQUENCY_FIXES.get(freq, freq),
        "mandate_start": _date_start(p.get("Mandate Start Date"))[:10] or None,
        "mandate_end": _date_start(p.get("Mandate End Date"))[:10] or None,
        "recurring": bool((p.get("Recurring") or {}).get("checkbox")),
    }


def _norm_id(value: str) -> str:
    return (value or "").replace("-", "").strip().lower()


class Command(BaseCommand):
    BATCH = 500  # rows per INSERT / UPDATE statement

    help = (
        "One-time, re-runnable copy of the Notion expenses database(s) into "
        "Postgres. Read-only toward Notion; rows are matched on notion_page_id "
        "so running it again updates rather than duplicates."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile", action="append",
            help="EXPENSE_PROFILES name to import (repeatable). Default: all.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Do the full import inside a transaction, report, then roll it back.",
        )

    def handle(self, *args, **opts):
        profiles = [p.upper() for p in (opts["profile"] or settings.EXPENSE_PROFILES)]
        failed = False
        for profile in profiles:
            try:
                failed |= not self._import_profile(profile, opts["dry_run"])
            except Exception as exc:
                raise CommandError(f"{profile}: {exc}") from exc
        if failed:
            raise CommandError("Verification found differences — see output above.")

    def _import_profile(self, profile: str, dry_run: bool) -> bool:
        dl = ExpensesDataLayer.from_env(profile)
        if not dl.is_configured:
            self.stdout.write(self.style.WARNING(f"{profile}: Notion not configured, skipped"))
            return True

        self.stdout.write(f"\n{profile}: fetching from Notion …")
        rows = dl.fetch_all_rows()
        parsed = [(r["id"], row_to_fields(r), _text(
            (r.get("properties", {}).get("Mandate ID") or {}), "rich_text")) for r in rows]
        # Mandate templates first so occurrences can link to them.
        parsed.sort(key=lambda t: not t[1]["is_mandate"])

        # Link rows to the person's account (matched on the profile's email)
        # when one exists; re-running after they sign up fills it in.
        email = next((e for e, p in settings.ALLOWED_USERS.items() if p == profile), "")
        user = User.objects.filter(email=email).first() if email else None
        if not user:
            self.stdout.write(self.style.WARNING(
                f"  note: no user account for {email or profile} yet — rows imported "
                f"without a user; re-run after signup to link them"))

        warnings = []
        created = updated = 0
        pk_by_notion = {}  # normalised Notion page id -> Postgres pk (so occurrences can link to mandates)
        now = timezone.now()

        # Columns a re-run refreshes on rows that already exist. ``user`` is only
        # touched when an account was found, so a re-run never un-links rows.
        field_names = list(parsed[0][1].keys()) if parsed else []
        update_fields = [f for f in field_names if f != "mandate_id"] + ["mandate", "profile", "updated_at"]
        if user:
            update_fields.append("user")

        with transaction.atomic():
            existing = dict(
                Expense.objects.filter(notion_page_id__in=[nid for nid, _, _ in parsed])
                .values_list("notion_page_id", "pk")
            )

            def save(rows_):
                """Insert/refresh ``rows_`` ((notion_id, fields) pairs) in batches —
                a few queries per ``BATCH`` rows instead of several per row, which
                matters a lot over a slow link to a hosted database."""
                nonlocal created, updated
                to_create, to_update = [], []
                for notion_id, fields in rows_:
                    obj = Expense(notion_page_id=notion_id, profile=profile, **fields)
                    if user:
                        obj.user = user
                    pk = existing.get(notion_id)
                    if pk:
                        obj.pk, obj.updated_at = pk, now  # bulk_update skips auto_now
                        to_update.append(obj)
                    else:
                        to_create.append(obj)
                Expense.objects.bulk_create(to_create, batch_size=self.BATCH)  # fills .pk on Postgres
                if to_update:
                    Expense.objects.bulk_update(to_update, update_fields, batch_size=self.BATCH)
                for obj in to_create + to_update:
                    pk_by_notion[_norm_id(obj.notion_page_id)] = obj.pk
                created += len(to_create)
                updated += len(to_update)

            # Templates first, so their pks exist when occurrences are built.
            save([(nid, {**f, "mandate_id": None}) for nid, f, _ in parsed if f["is_mandate"]])

            occurrences = []
            for notion_id, fields, mandate_ref in parsed:
                if fields["is_mandate"]:
                    continue
                target = None
                if mandate_ref:
                    target = pk_by_notion.get(_norm_id(mandate_ref))
                    if target is None:
                        warnings.append(f"'{fields['title']}' ({notion_id}): mandate {mandate_ref} not found, left unlinked")
                occurrences.append((notion_id, {**fields, "mandate_id": target}))
            save(occurrences)

            if user:
                sync_from_expenses(user.id)

            ok = self._verify(profile, rows, parsed)

            # Never keep a copy that doesn't match Notion.
            if dry_run or not ok:
                transaction.set_rollback(True)

        for w in warnings:
            self.stdout.write(self.style.WARNING(f"  warning: {w}"))
        freq_left = sorted({f["mandate_frequency"] for _, f, _ in parsed if f["mandate_frequency"]})
        unsupported = [f for f in freq_left if f not in ("Weekly", "Monthly", "Quarterly", "Yearly")]
        if unsupported:
            self.stdout.write(self.style.WARNING(
                f"  warning: mandate frequencies the service can't schedule: {unsupported}"))

        rolled_back = dry_run or not ok
        self.stdout.write(
            f"{profile}: {created} created, {updated} updated "
            f"({'rolled back — nothing was written' if rolled_back else 'committed'})"
        )
        return ok

    def _verify(self, profile: str, rows: list, parsed: list) -> bool:
        """Compare Notion-side numbers (from the parsed rows) with Postgres."""
        qs = Expense.objects.filter(profile=profile)
        expected = {
            "rows": len(rows),
            "mandates": sum(f["is_mandate"] for _, f, _ in parsed),
            "with splitwise id": sum(f["splitwise_id"] is not None for _, f, _ in parsed),
            # Straight from Notion's raw JSON, independent of row_to_fields.
            "spend total (non-mandate)": sum(
                (Decimal(str((r["properties"].get("Amount") or {}).get("number") or 0))
                 for r in rows
                 if not (r["properties"].get("Is Mandate") or {}).get("checkbox")),
                Decimal("0"),
            ).quantize(Decimal("0.01")),
        }
        actual = {
            "rows": qs.count(),
            "mandates": qs.filter(is_mandate=True).count(),
            "with splitwise id": qs.filter(splitwise_id__isnull=False).count(),
            "spend total (non-mandate)": qs.filter(is_mandate=False).aggregate(
                s=Sum("amount"))["s"] or Decimal("0"),
        }
        ok = True
        self.stdout.write(f"  {'check':28} {'notion':>14} {'postgres':>14}")
        for key, exp in expected.items():
            act = actual[key]
            match = exp == act
            ok &= match
            line = f"  {key:28} {exp!s:>14} {act!s:>14}  {'OK' if match else 'MISMATCH'}"
            self.stdout.write(line if match else self.style.ERROR(line))
        return ok
