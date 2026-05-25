import json
import os
import time

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

NOTION_VERSION = "2022-06-28"
READ_DB_ID  = os.environ.get("NOTION_READ_BLOGS_DB_ID",  "2832ba62-358b-8100-bb76-ebe4dbc79ff4")
WRITE_DB_ID = os.environ.get("NOTION_WRITE_BLOGS_DB_ID", "2832ba62-358b-813b-b78e-e9df9b6822a5")

_read_cache  = {"rows": None, "ts": 0.0}
_write_cache = {"rows": None, "ts": 0.0}
CACHE_TTL = 300


def _headers():
    return {
        "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN', '')}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _fetch_all(db_id, cache):
    now = time.time()
    if cache["rows"] is not None and now - cache["ts"] < CACHE_TTL:
        return cache["rows"]
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    rows, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = requests.post(url, headers=_headers(), json=body, timeout=15)
        data = resp.json()
        rows.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    cache["rows"] = rows
    cache["ts"] = now
    return rows


def _row_to_read_blog(row):
    props = row.get("properties", {})

    def title(key):
        return "".join(t.get("plain_text", "") for t in props.get(key, {}).get("title", [])).strip()

    def rich(key):
        return "".join(t.get("plain_text", "") for t in props.get(key, {}).get("rich_text", [])).strip()

    def sel(key):
        s = props.get(key, {}).get("select")
        return s["name"] if s else ""

    return {
        "page_id": row.get("id", ""),
        "topic": title("Topic"),
        "status": sel("Status"),
        "url": rich("Resource"),
        "created_time": row.get("created_time", ""),
        "last_edited_time": row.get("last_edited_time", ""),
    }


def _row_to_write_blog(row):
    props = row.get("properties", {})

    def title(key):
        return "".join(t.get("plain_text", "") for t in props.get(key, {}).get("title", [])).strip()

    def sel(key):
        s = props.get(key, {}).get("select")
        return s["name"] if s else ""

    return {
        "page_id": row.get("id", ""),
        "topic": title("Topic"),
        "status": sel("Status"),
        "url": props.get("URL", {}).get("url", "") or "",
        "created_time": row.get("created_time", ""),
        "last_edited_time": row.get("last_edited_time", ""),
    }


READ_STATUS_ORDER  = ["Reading", "To Read", "Read"]
WRITE_STATUS_ORDER = ["Draft", "To Write", "Written", "Published"]


class BlogsDashboardView(View):
    def get(self, request):
        return render(request, "blogs/dashboard.html")


class BlogsStatsView(View):
    def get(self, request):
        read_rows  = _fetch_all(READ_DB_ID,  _read_cache)
        write_rows = _fetch_all(WRITE_DB_ID, _write_cache)

        read_status, write_status = {}, {}
        for b in [_row_to_read_blog(r) for r in read_rows]:
            s = b["status"] or "Unknown"
            read_status[s] = read_status.get(s, 0) + 1
        for b in [_row_to_write_blog(r) for r in write_rows]:
            s = b["status"] or "Unknown"
            write_status[s] = write_status.get(s, 0) + 1

        return JsonResponse({
            "read_total":   len(read_rows),
            "read_status":  read_status,
            "write_total":  len(write_rows),
            "write_status": write_status,
        })


# ── Read blogs ──────────────────────────────────────────────────────────────

class ReadBlogsListView(View):
    def get(self, request):
        rows  = _fetch_all(READ_DB_ID, _read_cache)
        blogs = [_row_to_read_blog(r) for r in rows]

        status_filter = request.GET.get("status", "")
        q = request.GET.get("q", "").lower()

        if status_filter:
            blogs = [b for b in blogs if b["status"] == status_filter]
        if q:
            blogs = [b for b in blogs if q in b["topic"].lower()]

        blogs.sort(key=lambda b: (
            READ_STATUS_ORDER.index(b["status"]) if b["status"] in READ_STATUS_ORDER else 99,
            b["topic"].lower(),
        ))
        return JsonResponse({"blogs": blogs, "total": len(blogs)})


class ReadBlogsCreateView(View):
    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        topic = body.get("topic", "").strip()
        if not topic:
            return JsonResponse({"error": "Topic is required"}, status=400)

        properties = {
            "Topic":  {"title": [{"text": {"content": topic}}]},
            "Status": {"select": {"name": body.get("status", "To Read")}},
        }
        url = body.get("url", "").strip()
        if url:
            properties["Resource"] = {"rich_text": [{"text": {"content": url}}]}

        resp = requests.post(
            "https://api.notion.com/v1/pages",
            headers=_headers(),
            json={"parent": {"database_id": READ_DB_ID}, "properties": properties},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            return JsonResponse({"error": resp.text}, status=502)
        _read_cache["ts"] = 0.0
        return JsonResponse({"ok": True, "page_id": resp.json().get("id", "")})


class ReadBlogsUpdateView(View):
    def patch(self, request, page_id):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        properties = {}
        if "topic" in body:
            topic = body["topic"].strip()
            if not topic:
                return JsonResponse({"error": "Topic required"}, status=400)
            properties["Topic"] = {"title": [{"text": {"content": topic}}]}
        if "status" in body:
            properties["Status"] = {"select": {"name": body["status"]}}
        if "url" in body:
            properties["Resource"] = {"rich_text": [{"text": {"content": body["url"].strip()}}]}

        if not properties:
            return JsonResponse({"error": "Nothing to update"}, status=400)

        resp = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=_headers(),
            json={"properties": properties},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            return JsonResponse({"error": resp.text}, status=502)
        _read_cache["ts"] = 0.0
        return JsonResponse({"ok": True})


class ReadBlogsDeleteView(View):
    def post(self, request, page_id):
        resp = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=_headers(),
            json={"archived": True},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            return JsonResponse({"error": resp.text}, status=502)
        _read_cache["ts"] = 0.0
        return JsonResponse({"ok": True})


# ── Write blogs ──────────────────────────────────────────────────────────────

class WriteBlogsListView(View):
    def get(self, request):
        rows  = _fetch_all(WRITE_DB_ID, _write_cache)
        blogs = [_row_to_write_blog(r) for r in rows]

        status_filter = request.GET.get("status", "")
        q = request.GET.get("q", "").lower()

        if status_filter:
            blogs = [b for b in blogs if b["status"] == status_filter]
        if q:
            blogs = [b for b in blogs if q in b["topic"].lower()]

        blogs.sort(key=lambda b: (
            WRITE_STATUS_ORDER.index(b["status"]) if b["status"] in WRITE_STATUS_ORDER else 99,
            b["topic"].lower(),
        ))
        return JsonResponse({"blogs": blogs, "total": len(blogs)})


class WriteBlogsCreateView(View):
    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        topic = body.get("topic", "").strip()
        if not topic:
            return JsonResponse({"error": "Topic is required"}, status=400)

        properties = {
            "Topic":  {"title": [{"text": {"content": topic}}]},
            "Status": {"select": {"name": body.get("status", "To Write")}},
        }
        url = body.get("url", "").strip()
        if url:
            properties["URL"] = {"url": url}

        resp = requests.post(
            "https://api.notion.com/v1/pages",
            headers=_headers(),
            json={"parent": {"database_id": WRITE_DB_ID}, "properties": properties},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            return JsonResponse({"error": resp.text}, status=502)
        _write_cache["ts"] = 0.0
        return JsonResponse({"ok": True, "page_id": resp.json().get("id", "")})


class WriteBlogsUpdateView(View):
    def patch(self, request, page_id):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        properties = {}
        if "topic" in body:
            topic = body["topic"].strip()
            if not topic:
                return JsonResponse({"error": "Topic required"}, status=400)
            properties["Topic"] = {"title": [{"text": {"content": topic}}]}
        if "status" in body:
            properties["Status"] = {"select": {"name": body["status"]}}
        if "url" in body:
            url = body["url"].strip()
            properties["URL"] = {"url": url if url else None}

        if not properties:
            return JsonResponse({"error": "Nothing to update"}, status=400)

        resp = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=_headers(),
            json={"properties": properties},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            return JsonResponse({"error": resp.text}, status=502)
        _write_cache["ts"] = 0.0
        return JsonResponse({"ok": True})


class WriteBlogsDeleteView(View):
    def post(self, request, page_id):
        resp = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=_headers(),
            json={"archived": True},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            return JsonResponse({"error": resp.text}, status=502)
        _write_cache["ts"] = 0.0
        return JsonResponse({"ok": True})


class BlogsCacheView(View):
    def post(self, request):
        _read_cache["ts"] = 0.0
        _write_cache["ts"] = 0.0
        return JsonResponse({"ok": True})
