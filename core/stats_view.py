import os
import requests
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.http import JsonResponse
from django.views import View

NOTION_VERSION = "2022-06-28"


def _notion_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _query_notion(db_id, token, payload=None):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    rows, cursor = [], None
    while True:
        body = {**(payload or {}), "page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = requests.post(url, headers=_notion_headers(token), json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return rows


def _expenses_stat():
    token = os.environ.get("NOTION_TOKEN", "")
    db_id = os.environ.get("NOTION_EXPENSES_DB_ID", "")
    if not token or not db_id:
        return None
    today = date.today()
    s = today.replace(day=1)
    e = date(s.year + 1, 1, 1) if s.month == 12 else date(s.year, s.month + 1, 1)
    payload = {"filter": {"and": [
        {"property": "Date", "date": {"on_or_after": s.isoformat()}},
        {"property": "Date", "date": {"before": e.isoformat()}},
    ]}}
    rows = _query_notion(db_id, token, payload)
    total = sum((r.get("properties", {}).get("Amount") or {}).get("number") or 0 for r in rows)
    return f"₹{total:,.0f} this month"


def _habits_stat():
    token = os.environ.get("NOTION_TOKEN", "")
    db_id = os.environ.get("NOTION_HABITS_DB_ID", "")
    if not token or not db_id:
        return None
    today = date.today().isoformat()
    payload = {"filter": {"property": "Date", "date": {"equals": today}}}
    rows = _query_notion(db_id, token, payload)
    if not rows:
        return "No entry today"
    props = rows[0].get("properties", {})
    boxes = [v for v in props.values() if v.get("type") == "checkbox"]
    done = sum(1 for b in boxes if b.get("checkbox"))
    return f"{done}/{len(boxes)} done today"


def _books_stat():
    token = os.environ.get("NOTION_TOKEN", "")
    db_id = os.environ.get("NOTION_BOOKS_DB_ID", "752ac6b0-8422-42dc-9439-b60a411f3c3d")
    if not token or not db_id:
        return None
    rows = _query_notion(db_id, token)
    def status(r):
        return ((r.get("properties", {}).get("Status") or {}).get("select") or {}).get("name", "")
    reading = sum(1 for r in rows if status(r) == "Reading")
    queued  = sum(1 for r in rows if status(r) == "To Read")
    return f"{reading} reading · {queued} queued"


def _todos_stat():
    from todos.data_layer import JiraDataLayer
    dl = JiraDataLayer.from_env()
    if not dl.is_configured:
        return None
    jql = f"project={dl.project} AND statusCategory != Done ORDER BY created DESC"
    resp = dl.search_jql(jql=jql, max_results=0, fields="id")
    if not resp.ok:
        return None
    total = resp.json().get("total", 0)
    return f"{total} open issues"


def _blogs_stat():
    token  = os.environ.get("NOTION_TOKEN", "")
    db_id  = os.environ.get("NOTION_READ_BLOGS_DB_ID", "2832ba62-358b-8100-bb76-ebe4dbc79ff4")
    if not token or not db_id:
        return None
    rows = _query_notion(db_id, token)
    def status(r):
        return ((r.get("properties", {}).get("Status") or {}).get("select") or {}).get("name", "")
    to_read = sum(1 for r in rows if status(r) == "To Read")
    return f"{to_read} to read"


class HomeStatsView(View):
    def get(self, request):
        fetchers = {
            "expenses": _expenses_stat,
            "habits":   _habits_stat,
            "books":    _books_stat,
            "todos":    _todos_stat,
            "blogs":    _blogs_stat,
        }
        results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fn): key for key, fn in fetchers.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    results[key] = future.result()
                except Exception:
                    results[key] = None
        return JsonResponse(results)
