import json
import os
import re
import time
from datetime import date, timedelta

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View


NOTION_API_URL = "https://api.notion.com/v1/databases/{db_id}/query"
NOTION_VERSION = "2022-06-28"

VALID_PERIODS = ("all", "yearly", "monthly", "weekly", "daily", "custom")
VALID_GROUPS = ("category", "source")

YEAR_RE  = re.compile(r"^\d{4}$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
WEEK_RE  = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")
DAY_RE   = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")

# In-memory cache: fetch ALL rows once, serve all endpoints from this cache.
_rows_cache: dict = {"rows": None, "ts": 0.0}
CACHE_TTL = 300  # seconds; 0 = always re-fetch


def _notion_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _build_date_filter(period, year=None, month=None, week=None, day=None, start=None, end=None):
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


def _fetch_all_rows(token, db_id, notion_filter):
    url = NOTION_API_URL.format(db_id=db_id)
    payload = {}
    if notion_filter:
        payload["filter"] = notion_filter

    rows = []
    has_more = True

    while has_more:
        resp = requests.post(url, headers=_notion_headers(token), json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        if has_more:
            payload["start_cursor"] = data["next_cursor"]

    return rows


def _get_all_rows_cached(token: str, db_id: str, force: bool = False):
    """Fetch ALL expense rows once, cached for CACHE_TTL seconds.

    Returns (rows, cache_ts, from_cache).
    Pass force=True to bypass cache and re-fetch from Notion.
    """
    now = time.time()
    if (
        not force
        and _rows_cache["rows"] is not None
        and (now - _rows_cache["ts"]) < CACHE_TTL
    ):
        return _rows_cache["rows"], _rows_cache["ts"], True
    rows = _fetch_all_rows(token, db_id, None)
    _rows_cache["rows"] = rows
    _rows_cache["ts"] = time.time()
    return rows, _rows_cache["ts"], False


def _filter_rows_by_date(rows: list, range_start, range_end) -> list:
    """Filter cached rows to [range_start, range_end] inclusive. Returns all rows if range_start is None."""
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


def _build_display(period, grand_total, group_by, group_totals, range_start, range_end):
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


def _extract_groups(props, group_by):
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


class ExpensesSummaryView(View):
    def get(self, request):
        token = os.environ.get("NOTION_TOKEN")
        db_id = os.environ.get("NOTION_EXPENSES_DB_ID")

        if not token or not db_id:
            return JsonResponse(
                {"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"}, status=500
            )

        period = request.GET.get("period", "all")
        group_by = request.GET.get("group_by", "")
        year = request.GET.get("year", "")
        month = request.GET.get("month", "")
        week = request.GET.get("week", "")
        day = request.GET.get("day", "")
        start = request.GET.get("start", "")
        end = request.GET.get("end", "")
        force = request.GET.get("force", "") in ("1", "true")

        if period not in VALID_PERIODS:
            return JsonResponse(
                {"error": f"Invalid period '{period}'. Valid options: {', '.join(VALID_PERIODS)}"},
                status=400,
            )

        if group_by and group_by not in VALID_GROUPS:
            return JsonResponse(
                {"error": f"Invalid group_by '{group_by}'. Valid options: {', '.join(VALID_GROUPS)}"},
                status=400,
            )

        if year and not YEAR_RE.match(year):
            return JsonResponse({"error": "Invalid year format. Use YYYY (e.g. 2026)"}, status=400)
        if month and not MONTH_RE.match(month):
            return JsonResponse({"error": "Invalid month format. Use YYYY-MM (e.g. 2026-03)"}, status=400)
        if week and not WEEK_RE.match(week):
            return JsonResponse({"error": "Invalid week format. Use YYYY-Www (e.g. 2026-W19)"}, status=400)
        if day and not DAY_RE.match(day):
            return JsonResponse({"error": "Invalid day format. Use YYYY-MM-DD (e.g. 2026-05-10)"}, status=400)
        if period == "custom":
            if not start or not end:
                return JsonResponse({"error": "Custom period requires both start and end"}, status=400)
            if not DAY_RE.match(start):
                return JsonResponse({"error": "Invalid start date. Use YYYY-MM-DD"}, status=400)
            if not DAY_RE.match(end):
                return JsonResponse({"error": "Invalid end date. Use YYYY-MM-DD"}, status=400)
            if start > end:
                return JsonResponse({"error": "start must be on or before end"}, status=400)

        try:
            notion_filter, range_start, range_end = _build_date_filter(
                period,
                year=year or None,
                month=month or None,
                week=week or None,
                day=day or None,
                start=start or None,
                end=end or None,
            )
        except ValueError:
            return JsonResponse({"error": "Invalid date value."}, status=400)

        try:
            all_rows, cache_ts, from_cache = _get_all_rows_cached(token, db_id, force=force)
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        rows = _filter_rows_by_date(all_rows, range_start, range_end)

        group_totals: dict[str, float] = {}
        grand_total = 0.0

        for row in rows:
            props = row.get("properties", {})
            amount = (props.get("Amount") or {}).get("number") or 0.0
            grand_total += amount

            if group_by:
                for g in _extract_groups(props, group_by):
                    group_totals[g] = group_totals.get(g, 0.0) + amount

        response: dict = {
            "period": period,
            "grand_total": round(grand_total, 2),
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "total_rows": len(all_rows),
        }

        if period == "yearly":
            response["year"] = year if year else str(date.today().year)
        elif period == "monthly":
            response["month"] = month if month else date.today().strftime("%Y-%m")
        elif period == "weekly":
            response["week_start"] = range_start.isoformat()
            response["week_end"] = range_end.isoformat()
        elif period == "daily":
            response["date"] = range_start.isoformat()
        elif period == "custom":
            response["start"] = range_start.isoformat()
            response["end"] = range_end.isoformat()

        if group_by:
            response["group_by"] = group_by
            response["summary"] = [
                {"group": g, "total": round(t, 2)}
                for g, t in sorted(group_totals.items())
            ]

        display_start = range_start or date.today()
        display_end = range_end or date.today()
        response["display"] = _build_display(
            period, round(grand_total, 2), group_by, group_totals, display_start, display_end
        )

        return JsonResponse(response)


def _build_timeseries(period, year, rows, range_start, range_end):
    """Return (labels, values) lists bucketed by the appropriate time unit."""

    def row_date(row):
        return (((row.get("properties", {}).get("Date") or {}).get("date") or {}).get("start") or "")[:10]

    def row_amount(row):
        return (row.get("properties", {}).get("Amount") or {}).get("number") or 0.0

    if period == "daily":
        return [range_start.strftime("%d %b %Y")], [round(sum(row_amount(r) for r in rows), 2)]

    if period in ("monthly", "weekly"):
        buckets: dict[str, float] = {}
        d = range_start
        while d <= range_end:
            buckets[d.isoformat()] = 0.0
            d += timedelta(days=1)
        for row in rows:
            k = row_date(row)
            if k in buckets:
                buckets[k] = round(buckets[k] + row_amount(row), 2)
        fmt = "%a %d" if period == "weekly" else "%-d"
        return (
            [date.fromisoformat(k).strftime(fmt) for k in sorted(buckets)],
            [buckets[k] for k in sorted(buckets)],
        )

    if period == "yearly":
        y = int(year) if year else date.today().year
        buckets = {f"{y}-{m:02d}": 0.0 for m in range(1, 13)}
        for row in rows:
            k = row_date(row)[:7]
            if k in buckets:
                buckets[k] = round(buckets[k] + row_amount(row), 2)
        return (
            [date(int(k[:4]), int(k[5:]), 1).strftime("%b") for k in sorted(buckets)],
            [buckets[k] for k in sorted(buckets)],
        )

    if period == "custom":
        delta = (range_end - range_start).days
        if delta <= 60:
            buckets: dict[str, float] = {}
            d = range_start
            while d <= range_end:
                buckets[d.isoformat()] = 0.0
                d += timedelta(days=1)
            for row in rows:
                k = row_date(row)
                if k in buckets:
                    buckets[k] = round(buckets[k] + row_amount(row), 2)
            return (
                [date.fromisoformat(k).strftime("%-d %b") for k in sorted(buckets)],
                [buckets[k] for k in sorted(buckets)],
            )
        buckets2: dict[str, float] = {}
        d = range_start
        while d <= range_end:
            k = d.strftime("%Y-%m")
            buckets2.setdefault(k, 0.0)
            d += timedelta(days=1)
        for row in rows:
            k = row_date(row)[:7]
            if k in buckets2:
                buckets2[k] = round(buckets2[k] + row_amount(row), 2)
        sorted_keys2 = sorted(buckets2)
        return (
            [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in sorted_keys2],
            [buckets2[k] for k in sorted_keys2],
        )

    # all — dynamic month buckets from data
    buckets = {}
    for row in rows:
        k = row_date(row)[:7]
        if len(k) == 7:
            buckets[k] = round(buckets.get(k, 0.0) + row_amount(row), 2)
    sorted_keys = sorted(buckets)
    return (
        [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in sorted_keys],
        [buckets[k] for k in sorted_keys],
    )


class ExpensesTimeseriesView(View):
    def get(self, request):
        token = os.environ.get("NOTION_TOKEN")
        db_id = os.environ.get("NOTION_EXPENSES_DB_ID")

        if not token or not db_id:
            return JsonResponse(
                {"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"}, status=500
            )

        period = request.GET.get("period", "monthly")
        year   = request.GET.get("year", "")
        month  = request.GET.get("month", "")
        week   = request.GET.get("week", "")
        day    = request.GET.get("day", "")
        start  = request.GET.get("start", "")
        end    = request.GET.get("end", "")
        force  = request.GET.get("force", "") in ("1", "true")

        if period not in VALID_PERIODS:
            return JsonResponse({"error": f"Invalid period. Valid: {', '.join(VALID_PERIODS)}"}, status=400)
        if year  and not YEAR_RE.match(year):
            return JsonResponse({"error": "Invalid year. Use YYYY"}, status=400)
        if month and not MONTH_RE.match(month):
            return JsonResponse({"error": "Invalid month. Use YYYY-MM"}, status=400)
        if week  and not WEEK_RE.match(week):
            return JsonResponse({"error": "Invalid week. Use YYYY-Www"}, status=400)
        if day   and not DAY_RE.match(day):
            return JsonResponse({"error": "Invalid day. Use YYYY-MM-DD"}, status=400)
        if period == "custom":
            if not start or not end:
                return JsonResponse({"error": "Custom period requires both start and end"}, status=400)
            if not DAY_RE.match(start):
                return JsonResponse({"error": "Invalid start date. Use YYYY-MM-DD"}, status=400)
            if not DAY_RE.match(end):
                return JsonResponse({"error": "Invalid end date. Use YYYY-MM-DD"}, status=400)
            if start > end:
                return JsonResponse({"error": "start must be on or before end"}, status=400)

        try:
            notion_filter, range_start, range_end = _build_date_filter(
                period, year=year or None, month=month or None,
                week=week or None, day=day or None,
                start=start or None, end=end or None,
            )
        except ValueError:
            return JsonResponse({"error": "Invalid date value."}, status=400)

        try:
            all_rows, cache_ts, from_cache = _get_all_rows_cached(token, db_id, force=force)
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        rows = _filter_rows_by_date(all_rows, range_start, range_end)
        labels, values = _build_timeseries(period, year, rows, range_start, range_end)
        return JsonResponse({
            "labels": labels,
            "values": values,
            "period": period,
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "total_rows": len(all_rows),
        })


class ExpensesChartView(View):
    """Single endpoint that returns all chart data (trend + breakdown) in one response."""

    def get(self, request):
        token = os.environ.get("NOTION_TOKEN")
        db_id = os.environ.get("NOTION_EXPENSES_DB_ID")

        if not token or not db_id:
            return JsonResponse(
                {"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"}, status=500
            )

        period   = request.GET.get("period", "monthly")
        group_by = request.GET.get("group_by", "")
        year     = request.GET.get("year", "")
        month    = request.GET.get("month", "")
        week     = request.GET.get("week", "")
        day      = request.GET.get("day", "")
        start    = request.GET.get("start", "")
        end      = request.GET.get("end", "")
        force    = request.GET.get("force", "") in ("1", "true")

        if period not in VALID_PERIODS:
            return JsonResponse({"error": f"Invalid period. Valid: {', '.join(VALID_PERIODS)}"}, status=400)
        if group_by and group_by not in VALID_GROUPS:
            return JsonResponse({"error": f"Invalid group_by. Valid: {', '.join(VALID_GROUPS)}"}, status=400)
        if year  and not YEAR_RE.match(year):
            return JsonResponse({"error": "Invalid year. Use YYYY"}, status=400)
        if month and not MONTH_RE.match(month):
            return JsonResponse({"error": "Invalid month. Use YYYY-MM"}, status=400)
        if week  and not WEEK_RE.match(week):
            return JsonResponse({"error": "Invalid week. Use YYYY-Www"}, status=400)
        if day   and not DAY_RE.match(day):
            return JsonResponse({"error": "Invalid day. Use YYYY-MM-DD"}, status=400)
        if period == "custom":
            if not start or not end:
                return JsonResponse({"error": "Custom period requires both start and end"}, status=400)
            if not DAY_RE.match(start):
                return JsonResponse({"error": "Invalid start date. Use YYYY-MM-DD"}, status=400)
            if not DAY_RE.match(end):
                return JsonResponse({"error": "Invalid end date. Use YYYY-MM-DD"}, status=400)
            if start > end:
                return JsonResponse({"error": "start must be on or before end"}, status=400)

        try:
            notion_filter, range_start, range_end = _build_date_filter(
                period, year=year or None, month=month or None,
                week=week or None, day=day or None,
                start=start or None, end=end or None,
            )
        except ValueError:
            return JsonResponse({"error": "Invalid date value."}, status=400)

        try:
            all_rows, cache_ts, from_cache = _get_all_rows_cached(token, db_id, force=force)
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        rows = _filter_rows_by_date(all_rows, range_start, range_end)

        # Grand total
        grand_total = round(sum(
            (row.get("properties", {}).get("Amount") or {}).get("number") or 0.0
            for row in rows
        ), 2)

        # Trend (time-series)
        trend_labels, trend_values = _build_timeseries(period, year, rows, range_start, range_end)

        # Breakdown (category / source)
        breakdown = None
        if group_by:
            group_totals: dict[str, float] = {}
            for row in rows:
                amount = (row.get("properties", {}).get("Amount") or {}).get("number") or 0.0
                for g in _extract_groups(row.get("properties", {}), group_by):
                    group_totals[g] = round(group_totals.get(g, 0.0) + amount, 2)

            sorted_groups = sorted(group_totals.items(), key=lambda x: -x[1])
            breakdown = {
                "labels": [g for g, _ in sorted_groups],
                "values": [t for _, t in sorted_groups],
            }

        display_start = range_start or date.today()
        display_end   = range_end   or date.today()
        group_totals_for_display = (
            dict(zip(breakdown["labels"], breakdown["values"])) if breakdown else {}
        )

        response: dict = {
            "period":      period,
            "grand_total": grand_total,
            "entry_count": len(rows),
            "trend":       {"labels": trend_labels, "values": trend_values},
            "display":     _build_display(
                period, grand_total, group_by, group_totals_for_display,
                display_start, display_end
            ),
            "cache_ts":   cache_ts,
            "from_cache": from_cache,
            "total_rows": len(all_rows),
        }

        if period == "yearly":
            response["year"] = year if year else str(date.today().year)
        elif period == "monthly":
            response["month"] = month if month else date.today().strftime("%Y-%m")
        elif period == "weekly":
            response["week_start"] = range_start.isoformat()
            response["week_end"]   = range_end.isoformat()
        elif period == "daily":
            response["date"] = range_start.isoformat()
        elif period == "custom":
            response["start"] = range_start.isoformat()
            response["end"]   = range_end.isoformat()

        if breakdown:
            response["group_by"]  = group_by
            response["breakdown"] = breakdown

        return JsonResponse(response)


def _build_category_timeseries(period, year, rows, range_start, range_end):
    """Single-pass builder: returns (labels, overall_values, category_series).
    category_series = [{"name", "values": [...], "total"}, ...] sorted by total desc.
    All category arrays are aligned to the same labels list.
    """
    today = date.today()

    def _rdate(row):
        return (((row.get("properties", {}).get("Date") or {}).get("date") or {}).get("start") or "")[:10]

    def _ramount(row):
        return (row.get("properties", {}).get("Amount") or {}).get("number") or 0.0

    def _rcats(row):
        props = row.get("properties", {})
        cats = [opt["name"] for opt in (props.get("Category") or {}).get("multi_select", [])]
        return cats or ["Uncategorized"]

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
            k = _rdate(row)[:7]
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
        d_str = _rdate(row)
        if not d_str:
            continue
        k = key_fn(d_str)
        if k not in bucket_set:
            continue
        amount = _ramount(row)
        overall[k] = round(overall[k] + amount, 2)
        for cat in _rcats(row):
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


class ExpensesCategoryTimeseriesView(View):
    def get(self, request):
        token = os.environ.get("NOTION_TOKEN")
        db_id = os.environ.get("NOTION_EXPENSES_DB_ID")
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"}, status=500)

        period = request.GET.get("period", "monthly")
        year   = request.GET.get("year", "")
        month  = request.GET.get("month", "")
        week   = request.GET.get("week", "")
        day    = request.GET.get("day", "")
        start  = request.GET.get("start", "")
        end    = request.GET.get("end", "")
        force  = request.GET.get("force", "") in ("1", "true")

        if period not in VALID_PERIODS:
            return JsonResponse({"error": "Invalid period."}, status=400)

        try:
            notion_filter, range_start, range_end = _build_date_filter(
                period, year=year or None, month=month or None,
                week=week or None, day=day or None,
                start=start or None, end=end or None,
            )
        except ValueError:
            return JsonResponse({"error": "Invalid date value."}, status=400)

        try:
            all_rows, cache_ts, from_cache = _get_all_rows_cached(token, db_id, force=force)
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        rows = _filter_rows_by_date(all_rows, range_start, range_end)
        labels, overall_values, category_series = _build_category_timeseries(
            period, year, rows, range_start, range_end
        )

        return JsonResponse({
            "period": period,
            "labels": labels,
            "overall": overall_values,
            "by_category": category_series,
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "total_rows": len(all_rows),
        })


def _extract_title(props):
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


def _row_to_entry(row):
    props = row.get("properties", {})
    amount = (props.get("Amount") or {}).get("number") or 0.0
    cats = [opt["name"] for opt in (props.get("Category") or {}).get("multi_select", [])]
    src_prop = props.get("Source") or {}
    if src_prop.get("select"):
        src = src_prop["select"]["name"]
    else:
        srcs = [opt["name"] for opt in src_prop.get("multi_select", [])]
        src = srcs[0] if srcs else ""
    date_val = ((props.get("Date") or {}).get("date") or {}).get("start", "")[:10]
    return {
        "page_id": row.get("id", ""),
        "title": _extract_title(props),
        "amount": round(amount, 2),
        "date": date_val,
        "categories": cats,
        "source": src,
    }


def _detect_title_prop(rows):
    """Return the name of the title-type property from the first available row."""
    for row in rows:
        for key, val in row.get("properties", {}).items():
            if isinstance(val, dict) and val.get("type") == "title":
                return key
    return "Name"


def _detect_source_type(rows):
    """Return 'select' or 'multi_select' based on how Source is stored."""
    for row in rows:
        src = (row.get("properties") or {}).get("Source") or {}
        t = src.get("type")
        if t in ("select", "multi_select"):
            return t
    return "select"


def _build_page_properties(name, amount, date_str, categories, source, title_prop, source_type):
    props = {
        title_prop: {"title": [{"text": {"content": name}}]},
        "Amount": {"number": float(amount)},
        "Date": {"date": {"start": date_str}},
        "Category": {"multi_select": [{"name": c} for c in categories]},
    }
    if source_type == "multi_select":
        props["Source"] = {"multi_select": [{"name": source}] if source else []}
    else:
        props["Source"] = {"select": {"name": source} if source else None}
    return props


class ExpensesInsightsView(View):
    def get(self, request):
        token = os.environ.get("NOTION_TOKEN")
        db_id = os.environ.get("NOTION_EXPENSES_DB_ID")
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"}, status=500)

        period = request.GET.get("period", "all")
        year   = request.GET.get("year", "")
        month  = request.GET.get("month", "")
        week   = request.GET.get("week", "")
        day    = request.GET.get("day", "")
        start  = request.GET.get("start", "")
        end    = request.GET.get("end", "")
        force  = request.GET.get("force", "") in ("1", "true")

        if period not in VALID_PERIODS:
            return JsonResponse({"error": f"Invalid period."}, status=400)

        try:
            notion_filter, range_start, range_end = _build_date_filter(
                period, year=year or None, month=month or None,
                week=week or None, day=day or None,
                start=start or None, end=end or None,
            )
        except ValueError:
            return JsonResponse({"error": "Invalid date value."}, status=400)

        try:
            all_rows, cache_ts, from_cache = _get_all_rows_cached(token, db_id, force=force)
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        rows = _filter_rows_by_date(all_rows, range_start, range_end)

        cat_totals: dict[str, dict] = {}
        src_totals: dict[str, dict] = {}
        grand_total = 0.0
        entries = []

        for row in rows:
            e = _row_to_entry(row)
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

        cat_list = sorted(
            [{"name": k, "total": round(v["total"], 2), "count": v["count"],
              "pct": round(v["total"] / grand_total * 100, 1) if grand_total else 0.0}
             for k, v in cat_totals.items()],
            key=lambda x: -x["total"],
        )
        src_list = sorted(
            [{"name": k, "total": round(v["total"], 2), "count": v["count"],
              "pct": round(v["total"] / grand_total * 100, 1) if grand_total else 0.0}
             for k, v in src_totals.items()],
            key=lambda x: -x["total"],
        )
        top_entries = sorted(entries, key=lambda x: -x["amount"])[:10]
        top3_pct = round(sum(c["total"] for c in cat_list[:3]) / grand_total * 100, 1) if grand_total else 0.0

        return JsonResponse({
            "period": period,
            "grand_total": round(grand_total, 2),
            "entry_count": len(rows),
            "by_category": cat_list,
            "by_source": src_list,
            "top_entries": top_entries,
            "concentration": {
                "top1_name": cat_list[0]["name"] if cat_list else "",
                "top1_pct": cat_list[0]["pct"] if cat_list else 0.0,
                "top3_pct": top3_pct,
            },
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "total_rows": len(all_rows),
        })


VALID_SORTS = ("date_desc", "date_asc", "amount_desc", "amount_asc")


class ExpensesListView(View):
    def get(self, request):
        token = os.environ.get("NOTION_TOKEN")
        db_id = os.environ.get("NOTION_EXPENSES_DB_ID")
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"}, status=500)

        period    = request.GET.get("period", "all")
        year      = request.GET.get("year", "")
        month     = request.GET.get("month", "")
        week      = request.GET.get("week", "")
        day       = request.GET.get("day", "")
        start     = request.GET.get("start", "")
        end       = request.GET.get("end", "")
        category  = request.GET.get("category", "")
        source    = request.GET.get("source", "")
        min_amt   = request.GET.get("min_amount", "")
        max_amt   = request.GET.get("max_amount", "")
        sort      = request.GET.get("sort", "date_desc")
        search    = request.GET.get("search", "").strip().lower()
        force     = request.GET.get("force", "") in ("1", "true")

        try:
            page      = max(1, int(request.GET.get("page", 1)))
            page_size = max(1, min(100, int(request.GET.get("page_size", 25))))
        except ValueError:
            return JsonResponse({"error": "Invalid page or page_size."}, status=400)

        if period not in VALID_PERIODS:
            return JsonResponse({"error": "Invalid period."}, status=400)
        if sort not in VALID_SORTS:
            return JsonResponse({"error": f"Invalid sort. Valid: {', '.join(VALID_SORTS)}"}, status=400)

        try:
            notion_filter, range_start, range_end = _build_date_filter(
                period, year=year or None, month=month or None,
                week=week or None, day=day or None,
                start=start or None, end=end or None,
            )
        except ValueError:
            return JsonResponse({"error": "Invalid date value."}, status=400)

        try:
            all_rows, cache_ts, from_cache = _get_all_rows_cached(token, db_id, force=force)
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        rows = _filter_rows_by_date(all_rows, range_start, range_end)

        filter_cats = [c.strip() for c in category.split(",") if c.strip()] if category else []
        min_amount  = float(min_amt) if min_amt else None
        max_amount  = float(max_amt) if max_amt else None

        entries = []
        for row in rows:
            e = _row_to_entry(row)

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

            entries.append(e)

        if sort == "date_desc":
            entries.sort(key=lambda x: x["date"] or "", reverse=True)
        elif sort == "date_asc":
            entries.sort(key=lambda x: x["date"] or "")
        elif sort == "amount_desc":
            entries.sort(key=lambda x: -x["amount"])
        elif sort == "amount_asc":
            entries.sort(key=lambda x: x["amount"])

        total_count = len(entries)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        page = min(page, total_pages)
        start_idx = (page - 1) * page_size

        return JsonResponse({
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "entries": entries[start_idx: start_idx + page_size],
            "cache_ts": cache_ts,
            "from_cache": from_cache,
            "total_rows": len(all_rows),
        })


class ExpensesHeatmapView(View):
    """Returns daily spend totals for a date range, used to render the spend heatmap."""

    def get(self, request):
        token = os.environ.get("NOTION_TOKEN")
        db_id = os.environ.get("NOTION_EXPENSES_DB_ID")
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"}, status=500)

        period = request.GET.get("period", "monthly")
        year   = request.GET.get("year", "")
        month  = request.GET.get("month", "")
        week   = request.GET.get("week", "")
        day    = request.GET.get("day", "")
        start  = request.GET.get("start", "")
        end    = request.GET.get("end", "")
        force  = request.GET.get("force", "") in ("1", "true")

        if period not in VALID_PERIODS:
            return JsonResponse({"error": "Invalid period."}, status=400)

        try:
            _, range_start, range_end = _build_date_filter(
                period, year=year or None, month=month or None,
                week=week or None, day=day or None,
                start=start or None, end=end or None,
            )
        except ValueError:
            return JsonResponse({"error": "Invalid date value."}, status=400)

        try:
            all_rows, cache_ts, from_cache = _get_all_rows_cached(token, db_id, force=force)
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        rows = _filter_rows_by_date(all_rows, range_start, range_end)

        daily: dict[str, float] = {}
        for row in rows:
            d_str = (
                ((row.get("properties", {}).get("Date") or {}).get("date") or {}).get("start") or ""
            )[:10]
            if not d_str:
                continue
            amount = (row.get("properties", {}).get("Amount") or {}).get("number") or 0.0
            daily[d_str] = round(daily.get(d_str, 0.0) + amount, 2)

        # For period=all, derive actual date range from the data itself
        if range_start is None and daily:
            dates = sorted(daily.keys())
            range_start = date.fromisoformat(dates[0])
            range_end   = date.fromisoformat(dates[-1])

        return JsonResponse({
            "daily": daily,
            "range_start": range_start.isoformat() if range_start else None,
            "range_end":   range_end.isoformat()   if range_end   else None,
            "cache_ts":    cache_ts,
            "from_cache":  from_cache,
        })


class ExpensesCreateView(View):
    def post(self, request):
        token = os.environ.get("NOTION_TOKEN")
        db_id = os.environ.get("NOTION_EXPENSES_DB_ID")
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"}, status=500)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        name       = (data.get("name") or "").strip()
        amount     = data.get("amount")
        date_str   = (data.get("date") or "").strip()
        categories = [c for c in (data.get("categories") or []) if c]
        source     = (data.get("source") or "").strip()

        if not name:
            return JsonResponse({"error": "Name is required"}, status=400)
        if amount is None:
            return JsonResponse({"error": "Amount is required"}, status=400)
        if not date_str:
            return JsonResponse({"error": "Date is required"}, status=400)

        cached_rows = _rows_cache.get("rows") or []
        title_prop  = _detect_title_prop(cached_rows)
        source_type = _detect_source_type(cached_rows)

        properties = _build_page_properties(name, amount, date_str, categories, source, title_prop, source_type)

        try:
            resp = requests.post(
                "https://api.notion.com/v1/pages",
                headers=_notion_headers(token),
                json={"parent": {"database_id": db_id}, "properties": properties},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}", "detail": exc.response.text if exc.response else ""}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        _rows_cache["ts"] = 0.0  # bust cache
        return JsonResponse({"ok": True, "page_id": resp.json().get("id")}, status=201)


class ExpensesUpdateView(View):
    def patch(self, request, page_id):
        token = os.environ.get("NOTION_TOKEN")
        if not token:
            return JsonResponse({"error": "NOTION_TOKEN must be set"}, status=500)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        name       = (data.get("name") or "").strip()
        amount     = data.get("amount")
        date_str   = (data.get("date") or "").strip()
        categories = [c for c in (data.get("categories") or []) if c]
        source     = (data.get("source") or "").strip()

        if not name:
            return JsonResponse({"error": "Name is required"}, status=400)
        if amount is None:
            return JsonResponse({"error": "Amount is required"}, status=400)
        if not date_str:
            return JsonResponse({"error": "Date is required"}, status=400)

        cached_rows = _rows_cache.get("rows") or []
        title_prop  = _detect_title_prop(cached_rows)
        source_type = _detect_source_type(cached_rows)

        properties = _build_page_properties(name, amount, date_str, categories, source, title_prop, source_type)

        try:
            resp = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=_notion_headers(token),
                json={"properties": properties},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}", "detail": exc.response.text if exc.response else ""}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        _rows_cache["ts"] = 0.0  # bust cache
        return JsonResponse({"ok": True})


class DashboardView(View):
    def get(self, request):
        return render(request, "expenses/dashboard.html")


class ChartsView(View):
    def get(self, request):
        return render(request, "expenses/charts.html")
