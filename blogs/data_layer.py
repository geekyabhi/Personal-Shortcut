import os
import time

import requests


class BlogsDataLayer:
    NOTION_VERSION = "2022-06-28"
    NOTION_DB_QUERY_URL = "https://api.notion.com/v1/databases/{db_id}/query"
    NOTION_PAGES_URL = "https://api.notion.com/v1/pages"
    NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"

    CACHE_TTL = 300

    _read_cache = {"rows": None, "ts": 0.0}
    _write_cache = {"rows": None, "ts": 0.0}

    def __init__(self, token, read_db_id, write_db_id):
        self.token = token
        self.read_db_id = read_db_id
        self.write_db_id = write_db_id

    @classmethod
    def from_env(cls):
        return cls(
            token=os.environ.get("NOTION_TOKEN", ""),
            read_db_id=os.environ.get("NOTION_READ_BLOGS_DB_ID", "2832ba62-358b-8100-bb76-ebe4dbc79ff4"),
            write_db_id=os.environ.get("NOTION_WRITE_BLOGS_DB_ID", "2832ba62-358b-813b-b78e-e9df9b6822a5"),
        )

    @property
    def is_configured(self):
        return bool(self.token)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _fetch_all(self, db_id, cache):
        now = time.time()
        if cache["rows"] is not None and now - cache["ts"] < self.CACHE_TTL:
            return cache["rows"]
        url = self.NOTION_DB_QUERY_URL.format(db_id=db_id)
        rows, cursor = [], None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            resp = requests.post(url, headers=self._headers(), json=body, timeout=15)
            data = resp.json()
            rows.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        cache["rows"] = rows
        cache["ts"] = now
        return rows

    def fetch_read_blogs(self):
        return self._fetch_all(self.read_db_id, BlogsDataLayer._read_cache)

    def fetch_write_blogs(self):
        return self._fetch_all(self.write_db_id, BlogsDataLayer._write_cache)

    def create_page(self, db_id, properties):
        resp = requests.post(
            self.NOTION_PAGES_URL,
            headers=self._headers(),
            json={"parent": {"database_id": db_id}, "properties": properties},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def patch_page(self, page_id, payload):
        resp = requests.patch(
            self.NOTION_PAGE_URL.format(page_id=page_id),
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def bust_read_cache(self):
        BlogsDataLayer._read_cache["ts"] = 0.0

    def bust_write_cache(self):
        BlogsDataLayer._write_cache["ts"] = 0.0
