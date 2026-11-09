from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone as dj_timezone

from ..models import Expense
from . import options


class ExpensesDataService:
    """Postgres-backed replacement for the Notion ``ExpensesDataLayer``.

    Scoped to one EXPENSE_PROFILES person, like the Notion layer was scoped to
    one database. Reads return plain dicts with the same keys as
    ``ExpensesService._row_to_entry`` (``page_id``, ``title``, ``amount``,
    ``date``, ``categories`` …) so the service can move over without touching
    its callers. ``page_id`` is the row's primary key as a string.

    No caching and no ``bust_cache``: queries hit Postgres directly, so a
    write is visible to the next read.
    """

    # Fields create/update accept — anything else passed in is ignored.
    WRITABLE_FIELDS = (
        "title", "amount", "date", "occurred_at", "categories", "sources", "mode",
        "comment", "other_partner", "add_to_split", "from_split", "split_added",
        "processed", "splitwise_id", "is_mandate", "mandate_frequency",
        "mandate_start", "mandate_end", "mandate_id", "recurring",
    )

    def __init__(self, profile: str = "", user_id=None):
        # Rows are scoped to ``user_id`` when there is one, else to the legacy
        # ``profile`` name (rows not yet linked to an account). With neither,
        # the service sees nothing. New rows are stamped with both.
        self.profile = profile
        self.user_id = user_id

    @classmethod
    def from_env(cls, profile: str = "", user_id=None) -> "ExpensesDataService":
        """Same constructor name as ``ExpensesDataLayer.from_env`` so callers
        can swap one for the other."""
        return cls(profile, user_id)

    @property
    def is_configured(self) -> bool:
        # No DATABASE_URL means Django has no database to talk to.
        return bool(settings.DATABASES)

    # ------------------------------------------------------------------ #
    #  Conversion                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def to_entry(e: Expense) -> dict:
        if e.occurred_at:
            tz = timezone(timedelta(minutes=e.occurred_offset_min or 0))
            dt_str = e.occurred_at.astimezone(tz).isoformat()
        else:
            dt_str = e.date.isoformat() if e.date else ""
        return {
            "page_id": str(e.pk),
            "title": e.title or "—",
            "amount": round(float(e.amount), 2),
            "date": e.date.isoformat() if e.date else "",
            "datetime": dt_str,
            "categories": list(e.categories),
            "source": e.sources[0] if e.sources else "",
            "sources": list(e.sources),
            "mode": e.mode,
            "comment": e.comment,
            "other_partner": e.other_partner,
            "add_to_split": e.add_to_split,
            "from_split": e.from_split,
            "split_added": e.split_added,
            "processed": e.processed,
            "splitwise_id": e.splitwise_id,
            "is_mandate": e.is_mandate,
            "mandate_frequency": e.mandate_frequency,
            "mandate_start": e.mandate_start.isoformat() if e.mandate_start else "",
            "mandate_end": e.mandate_end.isoformat() if e.mandate_end else "",
            "mandate_id": str(e.mandate_id) if e.mandate_id else "",
            "recurring": e.recurring,
        }

    def _qs(self):
        if self.user_id:
            return Expense.objects.filter(user_id=self.user_id)
        if self.profile:
            return Expense.objects.filter(profile=self.profile)
        return Expense.objects.none()

    def _clean(self, fields: dict) -> dict:
        # ``source`` (single string) is accepted as shorthand for ``sources``.
        if "source" in fields and "sources" not in fields:
            fields = {**fields, "sources": [fields["source"]] if fields["source"] else []}
        data = {k: v for k, v in fields.items() if k in self.WRITABLE_FIELDS}
        # ``date`` may arrive as a bare day or a full datetime string. Setting
        # a date replaces the time too (as Notion's Date did): a bare day
        # clears any stored time, a datetime string stores it. The day itself
        # is always the string's own first 10 chars (the entry's local day),
        # never the UTC-converted one.
        raw_date = data.get("date")
        if isinstance(raw_date, str) and raw_date.strip() and "occurred_at" not in data:
            data["occurred_at"] = raw_date.strip() if len(raw_date.strip()) > 10 else None
        # Callers (and the service) pass dates as ISO strings, "" for "none".
        for key in ("date", "mandate_start", "mandate_end"):
            if key in data:
                data[key] = self._parse_date(data[key])
        if "occurred_at" in data:
            dt = self._parse_datetime(data["occurred_at"])
            if dt and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            data["occurred_at"] = dt
            data["occurred_offset_min"] = int(dt.utcoffset().total_seconds() // 60) if dt else None
        if "amount" in data:
            data["amount"] = Decimal(str(round(float(data["amount"] or 0), 2)))
        if "splitwise_id" in data:
            sid = str(data["splitwise_id"] if data["splitwise_id"] is not None else "").strip()
            data["splitwise_id"] = int(float(sid)) if sid else None
        if "mandate_id" in data:
            data["mandate_id"] = int(data["mandate_id"]) if data["mandate_id"] else None
        return data

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        return date.fromisoformat(str(value)[:10])

    @staticmethod
    def _parse_datetime(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    # ------------------------------------------------------------------ #
    #  Reads                                                               #
    # ------------------------------------------------------------------ #

    def list_entries(self, start: date = None, end: date = None, include_mandates: bool = False) -> list:
        """Entries dated within [start, end] (either bound optional), newest
        first. Mandate templates are left out unless asked for — they are not
        spend and carry no meaningful date."""
        qs = self._qs()
        if not include_mandates:
            qs = qs.filter(is_mandate=False)
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return [self.to_entry(e) for e in qs]

    def total(self, start: date, end: date) -> float:
        """Sum of spend (mandate templates excluded) dated within [start, end]."""
        agg = self._qs().filter(is_mandate=False, date__gte=start, date__lte=end).aggregate(s=Sum("amount"))
        return float(agg["s"] or 0)

    def get_entry(self, page_id) -> dict:
        try:
            return self.to_entry(self._qs().get(pk=int(page_id)))
        except (Expense.DoesNotExist, ValueError, TypeError):
            raise ValueError("Expense not found")

    # ------------------------------------------------------------------ #
    #  Writes                                                              #
    # ------------------------------------------------------------------ #

    def create_entry(self, **fields) -> str:
        """Insert a row; returns its ``page_id``."""
        data = self._clean(fields)
        pk = Expense.objects.create(profile=self.profile, user_id=self.user_id, **data).pk
        self._remember(data)
        return str(pk)

    def update_entry(self, page_id, **fields) -> None:
        """Update only the fields given; anything omitted stays as it is."""
        data = self._clean(fields)
        # QuerySet.update() skips auto_now, so stamp updated_at by hand.
        n = self._qs().filter(pk=int(page_id)).update(updated_at=dj_timezone.now(), **data)
        if not n:
            raise ValueError("Expense not found")
        self._remember(data)

    def _remember(self, data: dict) -> None:
        """Save any new category / source / mode the person just used to their lists."""
        if self.user_id:
            options.register(
                self.user_id, categories=data.get("categories"),
                sources=data.get("sources"), mode=data.get("mode") or "",
            )

    def delete_entry(self, page_id) -> None:
        n, _ = self._qs().filter(pk=int(page_id)).delete()
        if not n:
            raise ValueError("Expense not found")

    @transaction.atomic
    def replace_entry(self, page_id, new_entries: list) -> list:
        """Delete ``page_id`` and create ``new_entries`` in one transaction —
        for split_entry, which Notion could only do as a non-atomic
        create-then-archive. Returns the new page_ids."""
        ids = [self.create_entry(**f) for f in new_entries]
        self.delete_entry(page_id)
        return ids

    # ------------------------------------------------------------------ #
    #  Recurring mandates                                                  #
    # ------------------------------------------------------------------ #

    def list_mandates(self) -> list:
        return [self.to_entry(e) for e in self._qs().filter(is_mandate=True)]

    def mandate_last_logged(self) -> dict:
        """{mandate page_id: latest occurrence date already logged}."""
        rows = (
            self._qs()
            .filter(mandate__isnull=False, date__isnull=False)
            .values("mandate_id")
            .annotate(last=Max("date"))
        )
        return {str(r["mandate_id"]): r["last"] for r in rows}

    # ------------------------------------------------------------------ #
    #  Pick-lists (categories / sources / modes)                           #
    # ------------------------------------------------------------------ #

    def options(self) -> dict:
        """The person's own lists. With no account behind this scope (a session
        from before accounts existed), fall back to the values their expenses use."""
        if self.user_id:
            return options.list_options(self.user_id)
        rows = list(self._qs().values_list("categories", "sources", "mode"))
        cats = {c for r in rows for c in r[0]}
        srcs = {x for r in rows for x in r[1]}
        modes = {r[2] for r in rows if r[2]}
        fmt = lambda names: [{"id": None, "name": n, "uses": None} for n in sorted(names, key=str.lower)]
        return {"categories": fmt(cats), "sources": fmt(srcs), "modes": fmt(modes)}

    def _need_user(self):
        if not self.user_id:
            raise options.OptionError("Sign in to an account to manage these lists", 403)

    def add_option(self, kind: str, name) -> tuple:
        self._need_user()
        return options.add_option(self.user_id, kind, name)

    def rename_option(self, kind: str, option_id, name) -> dict:
        self._need_user()
        return options.rename_option(self.user_id, kind, option_id, name)

    def delete_option(self, kind: str, option_id) -> None:
        self._need_user()
        options.delete_option(self.user_id, kind, option_id)

    # ------------------------------------------------------------------ #
    #  Splitwise                                                           #
    # ------------------------------------------------------------------ #

    def imported_splitwise_ids(self) -> set:
        return set(
            self._qs().filter(splitwise_id__isnull=False).values_list("splitwise_id", flat=True)
        )
