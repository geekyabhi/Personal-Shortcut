import json
import re
from datetime import date, datetime, timedelta, timezone

from .data_layer import ExpensesDataLayer


class ExpensesService:
    VALID_PERIODS = ("all", "yearly", "monthly", "weekly", "daily", "custom")
    VALID_GROUPS = ("category", "source")
    VALID_SORTS = ("date_desc", "date_asc", "amount_desc", "amount_asc")

    YEAR_RE  = re.compile(r"^\d{4}$")
    MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    WEEK_RE  = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")
    DAY_RE   = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")

    def __init__(self, data_layer: ExpensesDataLayer):
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
        """Returns (notion_filter_dict, range_start, range_end). All None for period='all'."""
        today = date.today()

        if period == "all":
            return None, None, None

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

        notion_filter = {
            "and": [
                {"property": "Date", "date": {"on_or_after": s.isoformat()}},
                {"property": "Date", "date": {"before": e.isoformat()}},
            ]
        }
        return notion_filter, s, e - timedelta(days=1)

    def _filter_by_date(self, rows: list, range_start, range_end) -> list:
        """Filter rows to [range_start, range_end] inclusive. Returns all if range_start is None."""
        if range_start is None:
            return rows
        result = []
        for row in rows:
            d_str = (
                ((row.get("properties", {}).get("Date") or {}).get("date") or {}).get("start") or ""
            )[:10]
            if not d_str:
                continue
            try:
                d = date.fromisoformat(d_str)
            except ValueError:
                continue
            if range_start <= d <= range_end:
                result.append(row)
        return result

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

    def _filter_by_rules(self, rows: list, filters_raw: str) -> list:
        """Apply the client-side filter builder's rule list (JSON) to raw Notion
        rows. Unknown / half-built rules are ignored; all remaining rules are
        ANDed. Returns ``rows`` unchanged when there's nothing to apply."""
        if not filters_raw:
            return rows
        try:
            rules = json.loads(filters_raw)
        except (ValueError, TypeError):
            return rows
        rules = [
            r for r in rules
            if isinstance(r, dict) and r.get("field") and r.get("op") and self._rule_complete(r)
        ]
        if not rules:
            return rows
        return [
            row for row in rows
            if all(self._rule_match(self._row_to_entry(row), r) for r in rules)
        ]

    def _row_date(self, row) -> str:
        return (
            ((row.get("properties", {}).get("Date") or {}).get("date") or {}).get("start") or ""
        )[:10]

    def _row_amount(self, row) -> float:
        return (row.get("properties", {}).get("Amount") or {}).get("number") or 0.0

    def _row_categories(self, row) -> list:
        props = row.get("properties", {})
        cats = [opt["name"] for opt in (props.get("Category") or {}).get("multi_select", [])]
        return cats or ["Uncategorized"]

    def _row_source(self, row) -> str:
        src_prop = (row.get("properties", {}).get("Source") or {})
        if src_prop.get("select"):
            return src_prop["select"]["name"]
        srcs = [opt["name"] for opt in src_prop.get("multi_select", [])]
        return srcs[0] if srcs else ""

    def _extract_title(self, props) -> str:
        for key in ("Name", "Title"):
            prop = props.get(key, {})
            if prop and prop.get("title"):
                text = "".join(t.get("plain_text", "") for t in prop["title"]).strip()
                if text:
                    return text
        for prop in props.values():
            if isinstance(prop, dict) and prop.get("type") == "title":
                parts = prop.get("title") or []
                text = "".join(t.get("plain_text", "") for t in parts).strip()
                if text:
                    return text
        return "—"

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

    def _row_to_entry(self, row) -> dict:
        props = row.get("properties", {})
        amount = (props.get("Amount") or {}).get("number") or 0.0
        cats = [opt["name"] for opt in (props.get("Category") or {}).get("multi_select", [])]
        src_prop = props.get("Source") or {}
        if src_prop.get("select"):
            src = src_prop["select"]["name"]
        else:
            srcs = [opt["name"] for opt in src_prop.get("multi_select", [])]
            src = srcs[0] if srcs else ""
        # "Mode" (how the money moved — UPI / Card / Cash …). Notion type is
        # multi_select, but the app treats it as a single value like Source.
        mode_prop = props.get("Mode") or {}
        if mode_prop.get("select"):
            mode = mode_prop["select"]["name"]
        else:
            modes = [opt["name"] for opt in mode_prop.get("multi_select", [])]
            mode = modes[0] if modes else ""
        # Notion's Date "start" is either a bare date ("2026-07-01") or a full
        # datetime ("2026-07-01T14:23:00.000+05:30"). Keep both: `datetime` is the
        # raw value (has the time when Notion recorded one), `date` stays the
        # day-only form everything else in the app already relies on.
        date_start = ((props.get("Date") or {}).get("date") or {}).get("start", "")
        date_val = date_start[:10]
        comment = "".join(
            t.get("plain_text", "") for t in (props.get("Comment") or {}).get("rich_text", [])
        ).strip()
        other_partner = "".join(
            t.get("plain_text", "") for t in (props.get("Other Partner") or {}).get("rich_text", [])
        ).strip()
        return {
            "page_id": row.get("id", ""),
            "title": self._extract_title(props),
            "amount": round(amount, 2),
            "date": date_val,
            "datetime": date_start,
            "categories": cats,
            "source": src,
            "mode": mode,
            "comment": comment,
            "other_partner": other_partner,
            "add_to_split": bool((props.get("Add to Split") or {}).get("checkbox")),
            "from_split": bool((props.get("From Split") or {}).get("checkbox")),
            "split_added": bool((props.get("Split Added") or {}).get("checkbox")),
            "processed": bool((props.get("Processed") or {}).get("checkbox")),
            "splitwise_id": (props.get("Splitwise ID") or {}).get("number"),
        }

    def _detect_title_prop(self, rows) -> str:
        for row in rows:
            for key, val in row.get("properties", {}).items():
                if isinstance(val, dict) and val.get("type") == "title":
                    return key
        return "Name"

    def _detect_source_type(self, rows) -> str:
        for row in rows:
            src = (row.get("properties") or {}).get("Source") or {}
            t = src.get("type")
            if t in ("select", "multi_select"):
                return t
        return "select"

    def _detect_prop_type(self, rows, prop_name: str, default: str = "multi_select") -> str:
        for row in rows:
            p = (row.get("properties") or {}).get(prop_name) or {}
            t = p.get("type")
            if t in ("select", "multi_select"):
                return t
        return default

    def _build_page_properties(
        self,
        name: str,
        amount,
        date_str: str,
        categories: list,
        source: str,
        title_prop: str,
        source_type: str,
        mode: str = "",
        mode_type: str = "multi_select",
    ) -> dict:
        props = {
            title_prop: {"title": [{"text": {"content": name}}]},
            "Amount": {"number": float(amount)},
            "Category": {"multi_select": [{"name": c} for c in categories]},
        }
        # Only touch Date when a value is given — an empty date_str leaves the
        # existing Notion date (time + timezone) untouched on update.
        if date_str:
            props["Date"] = {"date": {"start": date_str}}
        if source_type == "multi_select":
            props["Source"] = {"multi_select": [{"name": source}] if source else []}
        else:
            props["Source"] = {"select": {"name": source} if source else None}
        if mode_type == "select":
            props["Mode"] = {"select": {"name": mode} if mode else None}
        else:
            props["Mode"] = {"multi_select": [{"name": mode}] if mode else []}
        return props

    def _extract_groups(self, props, group_by) -> list:
        if group_by == "category":
            values = [opt["name"] for opt in (props.get("Category") or {}).get("multi_select", [])]
            return values or ["Uncategorized"]
        if group_by == "source":
            prop = props.get("Source") or {}
            if prop.get("select"):
                return [prop["select"]["name"]]
            values = [opt["name"] for opt in prop.get("multi_select", [])]
            return values or ["Unknown"]
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

    def _build_timeseries(self, period, year, rows, range_start, range_end):
        """Return (labels, values) lists bucketed by the appropriate time unit."""
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

    def _build_category_timeseries(self, period, year, rows, range_start, range_end):
        """Returns (labels, overall_values, category_series).
        category_series = [{"name", "values": [...], "total"}, ...] sorted by total desc.
        All category arrays are aligned to the same labels list.
        """
        today = date.today()

        # Build bucket keys + key extractor + label formatter
        if period == "daily":
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
        notion_filter, range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self.dl.get_cached_rows(
            force=force, partial=partial
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))

        group_totals: dict[str, float] = {}
        grand_total = 0.0

        for row in rows:
            props = row.get("properties", {})
            amount = (props.get("Amount") or {}).get("number") or 0.0
            grand_total += amount
            if group_by:
                for g in self._extract_groups(props, group_by):
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
        notion_filter, range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self.dl.get_cached_rows(
            force=force, partial=partial
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
    ) -> dict:
        self._validate_period(period, year, month, week, day, start, end, group_by=group_by)
        notion_filter, range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self.dl.get_cached_rows(
            force=force, partial=partial
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))

        grand_total = round(sum(
            (row.get("properties", {}).get("Amount") or {}).get("number") or 0.0
            for row in rows
        ), 2)

        trend_labels, trend_values = self._build_timeseries(period, year, rows, range_start, range_end)

        breakdown = None
        if group_by:
            group_totals: dict[str, float] = {}
            for row in rows:
                amount = (row.get("properties", {}).get("Amount") or {}).get("number") or 0.0
                for g in self._extract_groups(row.get("properties", {}), group_by):
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
    ) -> dict:
        self._validate_period(period, year, month, week, day, start, end)
        notion_filter, range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self.dl.get_cached_rows(
            force=force, partial=partial
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))
        labels, overall_values, category_series = self._build_category_timeseries(
            period, year, rows, range_start, range_end
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
        notion_filter, range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self.dl.get_cached_rows(
            force=force, partial=partial
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))

        cat_totals: dict[str, dict] = {}
        src_totals: dict[str, dict] = {}
        modes_seen: set[str] = set()
        grand_total = 0.0
        entries = []

        for row in rows:
            e = self._row_to_entry(row)
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
        notion_filter, range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self.dl.get_cached_rows(
            force=force, partial=partial
        )
        rows = self._filter_by_date(all_rows, range_start, range_end)
        rows = self._filter_by_rules(rows, locals().get("filters", ""))

        filter_cats = [c.strip() for c in category.split(",") if c.strip()] if category else []

        entries = []
        for row in rows:
            e = self._row_to_entry(row)

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
        _, range_start, range_end = self._build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
        all_rows, cache_ts, from_cache, is_partial = self.dl.get_cached_rows(
            force=force, partial=partial
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

    @staticmethod
    def _extra_props(
        comment=None,
        other_partner=None,
        add_to_split=None,
        from_split=None,
        split_added=None,
        processed=None,
        splitwise_id=None,
    ) -> dict:
        """Notion property payloads for the optional columns. A value of
        ``None`` means 'leave this column untouched'."""
        props: dict = {}
        if comment is not None:
            props["Comment"] = {
                "rich_text": [{"text": {"content": comment[:2000]}}] if comment else []
            }
        if other_partner is not None:
            props["Other Partner"] = {
                "rich_text": [{"text": {"content": other_partner[:2000]}}] if other_partner else []
            }
        if add_to_split is not None:
            props["Add to Split"] = {"checkbox": bool(add_to_split)}
        if from_split is not None:
            props["From Split"] = {"checkbox": bool(from_split)}
        if split_added is not None:
            props["Split Added"] = {"checkbox": bool(split_added)}
        if processed is not None:
            props["Processed"] = {"checkbox": bool(processed)}
        if splitwise_id is not None:
            s = str(splitwise_id).strip()
            props["Splitwise ID"] = {"number": int(float(s)) if s else None}
        return props

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
        """Validates fields, creates the Notion page, busts cache. Returns page_id.
        ``extra`` may carry comment / other_partner / add_to_split / from_split /
        split_added / splitwise_id."""
        if not name:
            raise ValueError("Name is required")
        if amount is None:
            raise ValueError("Amount is required")
        if not date_str:
            raise ValueError("Date is required")

        cached_rows, _, _, _ = self.dl.get_cached_rows()
        title_prop = self._detect_title_prop(cached_rows)
        source_type = self._detect_source_type(cached_rows)
        mode_type = self._detect_prop_type(cached_rows, "Mode")
        properties = self._build_page_properties(
            name, amount, date_str, categories, source, title_prop, source_type,
            mode=mode, mode_type=mode_type,
        )
        properties.update(self._extra_props(**extra))
        result = self.dl.create_page(properties)
        self.dl.bust_cache()
        return result.get("id", "")

    SPLITWISE_ID_PROP = "Splitwise ID"

    def imported_splitwise_ids(self):
        """Set of Splitwise expense ids already present in Notion, or None if
        the 'Splitwise ID' column does not exist (dedupe unavailable).

        Uses a narrow filtered query (rows that carry a Splitwise id), not
        the full dataset.
        """
        ids, exists = self.dl.imported_splitwise_ids(self.SPLITWISE_ID_PROP)
        return ids if exists else None

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
        """Create a Notion row from a Splitwise import: Category fixed to
        'Splitwise', 'From Split' ticked, Source = the payer(s), the
        breakdown in Comment, and the Splitwise expense id recorded (if the
        'Splitwise ID' column exists). Returns the page_id."""
        if not name:
            raise ValueError("Name is required")
        if amount is None:
            raise ValueError("Amount is required")
        if not date_str:
            raise ValueError("Date is required")

        cached_rows, _, _, _ = self.dl.get_cached_rows()
        title_prop = self._detect_title_prop(cached_rows)
        source_type = self._detect_source_type(cached_rows)
        mode_type = self._detect_prop_type(cached_rows, "Mode")
        sources = [s for s in (sources or []) if s]

        properties = {
            title_prop: {"title": [{"text": {"content": name}}]},
            "Amount": {"number": float(amount)},
            "Date": {"date": {"start": date_str}},
            "Category": {"multi_select": [{"name": "Splitwise"}]},
            "From Split": {"checkbox": True},
            "Comment": {"rich_text": [{"text": {"content": (comment or "")[:2000]}}]},
        }
        if source_type == "multi_select":
            properties["Source"] = {"multi_select": [{"name": s} for s in sources]}
        else:
            properties["Source"] = {"select": {"name": sources[0]} if sources else None}
        if mode_type == "select":
            properties["Mode"] = {"select": {"name": mode} if mode else None}
        else:
            properties["Mode"] = {"multi_select": [{"name": mode}] if mode else []}

        if splitwise_id is not None:
            _, has_swid = self.dl.imported_splitwise_ids(self.SPLITWISE_ID_PROP)
            if has_swid:
                properties[self.SPLITWISE_ID_PROP] = {"number": int(splitwise_id)}

        result = self.dl.create_page(properties)
        self.dl.bust_cache()
        return result.get("id", "")

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
        """Patches the Notion page, busts cache. An empty ``date_str`` leaves
        the page's existing Date untouched. ``extra`` may carry comment /
        other_partner / add_to_split / from_split / split_added / splitwise_id."""
        if not name:
            raise ValueError("Name is required")
        if amount is None:
            raise ValueError("Amount is required")

        cached_rows, _, _, _ = self.dl.get_cached_rows()
        title_prop = self._detect_title_prop(cached_rows)
        source_type = self._detect_source_type(cached_rows)
        mode_type = self._detect_prop_type(cached_rows, "Mode")
        properties = self._build_page_properties(
            name, amount, date_str, categories, source, title_prop, source_type,
            mode=mode, mode_type=mode_type,
        )
        properties.update(self._extra_props(**extra))
        self.dl.patch_page(page_id, {"properties": properties})
        self.dl.bust_cache()

    def delete_entry(self, page_id: str) -> None:
        """Archives the Notion page and busts cache."""
        self.dl.patch_page(page_id, {"archived": True})
        self.dl.bust_cache()

    def get_entry(self, page_id: str) -> dict:
        """Return a single entry (as `_row_to_entry`) from the cached rows."""
        rows, _, _, _ = self.dl.get_cached_rows()
        for row in rows:
            if row.get("id") == page_id:
                return self._row_to_entry(row)
        raise ValueError("Expense not found")

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
        inherit-everything behavior. Creates one new Notion page per split
        (never carrying over the Splitwise ID — it can only belong to one
        row), then archives the original. Returns the new
        page_ids. Raises ValueError before creating anything if the splits
        don't validate, but a failure partway through creation leaves any
        already-created rows in place and does NOT touch the original."""
        if not splits or len(splits) < 2:
            raise ValueError("Provide at least two splits")

        original = self.get_entry(page_id)

        # `original["date"]` is truncated to YYYY-MM-DD by `_row_to_entry` (that's
        # all the rest of the UI ever needs), which would silently drop the
        # purchase's actual time-of-day/timezone on every split row. Pull the
        # untouched "start" value straight off the raw Notion row instead, so
        # the splits land on the exact same instant as the original.
        raw_rows, _, _, _ = self.dl.get_cached_rows()
        raw_row = next((r for r in raw_rows if r.get("id") == page_id), None)
        if raw_row is None:
            raise ValueError("Expense not found")
        original_date = (
            ((raw_row.get("properties", {}).get("Date") or {}).get("date") or {}).get("start")
            or original["date"]
        )

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

        new_ids = []
        for i, s in enumerate(splits, start=1):
            name = (s.get("name") or "").strip() or original["title"]
            # Ties this row back to the purchase it came from, since the original
            # page is archived and won't otherwise show up anywhere.
            trace_note = (
                f"Split {i}/{len(splits)} of \"{original['title']}\" — "
                f"total {original['amount']:.2f} on {original['date']}"
            )
            # Every other field is optional per split — omitted means "same as the
            # original" (so old callers that only send category/amount/name still
            # work); anything the caller does send (comment included) overrides it.
            row_comment = s.get("comment", original["comment"])
            comment = f"{trace_note}\n{row_comment}" if row_comment else trace_note
            source = s.get("source", original["source"])
            mode = s.get("mode", original.get("mode", ""))
            other_partner = s.get("other_partner", original["other_partner"])
            add_to_split = s.get("add_to_split", original["add_to_split"])
            from_split = s.get("from_split", original["from_split"])
            split_added = s.get("split_added", original["split_added"])
            processed = s.get("processed", original["processed"])
            new_id = self.create_entry(
                name, float(s["amount"]), original_date,
                [s["category"].strip()], source, mode,
                comment=comment, other_partner=other_partner,
                add_to_split=add_to_split, from_split=from_split,
                split_added=split_added, processed=processed,
            )
            new_ids.append(new_id)

        self.delete_entry(page_id)
        return new_ids

    def mark_split_added(self, page_id: str, value: bool = True) -> None:
        """Tick / untick the Notion 'Split Added' checkbox and bust cache."""
        self.dl.patch_page(
            page_id, {"properties": {"Split Added": {"checkbox": value}}}
        )
        self.dl.bust_cache()

    def finalize_split_push(
        self, page_id: str, my_share, existing_comment: str, note: str
    ) -> None:
        """Run after a row is pushed to Splitwise: drop its Amount to the user's
        own share, prepend ``note`` (the split breakdown) to the Comment, and
        tick 'Split Added' — all in one patch, one cache bust."""
        comment = f"{note}\n{existing_comment}" if existing_comment else note
        props = {
            "Amount": {"number": round(float(my_share or 0), 2)},
            "Split Added": {"checkbox": True},
        }
        props.update(self._extra_props(comment=comment))
        self.dl.patch_page(page_id, {"properties": props})
        self.dl.bust_cache()
