import os
import re
from datetime import date, timedelta

import requests
from django.http import JsonResponse
from django.views import View


NOTION_API_URL = "https://api.notion.com/v1/databases/{db_id}/query"
NOTION_VERSION = "2022-06-28"

VALID_PERIODS = ("all", "monthly", "weekly", "daily")
VALID_GROUPS = ("category", "source")

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
WEEK_RE = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")
DAY_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def _notion_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _build_date_filter(period, month=None, week=None, day=None):
    """Returns (notion_filter_dict, range_start, range_end). All None for period='all'."""
    today = date.today()

    if period == "all":
        return None, None, None

    if period == "monthly":
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

        if period == "monthly":
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

        return JsonResponse(response)
