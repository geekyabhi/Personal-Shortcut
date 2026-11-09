import json
import re
import time
from datetime import date, datetime, timedelta, timezone

from dateutil.relativedelta import relativedelta

from ..data_services import ExpensesDataService


class ExpensesService:
    VALID_PERIODS = ("all", "yearly", "monthly", "weekly", "daily", "custom")
    VALID_GROUPS = ("category", "source")
    VALID_SORTS = ("date_desc", "date_asc", "amount_desc", "amount_asc")
    VALID_BUCKETS = ("day", "week", "month", "year")

    YEAR_RE  = re.compile(r"^\d{4}$")
    MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    WEEK_RE  = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")
    DAY_RE   = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")

    # ── Recurring mandates ── #
    MANDATE_STEP = {
        "Weekly":    relativedelta(weeks=1),
        "Monthly":   relativedelta(months=1),
        "Quarterly": relativedelta(months=3),
        "Yearly":    relativedelta(years=1),
    }

    def __init__(self, data_layer: ExpensesDataService):
        self.dl = data_layer

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _validate_period(
        self,
        period: str,
        year: str,
        month: str,
        week: str,
        day: str,
        start: str,
        end: str,
        group_by: str = "",
        sort: str = "",
        bucket: str = "",
    ) -> None:
        """Raises ValueError with a descriptive message on bad input."""
        if period not in self.VALID_PERIODS:
            raise ValueError(
                f"Invalid period '{period}'. Valid options: {', '.join(self.VALID_PERIODS)}"
            )
        if group_by and group_by not in self.VALID_GROUPS:
            raise ValueError(
                f"Invalid group_by '{group_by}'. Valid options: {', '.join(self.VALID_GROUPS)}"
            )
        if bucket and bucket not in self.VALID_BUCKETS:
            raise ValueError(
                f"Invalid bucket '{bucket}'. Valid options: {', '.join(self.VALID_BUCKETS)}"
            )
        if sort and sort not in self.VALID_SORTS:
            raise ValueError(
                f"Invalid sort. Valid: {', '.join(self.VALID_SORTS)}"
            )
        if year and not self.YEAR_RE.match(year):
            raise ValueError("Invalid year format. Use YYYY (e.g. 2026)")
        if month and not self.MONTH_RE.match(month):
            raise ValueError("Invalid month format. Use YYYY-MM (e.g. 2026-03)")
        if week and not self.WEEK_RE.match(week):
            raise ValueError("Invalid week format. Use YYYY-Www (e.g. 2026-W19)")
        if day and not self.DAY_RE.match(day):
            raise ValueError("Invalid day format. Use YYYY-MM-DD (e.g. 2026-05-10)")
        if period == "custom":
            if not start or not end:
                raise ValueError("Custom period requires both start and end")
            if not self.DAY_RE.match(start):
                raise ValueError("Invalid start date. Use YYYY-MM-DD")
            if not self.DAY_RE.match(end):
                raise ValueError("Invalid end date. Use YYYY-MM-DD")
            if start > end:
                raise ValueError("start must be on or before end")

    def _build_date_filter(
        self,
        period: str,
        year: str = None,
        month: str = None,
        week: str = None,
        day: str = None,
        start: str = None,
        end: str = None,
    ):
        """Returns (range_start, range_end), both inclusive. (None, None) for period='all'."""
        today = date.today()

        if period == "all":
            return None, None

        if period == "yearly":
            y = int(year) if year else today.year
            s = date(y, 1, 1)
            e = date(y + 1, 1, 1)

        elif period == "monthly":
            if month:
                yr, m = int(month[:4]), int(month[5:])
                s = date(yr, m, 1)
            else:
                s = today.replace(day=1)
            e = date(s.year + 1, 1, 1) if s.month == 12 else date(s.year, s.month + 1, 1)

        elif period == "weekly":
            if week:
                yr, week_num = int(week[:4]), int(week[6:])
                s = date.fromisocalendar(yr, week_num, 1)
            else:
                s = today - timedelta(days=today.weekday())
            e = s + timedelta(days=7)

        elif period == "daily":
            s = date.fromisoformat(day) if day else today
            e = s + timedelta(days=1)

        elif period == "custom":
            s = date.fromisoformat(start) if start else date(today.year, 1, 1)
            e = date.fromisoformat(end) + timedelta(days=1) if end else today + timedelta(days=1)

        return s, e - timedelta(days=1)

    def _filter_by_date(self, rows: list, range_start, range_end) -> list:
        """Filter rows to [range_start, range_end] inclusive. Returns all if range_start is None."""
        if range_start is None:
            return rows
        result = []
        for row in rows:
            if not row["date"]:
                continue
            try:
                d = date.fromisoformat(row["date"])
            except ValueError:
                continue
            if range_start <= d <= range_end:
                result.append(row)
        return result

    def _get_rows(self, force: bool = False, partial: bool = False, start=None, end=None):
        """The non-mandate entries dated within [start, end] (all of them when
        both are None), as ``(rows, cache_ts, from_cache, is_partial)``.

        The date range is applied **in SQL**, so a one-month query only fetches
        that month's rows — over a remote database fetching and then filtering
        every row in Python was the whole cost of a request.

        The 4-tuple is kept for the API responses the UI reads. There is no
        cache any more — Postgres is queried directly — so ``force`` and
        ``partial`` have nothing to do and the result is always fresh. Mandate
        templates are left out so they never appear as a phantom line item; only
        their real backfilled occurrences count as spending."""
        return self.dl.list_entries(start, end), time.time(), False, False

    # ------------------------------------------------------------------ #
    #  Generic row-filter rules (the client-side "filter builder")        #
    # ------------------------------------------------------------------ #

    _RULE_NOVALUE_OPS = {"empty", "nempty", "true", "false"}
    _RULE_BOOL_FIELDS = {"processed", "add_to_split", "from_split", "split_added"}
    _RULE_NUM_FIELDS  = {"amount", "splitwise_id"}
    _RULE_DATE_FIELDS = {"date"}
    _RULE_MULTI_FIELDS = {"categories"}

    def _rule_complete(self, r: dict) -> bool:
        if r.get("op") in self._RULE_NOVALUE_OPS:
            return True
        if r.get("value") in ("", None):
            return False
        if r.get("op") == "between" and r.get("value2") in ("", None):
            return False
        return True

    def _rule_field_value(self, e: dict, field: str):
        if field == "date":
            return e.get("date") or (e.get("datetime") or "")[:10]
        return e.get(field)

    def _rule_match(self, e: dict, r: dict) -> bool:
        field, op = r["field"], r["op"]
        v = self._rule_field_value(e, field)
        a, b = r.get("value", ""), r.get("value2", "")

        if field in self._RULE_BOOL_FIELDS:
            return bool(v) if op == "true" else not bool(v)

        if field in self._RULE_MULTI_FIELDS:
            arr = [str(x).lower() for x in (v or [])]
            t = str(a).lower()
            if op == "empty":  return not arr
            if op == "nempty": return bool(arr)
            if op == "has":    return t in arr
            if op == "nhas":   return t not in arr
            if op == "only":   return arr == [t]
            return True

        if field in self._RULE_NUM_FIELDS:
            try:
                n = None if v in ("", None) else float(v)
            except (TypeError, ValueError):
                n = None
            if op == "empty":  return n is None
            if op == "nempty": return n is not None
            if n is None:
                return False
            try:
                x = float(a)
                y = float(b) if b not in ("", None) else x
            except (TypeError, ValueError):
                return True
            return {
                "eq": n == x, "ne": n != x, "gt": n > x, "lt": n < x,
                "gte": n >= x, "lte": n <= x,
                "between": min(x, y) <= n <= max(x, y),
            }.get(op, True)

        if field in self._RULE_DATE_FIELDS:
            d = v or ""
            if op == "empty":  return not d
            if op == "nempty": return bool(d)
            if not d:
                return False
            if op == "on":     return d == a
            if op == "before": return d < a
            if op == "after":  return d > a
            if op == "between": return (a <= d <= b) if b else (d >= a)
            return True

        # text / select
        s = ("" if v is None else str(v)).lower()
        t = str(a).lower()
        if op == "empty":     return not s
        if op == "nempty":    return bool(s)
        if op == "contains":  return t in s
        if op == "ncontains": return t not in s
        if op == "is":        return s == t
        if op == "isnot":     return s != t
        return True

    def _rule_active(self, node) -> bool:
        """True if a leaf is a usable rule, or a group has any active descendant."""
        if not isinstance(node, dict):
            return False
        if isinstance(node.get("rules"), list):
            return any(self._rule_active(child) for child in node["rules"])
        return bool(node.get("field") and node.get("op") and self._rule_complete(node))

    def _node_match(self, e: dict, node: dict) -> bool:
        if isinstance(node.get("rules"), list):
            kids = [c for c in node["rules"] if self._rule_active(c)]
            if not kids:
                return True
            results = [self._node_match(e, k) for k in kids]
            return any(results) if node.get("join") == "or" else all(results)
        return self._rule_match(e, node)

    def _filter_by_rules(self, rows: list, filters_raw: str) -> list:
        """Apply the client-side filter builder's rule tree (JSON) to entries. A node is either a leaf {field, op, value, value2} or a group
        {join: "and"|"or", rules: [node, ...]} — groups nest to express
        bracketed sub-expressions mixing AND/OR. A bare JSON array (the old
        flat format) is treated as an implicit top-level AND group. Unknown /
        half-built rules are ignored. Returns ``rows`` unchanged when there's
        nothing to apply."""
        if not filters_raw:
            return rows
        try:
            parsed = json.loads(filters_raw)
        except (ValueError, TypeError):
            return rows
        root = {"join": "and", "rules": parsed} if isinstance(parsed, list) else parsed
        if not isinstance(root, dict) or not isinstance(root.get("rules"), list):
            return rows
        if not self._rule_active(root):
            return rows
        return [row for row in rows if self._node_match(row, root)]

    def _row_date(self, row) -> str:
        return row["date"]

    def _row_amount(self, row) -> float:
        return row["amount"]

    def _row_categories(self, row) -> list:
        return row["categories"] or ["Uncategorized"]

    def _row_source(self, row) -> str:
        return row["source"]

    _EPOCH = datetime.min.replace(tzinfo=timezone.utc)

    def _entry_dt_key(self, e) -> datetime:
        """Chronologically-sortable, timezone-aware value for an entry — uses the
        full recorded datetime when there is one, else the day at midnight UTC.
        Entries with no date sort earliest."""
        raw = (e.get("datetime") or e.get("date") or "").strip()
        if not raw:
            return self._EPOCH
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                d = datetime.fromisoformat(raw[:10])
            except ValueError:
                return self._EPOCH
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

    def _extract_groups(self, row, group_by) -> list:
        if group_by == "category":
            return row["categories"] or ["Uncategorized"]
        if group_by == "source":
            return row["sources"] or ["Unknown"]
        return []

    def _build_display(
        self,
        period: str,
        grand_total: float,
        group_by: str,
        group_totals: dict,
        range_start,
        range_end,
    ) -> str:
        if period == "all":
            header = "All Time"
        elif period == "yearly":
            header = range_start.strftime("%Y")
        elif period == "monthly":
            header = range_start.strftime("%B %Y")
        elif period == "weekly":
            header = f"Week of {range_start.strftime('%d %b')} - {range_end.strftime('%d %b %Y')}"
        elif period == "daily":
            header = range_start.strftime("%d %B %Y")
        elif period == "custom":
            header = f"{range_start.strftime('%d %b %Y')} – {range_end.strftime('%d %b %Y')}"

        lines = [f"{header}  |  Total: {grand_total:,.2f}"]

        if group_by and group_totals:
            lines.append("")
            lines.append(f"By {group_by.title()}:")
            pad = max(len(g) for g in group_totals)
            for g, t in sorted(group_totals.items(), key=lambda x: -x[1]):
                lines.append(f"  {g:<{pad}}   {t:>10,.2f}")

        return "\n".join(lines)

    def _period_meta(
        self,
        period: str,
        year: str,
        month: str,
        range_start,
        range_end,
    ) -> dict:
        meta: dict = {}
        if period == "yearly":
            meta["year"] = year if year else str(date.today().year)
        elif period == "monthly":
            meta["month"] = month if month else date.today().strftime("%Y-%m")
        elif period == "weekly":
            meta["week_start"] = range_start.isoformat()
            meta["week_end"] = range_end.isoformat()
        elif period == "daily":
            meta["date"] = range_start.isoformat()
        elif period == "custom":
            meta["start"] = range_start.isoformat()
            meta["end"] = range_end.isoformat()
        return meta

    def _generic_bucket_keys(self, range_start, range_end, unit):
        """(bucket_keys, key_fn, fmt) for an explicit bucket unit — 'day', 'week',
        'month', or 'year' — spanning [range_start, range_end] inclusive, letting the
        user pick a time-frame independent of the period's own default granularity.
        key_fn maps a full "YYYY-MM-DD" row date to one of bucket_keys."""
        if unit == "day":
            keys = []
            d = range_start
            while d <= range_end:
                keys.append(d.isoformat())
                d += timedelta(days=1)
            return keys, (lambda ds: ds[:10]), (lambda k: date.fromisoformat(k).strftime("%-d %b %Y"))

        if unit == "week":
            d = range_start - timedelta(days=range_start.weekday())  # back up to Monday
            keys = []
            while d <= range_end:
                keys.append(d.isoformat())
                d += timedelta(days=7)

            def key_fn(ds):
                dd = date.fromisoformat(ds[:10])
                return (dd - timedelta(days=dd.weekday())).isoformat()

            return keys, key_fn, (lambda k: "Wk of " + date.fromisoformat(k).strftime("%-d %b"))

        if unit == "month":
            keys = []
            y, m = range_start.year, range_start.month
            while date(y, m, 1) <= range_end:
                keys.append(f"{y}-{m:02d}")
                m += 1
                if m > 12:
                    m, y = 1, y + 1
            return keys, (lambda ds: ds[:7]), (lambda k: date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y"))

        # "year"
        keys = [str(y) for y in range(range_start.year, range_end.year + 1)]
        return keys, (lambda ds: ds[:4]), (lambda k: k)

    def _bucket_override_range(self, rows, range_start, range_end):
        """When the period has no fixed range (e.g. 'all'), derive one from the
        actual row dates so an explicit bucket override still has bounds."""
        if range_start is not None and range_end is not None:
            return range_start, range_end
        dates = sorted(d for d in (self._row_date(r) for r in rows) if d)
        if not dates:
            return None, None
        return date.fromisoformat(dates[0]), date.fromisoformat(dates[-1])

    def _build_timeseries(self, period, year, rows, range_start, range_end, bucket=""):
        """Return (labels, values) lists bucketed by the appropriate time unit."""
        if bucket in self.VALID_BUCKETS:
            rs, re_ = self._bucket_override_range(rows, range_start, range_end)
            if rs is None:
                return [], []
            keys, key_fn, fmt = self._generic_bucket_keys(rs, re_, bucket)
            totals = {k: 0.0 for k in keys}
            for row in rows:
                d_str = self._row_date(row)
                if not d_str:
                    continue
                k = key_fn(d_str)
                if k in totals:
                    totals[k] = round(totals[k] + self._row_amount(row), 2)
            return [fmt(k) for k in keys], [totals[k] for k in keys]

        if period == "daily":
            return (
                [range_start.strftime("%d %b %Y")],
                [round(sum(self._row_amount(r) for r in rows), 2)],
            )

        if period in ("monthly", "weekly"):
            buckets: dict[str, float] = {}
            d = range_start
            while d <= range_end:
                buckets[d.isoformat()] = 0.0
                d += timedelta(days=1)
            for row in rows:
                k = self._row_date(row)
                if k in buckets:
                    buckets[k] = round(buckets[k] + self._row_amount(row), 2)
            fmt = "%a %d" if period == "weekly" else "%-d"
            return (
                [date.fromisoformat(k).strftime(fmt) for k in sorted(buckets)],
                [buckets[k] for k in sorted(buckets)],
            )

        if period == "yearly":
            y = int(year) if year else date.today().year
            buckets = {f"{y}-{m:02d}": 0.0 for m in range(1, 13)}
            for row in rows:
                k = self._row_date(row)[:7]
                if k in buckets:
                    buckets[k] = round(buckets[k] + self._row_amount(row), 2)
            return (
                [date(int(k[:4]), int(k[5:]), 1).strftime("%b") for k in sorted(buckets)],
                [buckets[k] for k in sorted(buckets)],
            )

        if period == "custom":
            delta = (range_end - range_start).days
            if delta <= 60:
                buckets2: dict[str, float] = {}
                d = range_start
                while d <= range_end:
                    buckets2[d.isoformat()] = 0.0
                    d += timedelta(days=1)
                for row in rows:
                    k = self._row_date(row)
                    if k in buckets2:
                        buckets2[k] = round(buckets2[k] + self._row_amount(row), 2)
                return (
                    [date.fromisoformat(k).strftime("%-d %b") for k in sorted(buckets2)],
                    [buckets2[k] for k in sorted(buckets2)],
                )
            buckets3: dict[str, float] = {}
            d = range_start
            while d <= range_end:
                k = d.strftime("%Y-%m")
                buckets3.setdefault(k, 0.0)
                d += timedelta(days=1)
            for row in rows:
                k = self._row_date(row)[:7]
                if k in buckets3:
                    buckets3[k] = round(buckets3[k] + self._row_amount(row), 2)
            sorted_keys = sorted(buckets3)
            return (
                [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in sorted_keys],
                [buckets3[k] for k in sorted_keys],
            )

        # "all" — dynamic month buckets from data
        buckets4: dict[str, float] = {}
        for row in rows:
            k = self._row_date(row)[:7]
            if len(k) == 7:
                buckets4[k] = round(buckets4.get(k, 0.0) + self._row_amount(row), 2)
        sorted_keys2 = sorted(buckets4)
        return (
            [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in sorted_keys2],
            [buckets4[k] for k in sorted_keys2],
        )

    def _build_category_timeseries(self, period, year, rows, range_start, range_end, bucket=""):
        """Returns (labels, overall_values, category_series).
        category_series = [{"name", "values": [...], "total"}, ...] sorted by total desc.
        All category arrays are aligned to the same labels list.
        """
        today = date.today()

        # Build bucket keys + key extractor + label formatter
        if bucket in self.VALID_BUCKETS:
            rs, re_ = self._bucket_override_range(rows, range_start, range_end)
            if rs is None:
                return [], [], []
            bucket_keys, key_fn, fmt = self._generic_bucket_keys(rs, re_, bucket)

        elif period == "daily":
            bucket_keys = [range_start.isoformat()]
            key_fn = lambda d: range_start.isoformat()
            fmt = lambda k: date.fromisoformat(k).strftime("%d %b %Y")

        elif period in ("monthly", "weekly"):
            bucket_keys = []
            d = range_start
            while d <= range_end:
                bucket_keys.append(d.isoformat())
                d += timedelta(days=1)
            key_fn = lambda d: d[:10]
            fmt = (lambda k: date.fromisoformat(k).strftime("%a %d")) if period == "weekly" \
                  else (lambda k: date.fromisoformat(k).strftime("%-d"))

        elif period == "yearly":
            y = int(year) if year else today.year
            bucket_keys = [f"{y}-{m:02d}" for m in range(1, 13)]
            key_fn = lambda d: d[:7]
            fmt = lambda k: date(int(k[:4]), int(k[5:]), 1).strftime("%b")

        elif period == "custom":
            delta = (range_end - range_start).days
            if delta <= 60:
                bucket_keys = []
                d = range_start
                while d <= range_end:
                    bucket_keys.append(d.isoformat())
                    d += timedelta(days=1)
                key_fn = lambda d: d[:10]
                fmt = lambda k: date.fromisoformat(k).strftime("%-d %b")
            else:
                seen: dict[str, bool] = {}
                d = range_start
                while d <= range_end:
                    seen.setdefault(d.strftime("%Y-%m"), True)
                    d += timedelta(days=1)
                bucket_keys = sorted(seen)
                key_fn = lambda d: d[:7]
                fmt = lambda k: date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y")

        else:  # "all" — derive from data
            month_set: set[str] = set()
            for row in rows:
                k = self._row_date(row)[:7]
                if len(k) == 7:
                    month_set.add(k)
            bucket_keys = sorted(month_set)
            key_fn = lambda d: d[:7]
            fmt = lambda k: date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y")

        if not bucket_keys:
            return [], [], []

        bucket_set = set(bucket_keys)
        overall: dict[str, float] = {k: 0.0 for k in bucket_keys}
        cat_data: dict[str, dict[str, float]] = {}

        for row in rows:
            d_str = self._row_date(row)
            if not d_str:
                continue
            k = key_fn(d_str)
            if k not in bucket_set:
                continue
            amount = self._row_amount(row)
            overall[k] = round(overall[k] + amount, 2)
            cats = self._row_categories(row)
            for cat in cats:
                if cat not in cat_data:
                    cat_data[cat] = {bk: 0.0 for bk in bucket_keys}
                cat_data[cat][k] = round(cat_data[cat][k] + amount, 2)

        labels = [fmt(k) for k in bucket_keys]
        overall_values = [overall[k] for k in bucket_keys]
        category_series = sorted(
            [
                {
                    "name": cat,
                    "values": [round(data[k], 2) for k in bucket_keys],
                    "total": round(sum(data.values()), 2),
                }
                for cat, data in cat_data.items()
            ],
            key=lambda x: -x["total"],
        )
        return labels, overall_values, category_series

    # ------------------------------------------------------------------ #
    #  Public methods                                                      #
    # ------------------------------------------------------------------ #

    def get_summary(
        self,
        period: str,
        group_by: str,
        year: str,
        month: str,
        week: str,
        day: str,
        start: str,
        end: str,
        force: bool,
        partial: bool = False,
        filters: str = "",
    ) -> dict:
        self._validate_period(period, year, month, week, day, start, end, group_by=group_by)
        range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self._get_rows(
            force=force, partial=partial, start=range_start, end=range_end
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))

        group_totals: dict[str, float] = {}
        grand_total = 0.0

        for row in rows:
            amount = row["amount"]
            grand_total += amount
            if group_by:
                for g in self._extract_groups(row, group_by):
                    group_totals[g] = group_totals.get(g, 0.0) + amount

        response: dict = {
            "period": period,
            "grand_total": round(grand_total, 2),
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "partial": is_partial,
            "total_rows": len(all_rows),
        }
        response.update(self._period_meta(period, year, month, range_start, range_end))

        if group_by:
            response["group_by"] = group_by
            response["summary"] = [
                {"group": g, "total": round(t, 2)}
                for g, t in sorted(group_totals.items())
            ]

        display_start = range_start or date.today()
        display_end = range_end or date.today()
        response["display"] = self._build_display(
            period, round(grand_total, 2), group_by, group_totals, display_start, display_end
        )
        return response

    def get_timeseries(
        self,
        period: str,
        year: str,
        month: str,
        week: str,
        day: str,
        start: str,
        end: str,
        force: bool,
        partial: bool = False,
        filters: str = "",
    ) -> dict:
        self._validate_period(period, year, month, week, day, start, end)
        range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self._get_rows(
            force=force, partial=partial, start=range_start, end=range_end
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))
        labels, values = self._build_timeseries(period, year, rows, range_start, range_end)
        return {
            "labels": labels,
            "values": values,
            "period": period,
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "partial": is_partial,
            "total_rows": len(all_rows),
        }

    def get_chart(
        self,
        period: str,
        group_by: str,
        year: str,
        month: str,
        week: str,
        day: str,
        start: str,
        end: str,
        force: bool,
        partial: bool = False,
        filters: str = "",
        bucket: str = "",
    ) -> dict:
        self._validate_period(period, year, month, week, day, start, end, group_by=group_by, bucket=bucket)
        range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self._get_rows(
            force=force, partial=partial, start=range_start, end=range_end
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))

        grand_total = round(sum(row["amount"] for row in rows), 2)

        trend_labels, trend_values = self._build_timeseries(period, year, rows, range_start, range_end, bucket)

        breakdown = None
        if group_by:
            group_totals: dict[str, float] = {}
            for row in rows:
                amount = row["amount"]
                for g in self._extract_groups(row, group_by):
                    group_totals[g] = round(group_totals.get(g, 0.0) + amount, 2)
            sorted_groups = sorted(group_totals.items(), key=lambda x: -x[1])
            breakdown = {
                "labels": [g for g, _ in sorted_groups],
                "values": [t for _, t in sorted_groups],
            }

        display_start = range_start or date.today()
        display_end = range_end or date.today()
        group_totals_for_display = (
            dict(zip(breakdown["labels"], breakdown["values"])) if breakdown else {}
        )

        response: dict = {
            "period": period,
            "grand_total": grand_total,
            "entry_count": len(rows),
            "trend": {"labels": trend_labels, "values": trend_values},
            "display": self._build_display(
                period, grand_total, group_by, group_totals_for_display,
                display_start, display_end
            ),
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "partial": is_partial,
            "total_rows": len(all_rows),
        }
        response.update(self._period_meta(period, year, month, range_start, range_end))

        if breakdown:
            response["group_by"] = group_by
            response["breakdown"] = breakdown

        return response

    def get_category_timeseries(
        self,
        period: str,
        year: str,
        month: str,
        week: str,
        day: str,
        start: str,
        end: str,
        force: bool,
        partial: bool = False,
        filters: str = "",
        bucket: str = "",
    ) -> dict:
        self._validate_period(period, year, month, week, day, start, end, bucket=bucket)
        range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self._get_rows(
            force=force, partial=partial, start=range_start, end=range_end
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))
        labels, overall_values, category_series = self._build_category_timeseries(
            period, year, rows, range_start, range_end, bucket
        )
        return {
            "period": period,
            "labels": labels,
            "overall": overall_values,
            "by_category": category_series,
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "partial": is_partial,
            "total_rows": len(all_rows),
        }

    def get_insights(
        self,
        period: str,
        year: str,
        month: str,
        week: str,
        day: str,
        start: str,
        end: str,
        force: bool,
        partial: bool = False,
        filters: str = "",
    ) -> dict:
        self._validate_period(period, year, month, week, day, start, end)
        range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self._get_rows(
            force=force, partial=partial, start=range_start, end=range_end
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))

        cat_totals: dict[str, dict] = {}
        src_totals: dict[str, dict] = {}
        modes_seen: set[str] = set()
        grand_total = 0.0
        entries = []

        for row in rows:
            e = row
            grand_total += e["amount"]
            entries.append(e)

            cats = e["categories"] or ["Uncategorized"]
            for cat in cats:
                rec = cat_totals.setdefault(cat, {"total": 0.0, "count": 0})
                rec["total"] += e["amount"]
                rec["count"] += 1

            src = e["source"] or "Unknown"
            rec = src_totals.setdefault(src, {"total": 0.0, "count": 0})
            rec["total"] += e["amount"]
            rec["count"] += 1

            if e["mode"]:
                modes_seen.add(e["mode"])

        cat_list = sorted(
            [
                {
                    "name": k,
                    "total": round(v["total"], 2),
                    "count": v["count"],
                    "pct": round(v["total"] / grand_total * 100, 1) if grand_total else 0.0,
                }
                for k, v in cat_totals.items()
            ],
            key=lambda x: -x["total"],
        )
        src_list = sorted(
            [
                {
                    "name": k,
                    "total": round(v["total"], 2),
                    "count": v["count"],
                    "pct": round(v["total"] / grand_total * 100, 1) if grand_total else 0.0,
                }
                for k, v in src_totals.items()
            ],
            key=lambda x: -x["total"],
        )
        mode_list = [{"name": m} for m in sorted(modes_seen)]
        top_entries = sorted(entries, key=lambda x: -x["amount"])[:10]
        top3_pct = (
            round(sum(c["total"] for c in cat_list[:3]) / grand_total * 100, 1)
            if grand_total
            else 0.0
        )

        return {
            "period": period,
            "grand_total": round(grand_total, 2),
            "entry_count": len(rows),
            "by_category": cat_list,
            "by_source": src_list,
            "by_mode": mode_list,
            "top_entries": top_entries,
            "concentration": {
                "top1_name": cat_list[0]["name"] if cat_list else "",
                "top1_pct": cat_list[0]["pct"] if cat_list else 0.0,
                "top3_pct": top3_pct,
            },
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "partial": is_partial,
            "total_rows": len(all_rows),
        }

    def list_entries(
        self,
        period: str,
        year: str,
        month: str,
        week: str,
        day: str,
        start: str,
        end: str,
        category: str,
        source: str,
        min_amount,
        max_amount,
        sort: str,
        search: str,
        force: bool,
        page: int,
        page_size: int,
        split_filter: str = "",
        partial: bool = False,
        unpaginated: bool = False,
        processed: str = "",
    ) -> dict:
        self._validate_period(period, year, month, week, day, start, end, sort=sort)
        range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self._get_rows(
            force=force, partial=partial, start=range_start, end=range_end
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))

        filter_cats = [c.strip() for c in category.split(",") if c.strip()] if category else []

        entries = []
        for row in rows:
            e = row

            if min_amount is not None and e["amount"] < min_amount:
                continue
            if max_amount is not None and e["amount"] > max_amount:
                continue
            if filter_cats and not any(c in e["categories"] for c in filter_cats):
                continue
            if source and e["source"] != source:
                continue
            if search and search not in e["title"].lower():
                continue
            if split_filter == "needs" and not (e["add_to_split"] and not e["split_added"]):
                continue
            if split_filter == "done" and not e["split_added"]:
                continue
            if split_filter == "flagged" and not e["add_to_split"]:
                continue
            if split_filter == "unflagged" and e["add_to_split"]:
                continue
            if processed == "true" and not e["processed"]:
                continue
            if processed == "false" and e["processed"]:
                continue

            entries.append(e)

        if sort == "date_desc":
            entries.sort(key=self._entry_dt_key, reverse=True)
        elif sort == "date_asc":
            entries.sort(key=self._entry_dt_key)
        elif sort == "amount_desc":
            entries.sort(key=lambda x: -x["amount"])
        elif sort == "amount_asc":
            entries.sort(key=lambda x: x["amount"])

        total_count = len(entries)

        if unpaginated:
            page_out, total_pages, page_entries = 1, 1, entries
        else:
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page_out = min(page, total_pages)
            start_idx = (page_out - 1) * page_size
            page_entries = entries[start_idx: start_idx + page_size]

        return {
            "total_count": total_count,
            "page": page_out,
            "page_size": page_size,
            "total_pages": total_pages,
            "entries": page_entries,
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "partial": is_partial,
            "total_rows": len(all_rows),
        }

    def get_heatmap(
        self,
        period: str,
        year: str,
        month: str,
        week: str,
        day: str,
        start: str,
        end: str,
        force: bool,
        partial: bool = False,
        filters: str = "",
    ) -> dict:
        self._validate_period(period, year, month, week, day, start, end)
        range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self._get_rows(
            force=force, partial=partial, start=range_start, end=range_end
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))

        daily: dict[str, float] = {}
        for row in rows:
            d_str = self._row_date(row)
            if not d_str:
                continue
            amount = self._row_amount(row)
            daily[d_str] = round(daily.get(d_str, 0.0) + amount, 2)

        # For period=all, derive actual date range from the data itself
        if range_start is None and daily:
            dates = sorted(daily.keys())
            range_start = date.fromisoformat(dates[0])
            range_end = date.fromisoformat(dates[-1])

        return {
            "daily": daily,
            "range_start": range_start.isoformat() if range_start else None,
            "range_end": range_end.isoformat() if range_end else None,
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "partial": is_partial,
        }

    # Optional per-row columns a caller may send; ``None`` means "leave as is".
    _BOOL_FIELDS = (
        "add_to_split", "from_split", "split_added", "processed",
        "is_mandate", "recurring",
    )

    @classmethod
    def _write_fields(cls, name, amount, date_str, categories, source, mode, extra) -> dict:
        """Entry arguments -> the field dict ExpensesDataService writes. An empty
        ``date_str`` leaves the stored date (and its time) untouched on update."""
        fields = {
            "title": name,
            "amount": float(amount),
            "categories": list(categories or []),
            "sources": [source] if source else [],
            "mode": mode,
        }
        if date_str:
            fields["date"] = date_str
        for key, value in extra.items():
            if value is None:
                continue
            if key in cls._BOOL_FIELDS:
                value = bool(value)
            if key == "mandate_source_id":  # the mandate template this row came from
                key = "mandate_id"
            fields[key] = value
        return fields

    def create_entry(
        self,
        name: str,
        amount,
        date_str: str,
        categories: list,
        source: str,
        mode: str = "",
        **extra,
    ) -> str:
        """Validates fields and inserts the row. Returns its page_id.
        ``extra`` may carry comment / other_partner / add_to_split / from_split /
        split_added / processed / splitwise_id / the mandate_* fields / recurring."""
        if not name:
            raise ValueError("Name is required")
        if amount is None:
            raise ValueError("Amount is required")
        if not date_str:
            raise ValueError("Date is required")
        return self.dl.create_entry(
            **self._write_fields(name, amount, date_str, categories, source, mode, extra)
        )

    # ------------------------------------------------------------------ #
    #  Recurring mandates — reconciliation / backfill                     #
    # ------------------------------------------------------------------ #

    def _mandate_missing_dates(self, mandate: dict, last_logged: dict, cap) -> list:
        """Occurrence dates for ``mandate`` that fall on/before ``cap``
        (further capped by the mandate's own End Date, if set) but have no
        real expense row logged for them yet. [] for a misconfigured mandate
        (unknown frequency / unparseable start) — it must never be treated
        as having infinite/undefined occurrences."""
        step = self.MANDATE_STEP.get(mandate["mandate_frequency"])
        if not step or not mandate["mandate_start"]:
            return []
        try:
            start = date.fromisoformat(mandate["mandate_start"])
        except ValueError:
            return []

        if mandate["mandate_end"]:
            try:
                cap = min(cap, date.fromisoformat(mandate["mandate_end"]))
            except ValueError:
                pass

        cursor = last_logged.get(mandate["page_id"], start - step)
        missing = []
        nxt = cursor + step
        while nxt <= cap:
            missing.append(nxt)
            nxt += step
        return missing

    def get_mandate_reconciliation(self) -> dict:
        """What's pending: every mandate with at least one occurrence that
        should have happened by today but has no matching expense row yet."""
        today = date.today()
        last_logged = self.dl.mandate_last_logged()

        pending = []
        for mandate in self.dl.list_mandates():
            missing = self._mandate_missing_dates(mandate, last_logged, today)
            if not missing:
                continue
            pending.append({
                "page_id": mandate["page_id"],
                "title": mandate["title"],
                "amount": mandate["amount"],
                "frequency": mandate["mandate_frequency"],
                "missing_dates": [d.isoformat() for d in missing],
            })
        return {"pending": pending}

    def backfill_mandate(self, mandate_page_id: str, cutoff_date: str = "") -> dict:
        """Creates one real expense row per missing occurrence, through
        today (``cutoff_date`` empty — "still running") or through
        ``cutoff_date`` (the mandate ended then; nothing beyond it is
        created, and — deliberately — the mandate's own End Date is left
        untouched here; see the recurring-mandates plan)."""
        entry = next(
            (m for m in self.dl.list_mandates() if m["page_id"] == mandate_page_id), None
        )
        if not entry:
            raise ValueError("Mandate not found")

        cap = date.today()
        if cutoff_date:
            try:
                cap = min(cap, date.fromisoformat(cutoff_date[:10]))
            except ValueError:
                raise ValueError(f"Invalid cutoff date: {cutoff_date}")

        missing = self._mandate_missing_dates(entry, self.dl.mandate_last_logged(), cap)

        for d in missing:
            self.create_entry(
                entry["title"], entry["amount"], d.isoformat(),
                entry["categories"], entry["source"], mode=entry["mode"],
                comment=entry["comment"], other_partner=entry["other_partner"],
                mandate_source_id=mandate_page_id, recurring=True,
            )
        return {"created": len(missing)}

    def list_mandates(self) -> dict:
        """Every mandate template, for the management panel."""
        return {"mandates": self.dl.list_mandates()}

    def imported_splitwise_ids(self) -> set:
        """Splitwise expense ids already recorded as expenses."""
        return self.dl.imported_splitwise_ids()

    def create_from_split(
        self,
        name: str,
        amount,
        date_str: str,
        sources: list,
        comment: str,
        splitwise_id=None,
        mode: str = "",
    ) -> str:
        """Create a row from a Splitwise import: Category fixed to
        'Splitwise', 'From Split' ticked, Source = the payer(s), the
        breakdown in Comment, and the Splitwise expense id recorded.
        Returns the page_id."""
        if not name:
            raise ValueError("Name is required")
        if amount is None:
            raise ValueError("Amount is required")
        if not date_str:
            raise ValueError("Date is required")

        fields = self._write_fields(
            name, amount, date_str, ["Splitwise"], "", mode,
            {"from_split": True, "comment": comment or "", "splitwise_id": splitwise_id},
        )
        fields["sources"] = [s for s in (sources or []) if s]
        return self.dl.create_entry(**fields)

    def update_entry(
        self,
        page_id: str,
        name: str,
        amount,
        date_str: str,
        categories: list,
        source: str,
        mode: str = "",
        **extra,
    ) -> None:
        """Updates the row. An empty ``date_str`` leaves its existing date
        untouched. ``extra`` may carry the same optional columns as create."""
        if not name:
            raise ValueError("Name is required")
        if amount is None:
            raise ValueError("Amount is required")
        self.dl.update_entry(
            page_id, **self._write_fields(name, amount, date_str, categories, source, mode, extra)
        )

    def delete_entry(self, page_id: str) -> None:
        self.dl.delete_entry(page_id)

    def get_entry(self, page_id: str) -> dict:
        """A single entry, as listed by ``list_entries``."""
        return self.dl.get_entry(page_id)

    def split_entry(self, page_id: str, splits: list) -> list:
        """Break one mixed-category purchase into several single-category rows
        so per-category analytics stop double-counting (today, a row tagged
        with N categories has its full amount added to every one of them).

        ``splits`` is a list of {"category": str, "amount": number, "name": str?,
        "source"?, "comment"?, "other_partner"?, "add_to_split"?, "from_split"?,
        "split_added"?, "processed"?}. Amounts must add up to the original
        entry's amount. Every field besides category/amount/name is optional
        per split — an omitted one falls back to the original entry's value,
        so a caller that only sends category/amount/name keeps today's
        inherit-everything behavior. Replaces the original with one new row
        per split (never carrying over the Splitwise ID — it can only belong
        to one row) in a single transaction, so a failure leaves the original
        untouched. Returns the new page_ids. Raises ValueError before writing
        anything if the splits don't validate."""
        if not splits or len(splits) < 2:
            raise ValueError("Provide at least two splits")

        original = self.get_entry(page_id)

        total = 0.0
        for s in splits:
            if not (s.get("category") or "").strip():
                raise ValueError("Every split needs a category")
            amount = s.get("amount")
            if amount is None or amount == "":
                raise ValueError("Every split needs an amount")
            amount = float(amount)
            if amount <= 0:
                raise ValueError("Split amounts must be greater than 0")
            total += amount

        if round(total, 2) != round(original["amount"], 2):
            raise ValueError(
                f"Split amounts add up to {total:.2f}, but the original "
                f"expense is {original['amount']:.2f}"
            )

        new_rows = []
        for i, s in enumerate(splits, start=1):
            name = (s.get("name") or "").strip() or original["title"]
            # Ties this row back to the purchase it came from, since the original
            # row is deleted and won't otherwise show up anywhere.
            trace_note = (
                f"Split {i}/{len(splits)} of \"{original['title']}\" — "
                f"total {original['amount']:.2f} on {original['date']}"
            )
            # Every other field is optional per split — omitted means "same as the
            # original" (so old callers that only send category/amount/name still
            # work); anything the caller does send (comment included) overrides it.
            row_comment = s.get("comment", original["comment"])
            comment = f"{trace_note}\n{row_comment}" if row_comment else trace_note
            fields = self._write_fields(
                name, float(s["amount"]), original["date"],
                [s["category"].strip()],
                s.get("source", original["source"]),
                s.get("mode", original.get("mode", "")),
                {
                    "comment": comment,
                    "other_partner": s.get("other_partner", original["other_partner"]),
                    "add_to_split": s.get("add_to_split", original["add_to_split"]),
                    "from_split": s.get("from_split", original["from_split"]),
                    "split_added": s.get("split_added", original["split_added"]),
                    "processed": s.get("processed", original["processed"]),
                },
            )
            # `date` above is the bare day; carry the exact moment (time and
            # UTC offset) over so the splits land on the same instant.
            fields["occurred_at"] = original["datetime"] if len(original["datetime"]) > 10 else None
            new_rows.append(fields)

        return self.dl.replace_entry(page_id, new_rows)

    def mark_split_added(self, page_id: str, value: bool = True) -> None:
        """Tick / untick 'Split Added'."""
        self.dl.update_entry(page_id, split_added=bool(value))

    def finalize_split_push(
        self, page_id: str, my_share, existing_comment: str, note: str
    ) -> None:
        """Run after a row is pushed to Splitwise: drop its Amount to the user's
        own share, prepend ``note`` (the split breakdown) to the Comment, and
        tick 'Split Added' — all in one update."""
        comment = f"{note}\n{existing_comment}" if existing_comment else note
        self.dl.update_entry(
            page_id,
            amount=round(float(my_share or 0), 2),
            split_added=True,
            comment=comment,
        )
