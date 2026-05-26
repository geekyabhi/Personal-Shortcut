import os
import time

import requests


class ExpensesDataLayer:
    NOTION_VERSION = "2022-06-28"
    NOTION_DB_QUERY_URL = "https://api.notion.com/v1/databases/{db_id}/query"
    NOTION_PAGES_URL = "https://api.notion.com/v1/pages"
    NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
    CACHE_TTL = 300  # seconds

    _cache: dict = {"rows": None, "ts": 0.0}

    def __init__(self, token: str, db_id: str):
        self.token = token
        self.db_id = db_id

    @classmethod
    def from_env(cls) -> "ExpensesDataLayer":
        return cls(
            token=os.environ.get("NOTION_TOKEN", ""),
            db_id=os.environ.get("NOTION_EXPENSES_DB_ID", ""),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.db_id)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def fetch_all_rows(self, notion_filter=None) -> list:
        """Paginated fetch from Notion. Raises on HTTP error."""
        url = self.NOTION_DB_QUERY_URL.format(db_id=self.db_id)
        payload: dict = {}
        if notion_filter:
            payload["filter"] = notion_filter

        rows = []
        has_more = True

        while has_more:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            rows.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            if has_more:
                payload["start_cursor"] = data["next_cursor"]

        return rows

    def get_cached_rows(self, force: bool = False):
        """Return (rows, cache_ts, from_cache). Uses class-level shared cache."""
        now = time.time()
        cache = self.__class__._cache
        if (
            not force
            and cache["rows"] is not None
            and (now - cache["ts"]) < self.CACHE_TTL
        ):
            return cache["rows"], cache["ts"], True

        rows = self.fetch_all_rows(None)
        cache["rows"] = rows
        cache["ts"] = time.time()
        return rows, cache["ts"], False

    def create_page(self, properties: dict) -> dict:
        """POST a new page to the expenses database. Raises on HTTP error."""
        resp = requests.post(
            self.NOTION_PAGES_URL,
            headers=self._headers(),
            json={"parent": {"database_id": self.db_id}, "properties": properties},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def patch_page(self, page_id: str, payload: dict) -> dict:
        """PATCH an existing page. Raises on HTTP error."""
        resp = requests.patch(
            self.NOTION_PAGE_URL.format(page_id=page_id),
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def bust_cache(self) -> None:
        """Invalidate the shared cache so the next request re-fetches."""
        self.__class__._cache["ts"] = 0.0
