import json
import os
import time
from collections import defaultdict

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


def _extract_files(props, key):
    items = props.get(key, {}).get("files", [])
    result = []
    for f in items:
        name = f.get("name", key)
        if f.get("type") == "external":
            result.append({"name": name, "url": f["external"]["url"], "hosted": False})
        elif f.get("type") == "file":
            result.append({"name": name, "url": f["file"]["url"], "hosted": True})
    return result


def _row_to_book(row):
    props = row.get("properties", {})

    def title(key):
        return "".join(t.get("plain_text", "") for t in props.get(key, {}).get("title", [])).strip()

    def rich(key):
        return "".join(t.get("plain_text", "") for t in props.get(key, {}).get("rich_text", [])).strip()

    def sel(key):
        s = props.get(key, {}).get("select")
        return s["name"] if s else ""

    def multi(key):
        return [o["name"] for o in props.get(key, {}).get("multi_select", [])]

    return {
        "page_id": row.get("id", ""),
        "name": title("Book Name"),
        "status": sel("Status"),
        "genre": multi("Genre"),
        "author": multi("Author"),
        "summary": rich("Summary"),
        "summary_status": sel("Summary Status"),
        "soft_copy": _extract_files(props, "Soft Copy"),
        "key_points": _extract_files(props, "Key Points"),
        "created_time": row.get("created_time", ""),
        "last_edited_time": row.get("last_edited_time", ""),
    }


STATUS_ORDER = ["Reading", "To Read", "Queued", "Finished", "Blocked", "Unorganized"]


class BooksDashboardView(View):
    def get(self, request):
        return render(request, "books/dashboard.html")


class BooksChartsView(View):
    def get(self, request):
        return render(request, "books/charts.html")


class BooksListView(View):
    def get(self, request):
        rows = _fetch_all_books()
        books = [_row_to_book(r) for r in rows]

        status_filter = request.GET.get("status", "")
        genre_filter = request.GET.get("genre", "")
        author_filter = request.GET.get("author", "")
        search = request.GET.get("q", "").lower()

        if status_filter:
            books = [b for b in books if b["status"] == status_filter]
        if genre_filter:
            books = [b for b in books if genre_filter in b["genre"]]
        if author_filter:
            books = [b for b in books if author_filter in b["author"]]
        if search:
            books = [b for b in books if search in b["name"].lower()]

        books.sort(key=lambda b: (
            STATUS_ORDER.index(b["status"]) if b["status"] in STATUS_ORDER else 99,
            b["name"].lower(),
        ))

        return JsonResponse({"books": books, "total": len(books)})


class BooksStatsView(View):
    def get(self, request):
        rows = _fetch_all_books()
        books = [_row_to_book(r) for r in rows]

        status_counts = {}
        genre_counts = {}
        author_counts = {}
        all_genres, all_authors = set(), set()

        for b in books:
            s = b["status"] or "Unknown"
            status_counts[s] = status_counts.get(s, 0) + 1
            for g in b["genre"]:
                genre_counts[g] = genre_counts.get(g, 0) + 1
                all_genres.add(g)
            for a in b["author"]:
                author_counts[a] = author_counts.get(a, 0) + 1
                all_authors.add(a)

        top_genres = sorted(genre_counts.items(), key=lambda x: -x[1])[:15]
        top_authors = sorted(author_counts.items(), key=lambda x: -x[1])[:10]

        return JsonResponse({
            "total": len(books),
            "status_counts": status_counts,
            "genre_counts": genre_counts,
            "top_genres": top_genres,
            "top_authors": top_authors,
            "all_genres": sorted(all_genres),
            "all_authors": sorted(all_authors),
        })


class BooksChartsDataView(View):
    def get(self, request):
        rows = _fetch_all_books()
        books = [_row_to_book(r) for r in rows]

        status_counts = {}
        genre_counts = {}
        author_counts = {}
        finished_by_year = defaultdict(int)
        finished_by_month = defaultdict(int)   # "YYYY-MM"
        added_by_year = defaultdict(int)

        for b in books:
            s = b["status"] or "Unknown"
            status_counts[s] = status_counts.get(s, 0) + 1

            for g in b["genre"]:
                genre_counts[g] = genre_counts.get(g, 0) + 1
            for a in b["author"]:
                author_counts[a] = author_counts.get(a, 0) + 1

            # Books added to DB by year
            if b["created_time"]:
                yr = b["created_time"][:4]
                added_by_year[yr] += 1

            # Finished books — use last_edited_time as proxy for finish date
            if b["status"] == "Finished" and b["last_edited_time"]:
                yr = b["last_edited_time"][:4]
                ym = b["last_edited_time"][:7]
                finished_by_year[yr] += 1
                finished_by_month[ym] += 1

        # Fill missing months for last 24 months
        import datetime
        today = datetime.date.today()
        all_months = []
        for i in range(23, -1, -1):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            all_months.append(f"{y}-{m:02d}")

        monthly_finished = {m: finished_by_month.get(m, 0) for m in all_months}

        top_genres = sorted(genre_counts.items(), key=lambda x: -x[1])[:15]
        top_authors = sorted(author_counts.items(), key=lambda x: -x[1])[:10]

        return JsonResponse({
            "total": len(books),
            "status_counts": status_counts,
            "top_genres": top_genres,
            "top_authors": top_authors,
            "finished_by_year": dict(sorted(finished_by_year.items())),
            "monthly_finished": monthly_finished,
            "added_by_year": dict(sorted(added_by_year.items())),
        })


class BooksCreateView(View):
    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        name = body.get("name", "").strip()
        if not name:
            return JsonResponse({"error": "Book name is required"}, status=400)

        status = body.get("status", "To Read")
        authors = body.get("authors", [])
        genres = body.get("genres", [])
        summary = body.get("summary", "").strip()

        properties = {
            "Book Name": {"title": [{"text": {"content": name}}]},
            "Status": {"select": {"name": status}},
        }
        if authors:
            properties["Author"] = {"multi_select": [{"name": a} for a in authors]}
        if genres:
            properties["Genre"] = {"multi_select": [{"name": g} for g in genres]}
        if summary:
            properties["Summary"] = {"rich_text": [{"text": {"content": summary}}]}

        resp = requests.post(
            "https://api.notion.com/v1/pages",
            headers=_headers(),
            json={"parent": {"database_id": BOOKS_DB_ID}, "properties": properties},
            timeout=15,
        )

        if resp.status_code not in (200, 201):
            return JsonResponse({"error": resp.text}, status=502)

        _books_cache["ts"] = 0.0
        return JsonResponse({"ok": True, "page_id": resp.json().get("id", "")})


class BooksCacheView(View):
    def post(self, request):
        _books_cache["ts"] = 0.0
        return JsonResponse({"ok": True})
