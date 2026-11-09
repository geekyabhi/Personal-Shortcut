"""A person's own pick-lists: categories, sources and modes.

Expenses store the plain text value; these functions manage the per-user catalog
the pickers offer (tables ``expense_categories`` / ``expense_sources`` /
``expense_modes``, each keyed by the user's uid).
"""
import re

from django.db import connection, transaction
from django.utils import timezone

from ..models import Expense, ExpenseCategory, ExpenseMode, ExpenseSource

# URL / API name -> (model, the Expense column that holds the value, is it a list column)
KINDS = {
    "categories": (ExpenseCategory, "categories", True),
    "sources": (ExpenseSource, "sources", True),
    "modes": (ExpenseMode, "mode", False),
}
MAX_LEN = 100


class OptionError(ValueError):
    """Bad input (400), unknown id (404) or a name clash (409)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def clean_name(name) -> str:
    """Trim and collapse inner whitespace; case is kept as typed."""
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    if not text:
        raise OptionError("Name is required")
    if len(text) > MAX_LEN:
        raise OptionError(f"Name must be at most {MAX_LEN} characters")
    return text


def _model(kind: str):
    if kind not in KINDS:
        raise OptionError(f"Unknown list '{kind}'. Use one of: {', '.join(KINDS)}", 404)
    return KINDS[kind][0]


def _usage(user_id, kind: str) -> dict:
    """{lower-cased value: number of the user's expenses using it}."""
    _, column, is_list = KINDS[kind]
    table = Expense._meta.db_table
    if is_list:
        sql = f"select lower(x), count(*) from {table}, unnest({column}) as x where user_id = %s group by 1"
    else:
        sql = f"select lower({column}), count(*) from {table} where user_id = %s and {column} <> '' group by 1"
    with connection.cursor() as cur:
        cur.execute(sql, [user_id])
        return {name: n for name, n in cur.fetchall()}


def list_options(user_id) -> dict:
    """{"categories": [{id, name, uses}], "sources": [...], "modes": [...]}, A→Z."""
    out = {}
    for kind, (model, _, _) in KINDS.items():
        used = _usage(user_id, kind)
        out[kind] = [
            {"id": o.pk, "name": o.name, "uses": used.get(o.name.lower(), 0)}
            for o in model.objects.filter(user_id=user_id).order_by("name")
        ]
    return out


def add_option(user_id, kind: str, name) -> tuple:
    """Save a value to the person's list. Returns (option, created); adding one
    that already exists (ignoring case) just returns the existing entry."""
    model, name = _model(kind), clean_name(name)
    existing = model.objects.filter(user_id=user_id, name__iexact=name).first()
    if existing:
        return existing, False
    return model.objects.create(user_id=user_id, name=name), True


def register(user_id, *, categories=(), sources=(), mode="") -> None:
    """Remember the values an expense was just saved with (silently skips blanks
    and anything already known)."""
    for kind, values in (("categories", categories or ()), ("sources", sources or ()), ("modes", [mode] if mode else ())):
        model = _model(kind)
        wanted = {}
        for v in values:
            try:
                name = clean_name(v)
            except OptionError:
                continue
            wanted.setdefault(name.lower(), name)
        if wanted:
            model.objects.bulk_create(
                [model(user_id=user_id, name=n) for n in wanted.values()], ignore_conflicts=True
            )


def rename_option(user_id, kind: str, option_id, new_name) -> dict:
    """Rename an entry and carry the new name onto the person's expenses.
    Returns {"option": obj, "expenses_updated": n}."""
    model, new_name = _model(kind), clean_name(new_name)
    _, column, is_list = KINDS[kind]
    try:
        obj = model.objects.get(pk=int(option_id), user_id=user_id)
    except (model.DoesNotExist, ValueError, TypeError):
        raise OptionError("Not found", 404)
    clash = model.objects.filter(user_id=user_id, name__iexact=new_name).exclude(pk=obj.pk).exists()
    if clash:
        raise OptionError(f"'{new_name}' already exists", 409)

    old = obj.name
    table, now = Expense._meta.db_table, timezone.now()
    with transaction.atomic():
        obj.name = new_name
        obj.save(update_fields=["name"])
        with connection.cursor() as cur:
            if is_list:   # swap the element in place, keeping the array's order
                cur.execute(
                    f"""update {table} set {column} = (
                          select array_agg(case when lower(x) = lower(%s) then %s else x end order by ord)
                          from unnest({column}) with ordinality as t(x, ord)),
                        updated_at = %s
                        where user_id = %s and exists (select 1 from unnest({column}) x where lower(x) = lower(%s))""",
                    [old, new_name, now, user_id, old],
                )
            else:
                cur.execute(
                    f"update {table} set {column} = %s, updated_at = %s where user_id = %s and lower({column}) = lower(%s)",
                    [new_name, now, user_id, old],
                )
            changed = cur.rowcount
    return {"option": obj, "expenses_updated": changed}


def delete_option(user_id, kind: str, option_id) -> None:
    """Remove an entry from the person's list. Expenses already saved with the
    value keep it; it simply stops being offered (until it's used again)."""
    model = _model(kind)
    n, _ = model.objects.filter(pk=option_id, user_id=user_id).delete()
    if not n:
        raise OptionError("Not found", 404)


def sync_from_expenses(user_id) -> dict:
    """Fill the person's lists from the values their expenses already use.
    Safe to re-run; where an entry exists in several casings the most-used wins."""
    added = {}
    for kind, (model, column, is_list) in KINDS.items():
        table = Expense._meta.db_table
        if is_list:
            sql = f"select x, count(*) from {table}, unnest({column}) as x where user_id = %s and x <> '' group by x"
        else:
            sql = f"select {column}, count(*) from {table} where user_id = %s and {column} <> '' group by {column}"
        with connection.cursor() as cur:
            cur.execute(sql, [user_id])
            counts = cur.fetchall()
        best = {}
        for name, n in counts:
            key = name.lower()
            if key not in best or n > best[key][1]:
                best[key] = (name, n)
        before = model.objects.filter(user_id=user_id).count()
        model.objects.bulk_create([model(user_id=user_id, name=n) for n, _ in best.values()], ignore_conflicts=True)
        added[kind] = model.objects.filter(user_id=user_id).count() - before
    return added
