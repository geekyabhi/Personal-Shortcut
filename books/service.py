import datetime
from collections import defaultdict

from .data_layer import BooksDataLayer, DriveDataLayer


class BooksService:
    STATUS_ORDER = ["Reading", "To Read", "Queued", "Finished", "Blocked", "Unorganized"]

    def __init__(self, data_layer: BooksDataLayer, drive_layer: DriveDataLayer = None):
        self.data_layer = data_layer
        self.drive_layer = drive_layer

    def _extract_files(self, props: dict, key: str) -> list:
        items = props.get(key, {}).get("files", [])
        result = []
        for f in items:
            name = f.get("name", key)
            if f.get("type") == "external":
                result.append({"name": name, "url": f["external"]["url"], "hosted": False})
            elif f.get("type") == "file":
                result.append({"name": name, "url": f["file"]["url"], "hosted": True})
        return result

    def _row_to_book(self, row: dict) -> dict:
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
            "soft_copy": self._extract_files(props, "Soft Copy"),
            "key_points": self._extract_files(props, "Key Points"),
            "created_time": row.get("created_time", ""),
            "last_edited_time": row.get("last_edited_time", ""),
        }

    def get_list(self, status: str = "", genre: str = "", author: str = "", search: str = "") -> dict:
        rows = self.data_layer.fetch_all_books()
        books = [self._row_to_book(r) for r in rows]

        if status:
            books = [b for b in books if b["status"] == status]
        if genre:
            books = [b for b in books if genre in b["genre"]]
        if author:
            books = [b for b in books if author in b["author"]]
        if search:
            books = [b for b in books if search.lower() in b["name"].lower()]

        books.sort(key=lambda b: (
            self.STATUS_ORDER.index(b["status"]) if b["status"] in self.STATUS_ORDER else 99,
            b["name"].lower(),
        ))
        return {"books": books, "total": len(books)}

    def get_stats(self) -> dict:
        rows = self.data_layer.fetch_all_books()
        books = [self._row_to_book(r) for r in rows]

        status_counts: dict = {}
        genre_counts: dict = {}
        author_counts: dict = {}
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

        return {
            "total": len(books),
            "status_counts": status_counts,
            "genre_counts": genre_counts,
            "top_genres": top_genres,
            "top_authors": top_authors,
            "all_genres": sorted(all_genres),
            "all_authors": sorted(all_authors),
        }

    def get_chart_data(self) -> dict:
        rows = self.data_layer.fetch_all_books()
        books = [self._row_to_book(r) for r in rows]

        status_counts: dict = {}
        genre_counts: dict = {}
        author_counts: dict = {}
        finished_by_year: dict = defaultdict(int)
        finished_by_month: dict = defaultdict(int)
        added_by_year: dict = defaultdict(int)

        for b in books:
            s = b["status"] or "Unknown"
            status_counts[s] = status_counts.get(s, 0) + 1
            for g in b["genre"]:
                genre_counts[g] = genre_counts.get(g, 0) + 1
            for a in b["author"]:
                author_counts[a] = author_counts.get(a, 0) + 1

            if b["created_time"]:
                added_by_year[b["created_time"][:4]] += 1

            if b["status"] == "Finished" and b["last_edited_time"]:
                yr = b["last_edited_time"][:4]
                ym = b["last_edited_time"][:7]
                finished_by_year[yr] += 1
                finished_by_month[ym] += 1

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

        return {
            "total": len(books),
            "status_counts": status_counts,
            "top_genres": top_genres,
            "top_authors": top_authors,
            "finished_by_year": dict(sorted(finished_by_year.items())),
            "monthly_finished": monthly_finished,
            "added_by_year": dict(sorted(added_by_year.items())),
        }

    def create_book(
        self,
        name: str,
        status: str,
        authors: list,
        genres: list,
        summary: str,
        drive_url: str,
    ) -> str:
        properties: dict = {
            "Book Name": {"title": [{"text": {"content": name}}]},
            "Status": {"select": {"name": status}},
        }
        if authors:
            properties["Author"] = {"multi_select": [{"name": a} for a in authors]}
        if genres:
            properties["Genre"] = {"multi_select": [{"name": g} for g in genres]}
        if summary:
            properties["Summary"] = {"rich_text": [{"text": {"content": summary}}]}
        if drive_url:
            properties["Soft Copy"] = {
                "files": [{"type": "external", "name": "Google Drive", "external": {"url": drive_url}}]
            }

        page = self.data_layer.create_page(properties)
        self.data_layer.bust_cache()
        return page.get("id", "")

    def update_book(self, page_id: str, body: dict):
        properties: dict = {}

        if "name" in body:
            name = body["name"].strip()
            if not name:
                raise ValueError("Book name required")
            properties["Book Name"] = {"title": [{"text": {"content": name}}]}

        if "status" in body:
            properties["Status"] = {"select": {"name": body["status"]}}

        if "authors" in body:
            properties["Author"] = {"multi_select": [{"name": a} for a in body["authors"]]}

        if "genres" in body:
            properties["Genre"] = {"multi_select": [{"name": g} for g in body["genres"]]}

        if "summary" in body:
            properties["Summary"] = {"rich_text": [{"text": {"content": body["summary"]}}]}

        if "drive_url" in body:
            if body["drive_url"].strip():
                properties["Soft Copy"] = {
                    "files": [{"type": "external", "name": "Google Drive", "external": {"url": body["drive_url"].strip()}}]
                }
            else:
                properties["Soft Copy"] = {"files": []}

        if not properties:
            raise ValueError("No fields to update")

        self.data_layer.patch_page(page_id, {"properties": properties})
        self.data_layer.bust_cache()

    def delete_book(self, page_id: str):
        self.data_layer.patch_page(page_id, {"archived": True})
        self.data_layer.bust_cache()

    def bust_cache(self):
        self.data_layer.bust_cache()

    def list_drive_files(self) -> list:
        return self.drive_layer.list_files()

    def upload_drive_file(self, upload, folder_id: str) -> dict:
        return self.drive_layer.upload_file(upload, folder_id)
