import os
import re
from datetime import date, timedelta

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View


NOTION_API_URL = "https://api.notion.com/v1/databases/{db_id}/query"
NOTION_VERSION = "2022-06-28"

VALID_PERIODS = ("all", "yearly", "monthly", "weekly", "daily")
VALID_GROUPS = ("category", "source")

YEAR_RE  = re.compile(r"^\d{4}$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
WEEK_RE  = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")
DAY_RE   = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def _notion_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _build_date_filter(period, year=None, month=None, week=None, day=None):
    """Returns (notion_filter_dict, range_start, range_end). All None for period='all'."""
    today = date.today()

    if period == "all":
        return None, None, None

    if period == "yearly":
        y = int(year) if year else today.year
        start = date(y, 1, 1)
        end = date(y + 1, 1, 1)

    elif period == "monthly":
        if month:
            year, m = int(month[:4]), int(month[5:])
            start = date(year, m, 1)
        else:
            start = today.replace(day=1)
        end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)

    elif period == "weekly":
        if week:
            year, week_num = int(week[:4]), int(week[6:])
            start = date.fromisocalendar(year, week_num, 1)
        else:
            start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)

    elif period == "daily":
        start = date.fromisoformat(day) if day else today
        end = start + timedelta(days=1)

    notion_filter = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start.isoformat()}},
            {"property": "Date", "date": {"before": end.isoformat()}},
        ]
    }
    return notion_filter, start, end - timedelta(days=1)


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
            return JsonResponse(
                {"error": "Invalid year format. Use YYYY (e.g. 2026)"}, status=400
            )

        if month and not MONTH_RE.match(month):
            return JsonResponse(
                {"error": "Invalid month format. Use YYYY-MM (e.g. 2026-03)"}, status=400
            )

        if week and not WEEK_RE.match(week):
            return JsonResponse(
                {"error": "Invalid week format. Use YYYY-Www (e.g. 2026-W19)"}, status=400
            )

        if day and not DAY_RE.match(day):
            return JsonResponse(
                {"error": "Invalid day format. Use YYYY-MM-DD (e.g. 2026-05-10)"}, status=400
            )

        try:
            notion_filter, range_start, range_end = _build_date_filter(
                period,
                year=year or None,
                month=month or None,
                week=week or None,
                day=day or None,
            )
        except ValueError:
            return JsonResponse({"error": "Invalid date value."}, status=400)

        try:
            rows = _fetch_all_rows(token, db_id, notion_filter)
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        group_totals: dict[str, float] = {}
        grand_total = 0.0

        for row in rows:
            props = row.get("properties", {})
            amount = (props.get("Amount") or {}).get("number") or 0.0
            grand_total += amount

            if group_by:
                for g in _extract_groups(props, group_by):
                    group_totals[g] = group_totals.get(g, 0.0) + amount

        response: dict = {"period": period, "grand_total": round(grand_total, 2)}

        if period == "yearly":
            response["year"] = year if year else str(date.today().year)
        elif period == "monthly":
            response["month"] = month if month else date.today().strftime("%Y-%m")
        elif period == "weekly":
            response["week_start"] = range_start.isoformat()
            response["week_end"] = range_end.isoformat()
        elif period == "daily":
            response["date"] = range_start.isoformat()

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

        try:
            notion_filter, range_start, range_end = _build_date_filter(
                period, year=year or None, month=month or None,
                week=week or None, day=day or None,
            )
        except ValueError:
            return JsonResponse({"error": "Invalid date value."}, status=400)

        try:
            rows = _fetch_all_rows(token, db_id, notion_filter)
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        labels, values = _build_timeseries(period, year, rows, range_start, range_end)
        return JsonResponse({"labels": labels, "values": values, "period": period})


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

        try:
            notion_filter, range_start, range_end = _build_date_filter(
                period, year=year or None, month=month or None,
                week=week or None, day=day or None,
            )
        except ValueError:
            return JsonResponse({"error": "Invalid date value."}, status=400)

        try:
            rows = _fetch_all_rows(token, db_id, notion_filter)
        except requests.HTTPError as exc:
            return JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

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
            "trend":       {"labels": trend_labels, "values": trend_values},
            "display":     _build_display(
                period, grand_total, group_by, group_totals_for_display,
                display_start, display_end
            ),
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

        if breakdown:
            response["group_by"]  = group_by
            response["breakdown"] = breakdown

        return JsonResponse(response)


class DashboardView(View):
    def get(self, request):
        return render(request, "expenses/dashboard.html")


class ChartsView(View):
    def get(self, request):
        return render(request, "expenses/charts.html")
