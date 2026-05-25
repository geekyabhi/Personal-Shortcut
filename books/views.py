import os
import time

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View


NOTION_VERSION = "2022-06-28"
BOOKS_DB_ID = os.environ.get("NOTION_BOOKS_DB_ID", "752ac6b0-8422-42dc-9439-b60a411f3c3d")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")

_books_cache: dict = {"rows": None, "ts": 0.0}
CACHE_TTL = 300


def _headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _fetch_all_books():
    now = time.time()
    if _books_cache["rows"] is not None and now - _books_cache["ts"] < CACHE_TTL:
        return _books_cache["rows"]

    url = f"https://api.notion.com/v1/databases/{BOOKS_DB_ID}/query"
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

    _books_cache["rows"] = rows
    _books_cache["ts"] = now
    return rows


def _row_to_book(row):
    props = row.get("properties", {})

    def title(key):
        items = props.get(key, {}).get("title", [])
        return "".join(t.get("plain_text", "") for t in items).strip()

    def rich(key):
        items = props.get(key, {}).get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in items).strip()

    def select(key):
        s = props.get(key, {}).get("select")
        return s["name"] if s else ""

    def multi(key):
        return [o["name"] for o in props.get(key, {}).get("multi_select", [])]

    return {
        "page_id": row.get("id", ""),
        "name": title("Book Name"),
        "status": select("Status"),
        "genre": multi("Genre"),
        "author": multi("Author"),
        "summary": rich("Summary"),
        "summary_status": select("Summary Status"),
    }


STATUS_ORDER = ["Reading", "To Read", "Queued", "Finished", "Blocked", "Unorganized"]


class BooksDashboardView(View):
    def get(self, request):
        return render(request, "books/dashboard.html")


class BooksListView(View):
    def get(self, request):
        rows = _fetch_all_books()
        books = [_row_to_book(r) for r in rows]

        status_filter = request.GET.get("status", "")
        genre_filter = request.GET.get("genre", "")
        author_filter = request.GET.get("author", "").lower()
        search = request.GET.get("q", "").lower()

        if status_filter:
            books = [b for b in books if b["status"] == status_filter]
        if genre_filter:
            books = [b for b in books if genre_filter in b["genre"]]
        if author_filter:
            books = [b for b in books if any(author_filter in a.lower() for a in b["author"])]
        if search:
            books = [b for b in books if search in b["name"].lower()]

        books.sort(key=lambda b: (STATUS_ORDER.index(b["status"]) if b["status"] in STATUS_ORDER else 99, b["name"].lower()))

        return JsonResponse({"books": books, "total": len(books)})


class BooksStatsView(View):
    def get(self, request):
        rows = _fetch_all_books()
        books = [_row_to_book(r) for r in rows]

        status_counts = {}
        genre_counts = {}
        all_genres = set()
        all_authors = set()

        for b in books:
            s = b["status"] or "Unknown"
            status_counts[s] = status_counts.get(s, 0) + 1
            for g in b["genre"]:
                genre_counts[g] = genre_counts.get(g, 0) + 1
                all_genres.add(g)
            for a in b["author"]:
                all_authors.add(a)

        return JsonResponse({
            "total": len(books),
            "status_counts": status_counts,
            "genre_counts": genre_counts,
            "all_genres": sorted(all_genres),
            "all_authors": sorted(all_authors),
        })


class BooksCacheView(View):
    def post(self, request):
        _books_cache["ts"] = 0.0
        return JsonResponse({"ok": True})
