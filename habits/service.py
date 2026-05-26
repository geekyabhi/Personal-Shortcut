import re
from datetime import date, timedelta

import requests

from .data_layer import create_page, fetch_all_rows, patch_page

VALID_PERIODS = ("all", "yearly", "monthly", "weekly", "daily", "custom")

YEAR_RE  = re.compile(r"^\d{4}$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
WEEK_RE  = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")
DAY_RE   = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")

_TRUTHY = {"true", "1", "yes", "on"}


# ── Validation ──────────────────────────────────────────────────────────────

def validate_period_params(period, year, month, week, day, start="", end=""):
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period '{period}'. Valid: {', '.join(VALID_PERIODS)}")
    if year  and not YEAR_RE.match(year):   raise ValueError("Invalid year. Use YYYY")
    if month and not MONTH_RE.match(month): raise ValueError("Invalid month. Use YYYY-MM")
    if week  and not WEEK_RE.match(week):   raise ValueError("Invalid week. Use YYYY-Www")
    if day   and not DAY_RE.match(day):     raise ValueError("Invalid day. Use YYYY-MM-DD")
    if period == "custom":
        if not start or not end:            raise ValueError("Custom period requires both start and end")
        if not DAY_RE.match(start):         raise ValueError("Invalid start date. Use YYYY-MM-DD")
        if not DAY_RE.match(end):           raise ValueError("Invalid end date. Use YYYY-MM-DD")
        if start > end:                     raise ValueError("start must be on or before end")


# ── Date filter ──────────────────────────────────────────────────────────────

def build_date_filter(period, year=None, month=None, week=None, day=None, start=None, end=None):
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


# ── Row accessors ─────────────────────────────────────────────────────────────

def get_habit_fields(rows):
    if not rows:
        return []
    props = rows[0].get("properties", {})
    return sorted([k for k, v in props.items() if v.get("type") == "checkbox"])


def get_row_date(row):
    return (((row.get("properties", {}).get("Date") or {}).get("date") or {}).get("start") or "")[:10]


def get_row_score(row):
    return ((row.get("properties", {}).get("Score") or {}).get("formula") or {}).get("number")


# ── Period metadata ───────────────────────────────────────────────────────────

def get_period_meta(period, year, month, week, range_start, range_end):
    if period == "yearly":  return {"year": year or str(date.today().year)}
    if period == "monthly": return {"month": month or date.today().strftime("%Y-%m")}
    if period == "weekly":  return {"week_start": range_start.isoformat(), "week_end": range_end.isoformat()}
    if period == "daily":   return {"date": range_start.isoformat()}
    if period == "custom":  return {"start": range_start.isoformat(), "end": range_end.isoformat()}
    return {}


# ── Chart builders ────────────────────────────────────────────────────────────

def build_score_trend(period, year, rows, range_start, range_end):
    if period == "daily" or not rows:
        scores = [s for r in rows if (s := get_row_score(r)) is not None]
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
            k, s = get_row_date(row), get_row_score(row)
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
            k, s = get_row_date(row)[:7], get_row_score(row)
            if k in buckets and s is not None:
                buckets[k].append(s)
        return {
            "labels": [date(int(k[:4]), int(k[5:]), 1).strftime("%b") for k in sorted(buckets)],
            "values": [round(sum(v) / len(v), 1) if v else None for v in [buckets[k] for k in sorted(buckets)]],
        }

    if period == "custom":
        delta = (range_end - range_start).days
        if delta <= 60:
            buckets = {}
            d = range_start
            while d <= range_end:
                buckets[d.isoformat()] = []
                d += timedelta(days=1)
            for row in rows:
                k, s = get_row_date(row), get_row_score(row)
                if k in buckets and s is not None:
                    buckets[k].append(s)
            return {
                "labels": [date.fromisoformat(k).strftime("%-d %b") for k in sorted(buckets)],
                "values": [round(sum(v) / len(v), 1) if v else None for v in [buckets[k] for k in sorted(buckets)]],
            }
        buckets2: dict[str, list] = {}
        d = range_start
        while d <= range_end:
            k = d.strftime("%Y-%m")
            buckets2.setdefault(k, [])
            d += timedelta(days=1)
        for row in rows:
            k, s = get_row_date(row)[:7], get_row_score(row)
            if k in buckets2 and s is not None:
                buckets2[k].append(s)
        keys2 = sorted(buckets2)
        return {
            "labels": [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in keys2],
            "values": [round(sum(buckets2[k]) / len(buckets2[k]), 1) if buckets2[k] else None for k in keys2],
        }

    # all — monthly buckets
    buckets: dict[str, list] = {}
    for row in rows:
        k, s = get_row_date(row)[:7], get_row_score(row)
        if len(k) == 7 and s is not None:
            buckets.setdefault(k, []).append(s)
    keys = sorted(buckets)
    return {
        "labels": [date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y") for k in keys],
        "values": [round(sum(buckets[k]) / len(buckets[k]), 1) for k in keys],
    }


def build_habit_grid(rows, range_start, range_end):
    if not rows or range_start is None or range_end is None:
        return None
    habits = get_habit_fields(rows)
    dates = []
    d = range_start
    while d <= range_end:
        dates.append(d.isoformat())
        d += timedelta(days=1)
    row_by_date = {get_row_date(r): r for r in rows if get_row_date(r)}
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


# ── High-level service functions ──────────────────────────────────────────────

def get_habits_summary(token, db_id, period, year, month, week, day, start, end):
    validate_period_params(period, year, month, week, day, start, end)
    notion_filter, range_start, range_end = build_date_filter(
        period, year=year or None, month=month or None,
        week=week or None, day=day or None,
        start=start or None, end=end or None,
    )
    rows = fetch_all_rows(token, db_id, notion_filter)

    habits = get_habit_fields(rows)
    total_days = len(rows)
    done = {h: 0 for h in habits}
    scores = []

    for row in rows:
        props = row.get("properties", {})
        for h in habits:
            if (props.get(h) or {}).get("checkbox"):
                done[h] += 1
        s = get_row_score(row)
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

    return {
        "period": period,
        "total_days": total_days,
        "avg_score": avg_score,
        "overall_completion_rate": overall_rate,
        "habits": habit_stats,
        **get_period_meta(period, year, month, week, range_start, range_end),
    }


def get_habits_chart_data(token, db_id, period, year, month, week, day, start, end):
    validate_period_params(period, year, month, week, day, start, end)
    notion_filter, range_start, range_end = build_date_filter(
        period, year=year or None, month=month or None,
        week=week or None, day=day or None,
        start=start or None, end=end or None,
    )
    rows = fetch_all_rows(token, db_id, notion_filter)

    habits = get_habit_fields(rows)
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
    grid = build_habit_grid(rows, range_start, range_end) if show_grid else None

    return {
        "period": period,
        "total_days": total_days,
        "score_trend": build_score_trend(period, year, rows, range_start, range_end),
        "habit_counts": habit_counts,
        "habit_grid": grid,
        **get_period_meta(period, year, month, week, range_start, range_end),
    }


def backfill_missing_dates(token, db_id):
    today = date.today()
    start = date(today.year, 1, 1)

    notion_filter = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start.isoformat()}},
            {"property": "Date", "date": {"on_or_before": today.isoformat()}},
        ]
    }
    rows = fetch_all_rows(token, db_id, notion_filter)
    existing = {get_row_date(r) for r in rows if get_row_date(r)}

    all_dates = []
    d = start
    while d <= today:
        all_dates.append(d.isoformat())
        d += timedelta(days=1)

    missing = [d for d in all_dates if d not in existing]

    created, failed = [], []
    for date_str in missing:
        try:
            create_page(token, db_id, date_str)
            created.append(date_str)
        except requests.HTTPError as exc:
            try:
                err = exc.response.json() if exc.response else str(exc)
            except Exception:
                err = str(exc)
            failed.append({"date": date_str, "error": err})
        except requests.RequestException as exc:
            failed.append({"date": date_str, "error": str(exc)})

    return {"created": len(created), "dates": created, "failed": failed}


def _to_bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, str):  return v.strip().lower() in _TRUTHY
    return bool(v)


def check_and_update_habits(token, db_id, habits_dict):
    today = date.today().isoformat()
    notion_filter = {"property": "Date", "date": {"equals": today}}
    rows = fetch_all_rows(token, db_id, notion_filter)

    created = False
    if rows:
        page_id = rows[0]["id"]
    else:
        page = create_page(token, db_id, today)
        page_id = page["id"]
        created = True

    if habits_dict:
        patch_props = {name: {"checkbox": _to_bool(val)} for name, val in habits_dict.items()}
        patch_page(token, page_id, patch_props)

    return {
        "date": today,
        "page_id": page_id,
        "created": created,
        "updated": habits_dict,
    }
