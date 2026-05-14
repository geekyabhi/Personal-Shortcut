import os
import re
import json
from datetime import date, timedelta

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

NOTION_PAGES_URL = "https://api.notion.com/v1/pages"


NOTION_API_URL = "https://api.notion.com/v1/databases/{db_id}/query"
NOTION_VERSION = "2022-06-28"

VALID_PERIODS = ("all", "yearly", "monthly", "weekly", "daily", "custom")

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


def _build_date_filter(period, year=None, month=None, week=None, day=None, start=None, end=None):
    today = date.today()
    if period == "all":
        return None, None, None
    if period == "yearly":
        y = int(year) if year else today.year
        s, e = date(y, 1, 1), date(y + 1, 1, 1)
    elif period == "monthly":
        s = date(int(month[:4]), int(month[5:]), 1) if month else today.replace(day=1)
        e = date(s.year + 1, 1, 1) if s.month == 12 else date(s.year, s.month + 1, 1)
    elif period == "weekly":
        s = date.fromisocalendar(int(week[:4]), int(week[6:]), 1) if week else today - timedelta(days=today.weekday())
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


def _habit_fields(rows):
    if not rows:
        return []
    props = rows[0].get("properties", {})
    return sorted([k for k, v in props.items() if v.get("type") == "checkbox"])


def _row_date(row):
    return (((row.get("properties", {}).get("Date") or {}).get("date") or {}).get("start") or "")[:10]


def _row_score(row):
    return ((row.get("properties", {}).get("Score") or {}).get("formula") or {}).get("number")


def _validate(period, year, month, week, day, start="", end=""):
    if period not in VALID_PERIODS:
        return f"Invalid period '{period}'. Valid: {', '.join(VALID_PERIODS)}"
    if year  and not YEAR_RE.match(year):   return "Invalid year. Use YYYY"
    if month and not MONTH_RE.match(month): return "Invalid month. Use YYYY-MM"
    if week  and not WEEK_RE.match(week):   return "Invalid week. Use YYYY-Www"
    if day   and not DAY_RE.match(day):     return "Invalid day. Use YYYY-MM-DD"
    if period == "custom":
        if not start or not end:            return "Custom period requires both start and end"
        if not DAY_RE.match(start):         return "Invalid start date. Use YYYY-MM-DD"
        if not DAY_RE.match(end):           return "Invalid end date. Use YYYY-MM-DD"
        if start > end:                     return "start must be on or before end"


def _period_meta(period, year, month, week, range_start, range_end):
    if period == "yearly":  return {"year": year or str(date.today().year)}
    if period == "monthly": return {"month": month or date.today().strftime("%Y-%m")}
    if period == "weekly":  return {"week_start": range_start.isoformat(), "week_end": range_end.isoformat()}
    if period == "daily":   return {"date": range_start.isoformat()}
    if period == "custom":  return {"start": range_start.isoformat(), "end": range_end.isoformat()}
    return {}


def _score_trend(period, year, rows, range_start, range_end):
    if period == "daily" or not rows:
        scores = [s for r in rows if (s := _row_score(r)) is not None]
        return {
            "labels": [range_start.strftime("%d %b %Y") if range_start else "-"],
            "values": [round(sum(scores) / len(scores), 1) if scores else None],
        }

    if period in ("monthly", "weekly"):
        buckets: dict[str, list] = {}
        d = range_start
        while d <= range_end:
            buckets[d.isoformat()] = []
            d += timedelta(days=1)
        for row in rows:
            k, s = _row_date(row), _row_score(row)
            if k in buckets and s is not None:
                buckets[k].append(s)
        fmt = "%a %d" if period == "weekly" else "%-d"
        return {
            "labels": [date.fromisoformat(k).strftime(fmt) for k in sorted(buckets)],
            "values": [round(sum(v) / len(v), 1) if v else None for v in [buckets[k] for k in sorted(buckets)]],
        }

    if period == "yearly":
        y = int(year) if year else date.today().year
        buckets = {f"{y}-{m:02d}": [] for m in range(1, 13)}
        for row in rows:
            k, s = _row_date(row)[:7], _row_score(row)
            if k in buckets and s is not None:
                buckets[k].append(s)
        return {
            "labels": [date(int(k[:4]), int(k[5:]), 1).strftime("%b") for k in sorted(buckets)],
            "values": [round(sum(v) / len(v), 1) if v else None for v in [buckets[k] for k in sorted(buckets)]],
        }

    if period == "custom":
        delta = (range_end - range_start).days
        if delta <= 60:
            buckets: dict[str, list] = {}
            d = range_start
            while d <= range_end:
                buckets[d.isoformat()] = []
                d += timedelta(days=1)
            for row in rows:
                k, s = _row_date(row), _row_score(row)
                if k in buckets and s is not None:
                    buckets[k].append(s)
            return {
                "labels": [date.fromisoformat(k).strftime("%-d %b") for k in sorted(buckets)],
                "values": [round(sum(v) / len(v), 1) if v else None for v in [buckets[k] for k in sorted(buckets)]],
            }
        # monthly buckets for longer ranges
        buckets2: dict[str, list] = {}
        d = range_start
        while d <= range_end:
            k = d.strftime("%Y-%m")
            buckets2.setdefault(k, [])
            d += timedelta(days=1)
        for row in rows:
            k, s = _row_date(row)[:7], _row_score(row)
            if k in buckets2 and s is not None:
                buckets2[k].append(s)
        keys2 = sorted(buckets2)
        return {
            "labels": [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in keys2],
            "values": [round(sum(buckets2[k]) / len(buckets2[k]), 1) if buckets2[k] else None for k in keys2],
        }

    # all
    buckets: dict[str, list] = {}
    for row in rows:
        k, s = _row_date(row)[:7], _row_score(row)
        if len(k) == 7 and s is not None:
            buckets.setdefault(k, []).append(s)
    keys = sorted(buckets)
    return {
        "labels": [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in keys],
        "values": [round(sum(buckets[k]) / len(buckets[k]), 1) for k in keys],
    }


def _get_creds():
    return os.environ.get("NOTION_TOKEN"), os.environ.get("NOTION_HABITS_DB_ID")


def _common_fetch(request):
    token, db_id = _get_creds()
    if not token or not db_id:
        return None, None, None, None, None, None, None, \
            JsonResponse({"error": "NOTION_TOKEN and NOTION_HABITS_DB_ID must be set"}, status=500)

    period = request.GET.get("period", "monthly")
    year   = request.GET.get("year", "")
    month  = request.GET.get("month", "")
    week   = request.GET.get("week", "")
    day    = request.GET.get("day", "")
    start  = request.GET.get("start", "")
    end    = request.GET.get("end", "")

    err = _validate(period, year, month, week, day, start, end)
    if err:
        return None, None, None, None, None, None, None, JsonResponse({"error": err}, status=400)

    try:
        notion_filter, range_start, range_end = _build_date_filter(
            period, year=year or None, month=month or None,
            week=week or None, day=day or None,
            start=start or None, end=end or None,
        )
    except ValueError:
        return None, None, None, None, None, None, None, \
            JsonResponse({"error": "Invalid date value."}, status=400)

    try:
        rows = _fetch_all_rows(token, db_id, notion_filter)
    except requests.HTTPError as exc:
        return None, None, None, None, None, None, None, \
            JsonResponse({"error": f"Notion API error: {exc}"}, status=502)
    except requests.RequestException as exc:
        return None, None, None, None, None, None, None, \
            JsonResponse({"error": f"Network error: {exc}"}, status=502)

    return period, year, month, week, day, range_start, range_end, rows


class HabitsSummaryView(View):
    def get(self, request):
        period, year, month, week, day, range_start, range_end, rows_or_err = _common_fetch(request)
        if isinstance(rows_or_err, JsonResponse):
            return rows_or_err
        rows = rows_or_err

        habits = _habit_fields(rows)
        total_days = len(rows)
        done = {h: 0 for h in habits}
        scores = []

        for row in rows:
            props = row.get("properties", {})
            for h in habits:
                if (props.get(h) or {}).get("checkbox"):
                    done[h] += 1
            s = _row_score(row)
            if s is not None:
                scores.append(s)

        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        total_possible = total_days * len(habits)
        overall_rate = round(sum(done.values()) / total_possible * 100, 1) if total_possible else 0

        habit_stats = sorted([
            {
                "name": h,
                "done": done[h],
                "total": total_days,
                "rate": round(done[h] / total_days * 100, 1) if total_days else 0,
            }
            for h in habits
        ], key=lambda x: -x["rate"])

        return JsonResponse({
            "period": period,
            "total_days": total_days,
            "avg_score": avg_score,
            "overall_completion_rate": overall_rate,
            "habits": habit_stats,
            **_period_meta(period, year, month, week, range_start, range_end),
        })


def _habit_grid(rows, range_start, range_end):
    """Per-day binary grid: 1=done, 0=not done, None=entry missing."""
    if not rows or range_start is None or range_end is None:
        return None
    habits = _habit_fields(rows)
    dates = []
    d = range_start
    while d <= range_end:
        dates.append(d.isoformat())
        d += timedelta(days=1)
    row_by_date = {_row_date(r): r for r in rows if _row_date(r)}
    result = []
    for h in habits:
        vals = []
        for date_str in dates:
            row = row_by_date.get(date_str)
            if row is None:
                vals.append(None)
            else:
                done = (row.get("properties", {}).get(h) or {}).get("checkbox", False)
                vals.append(1 if done else 0)
        result.append({"name": h, "values": vals})
    return {"dates": dates, "habits": result}


class HabitsChartView(View):
    def get(self, request):
        period, year, month, week, day, range_start, range_end, rows_or_err = _common_fetch(request)
        if isinstance(rows_or_err, JsonResponse):
            return rows_or_err
        rows = rows_or_err

        habits = _habit_fields(rows)
        total_days = len(rows)
        done = {h: 0 for h in habits}

        for row in rows:
            props = row.get("properties", {})
            for h in habits:
                if (props.get(h) or {}).get("checkbox"):
                    done[h] += 1

        sorted_habits = sorted(done.items(), key=lambda x: -x[1])
        habit_counts = {
            "labels": [h for h, _ in sorted_habits],
            "values": [c for _, c in sorted_habits],
        }

        show_grid = period in ("daily", "weekly", "monthly") or (
            period == "custom" and range_start and range_end
            and (range_end - range_start).days <= 60
        )
        grid = _habit_grid(rows, range_start, range_end) if show_grid else None

        return JsonResponse({
            "period": period,
            "total_days": total_days,
            "score_trend": _score_trend(period, year, rows, range_start, range_end),
            "habit_counts": habit_counts,
            "habit_grid": grid,
            **_period_meta(period, year, month, week, range_start, range_end),
        })


class BackfillView(View):
    def post(self, request):
        token, db_id = _get_creds()
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_HABITS_DB_ID must be set"}, status=500)

        headers = _notion_headers(token)
        start = date(date.today().year, 1, 1)
        today = date.today()

        notion_filter = {
            "and": [
                {"property": "Date", "date": {"on_or_after": start.isoformat()}},
                {"property": "Date", "date": {"on_or_before": today.isoformat()}},
            ]
        }

        try:
            rows = _fetch_all_rows(token, db_id, notion_filter)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Notion fetch error: {exc}"}, status=502)

        existing = {_row_date(r) for r in rows if _row_date(r)}

        all_dates = []
        d = start
        while d <= today:
            all_dates.append(d.isoformat())
            d += timedelta(days=1)

        missing = [d for d in all_dates if d not in existing]

        created, failed = [], []
        for date_str in missing:
            payload = {
                "parent": {"database_id": db_id},
                "properties": {
                    "Date": {"date": {"start": date_str}}
                },
            }
            try:
                resp = requests.post(NOTION_PAGES_URL, headers=headers, json=payload, timeout=15)
                if resp.status_code == 200:
                    created.append(date_str)
                else:
                    failed.append({"date": date_str, "error": resp.json()})
            except requests.RequestException as exc:
                failed.append({"date": date_str, "error": str(exc)})

        return JsonResponse({"created": len(created), "dates": created, "failed": failed})


class CheckHabitsView(View):
    def post(self, request):
        token, db_id = _get_creds()
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_HABITS_DB_ID must be set"}, status=500)

        try:
            body = json.loads(request.body)
        except (ValueError, json.JSONDecodeError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        habits = body.get("habits", {})
        if not isinstance(habits, dict):
            return JsonResponse({"error": "'habits' must be an object e.g. {\"Exercise\": true}"}, status=400)

        today     = date.today().isoformat()
        headers   = _notion_headers(token)

        # Find today's page
        notion_filter = {"property": "Date", "date": {"equals": today}}
        try:
            rows = _fetch_all_rows(token, db_id, notion_filter)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Notion fetch error: {exc}"}, status=502)

        created = False
        if rows:
            page_id = rows[0]["id"]
        else:
            # Create today's page
            payload = {
                "parent":     {"database_id": db_id},
                "properties": {"Date": {"date": {"start": today}}},
            }
            try:
                resp = requests.post(NOTION_PAGES_URL, headers=headers, json=payload, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as exc:
                return JsonResponse({"error": f"Failed to create page: {exc}"}, status=502)
            page_id = resp.json()["id"]
            created = True

        # Patch the habits
        if habits:
            patch_props = {name: {"checkbox": bool(val)} for name, val in habits.items()}
            try:
                resp = requests.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers=headers,
                    json={"properties": patch_props},
                    timeout=15,
                )
                if not resp.ok:
                    try:
                        notion_err = resp.json()
                    except Exception:
                        notion_err = resp.text
                    return JsonResponse({"error": notion_err}, status=resp.status_code)
            except requests.RequestException as exc:
                return JsonResponse({"error": f"Failed to update habits: {exc}"}, status=502)

        return JsonResponse({
            "date":    today,
            "page_id": page_id,
            "created": created,
            "updated": habits,
        })


class DashboardView(View):
    def get(self, request):
        return render(request, "habits/dashboard.html")


class ChartsView(View):
    def get(self, request):
        return render(request, "habits/charts.html")
