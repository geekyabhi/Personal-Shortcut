import os
import threading
import time
from datetime import date

import requests


class ExpensesDataLayer:
    NOTION_VERSION = "2022-06-28"
    NOTION_DB_QUERY_URL = "https://api.notion.com/v1/databases/{db_id}/query"
    NOTION_PAGES_URL = "https://api.notion.com/v1/pages"
    NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
    CACHE_TTL = 300  # seconds

    SWID_TTL = 60  # seconds — cache for the tiny "already-imported ids" query

    # Full dataset + a small "recent months" slice used for the fast first paint.
    _cache: dict = {"rows": None, "ts": 0.0}
    _recent_cache: dict = {"rows": None, "ts": 0.0}
    _swid_cache: dict = {"ids": None, "ts": 0.0, "exists": True}
    _full_fetch_lock = threading.Lock()

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

    @staticmethod
    def _recent_since() -> str:
        """First day of the previous calendar month (covers current + last month)."""
        t = date.today()
        y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
        return date(y, m, 1).isoformat()

    def fetch_recent_rows(self) -> list:
        """Single filtered Notion query for rows dated on/after `_recent_since()`."""
        return self.fetch_all_rows(
            {"property": "Date", "date": {"on_or_after": self._recent_since()}}
        )

    def imported_splitwise_ids(self, prop_name: str):
        """Return (set_of_ids, column_exists).

        A narrow filtered query — only rows that already carry a Splitwise
        id (a handful), never the whole table. Cached for `SWID_TTL`.
        """
        now = time.time()
        cache = self.__class__._swid_cache
        if cache["ids"] is not None and (now - cache["ts"]) < self.SWID_TTL:
            return set(cache["ids"]), cache["exists"]

        try:
            rows = self.fetch_all_rows(
                {"property": prop_name, "number": {"is_not_empty": True}}
            )
        except requests.HTTPError as exc:
            resp = exc.response
            if resp is not None and resp.status_code == 400 and prop_name in (resp.text or ""):
                cache.update(ids=[], ts=now, exists=False)  # column not added yet
                return set(), False
            raise

        ids = set()
        for row in rows:
            num = (row.get("properties", {}).get(prop_name) or {}).get("number")
            if num is not None:
                ids.add(int(num))
        cache.update(ids=list(ids), ts=now, exists=True)
        return set(ids), True

    def get_cached_rows(self, force: bool = False, partial: bool = False):
        """Return (rows, cache_ts, from_cache, is_partial).

        A fresh full cache always wins. Otherwise, when ``partial`` is set,
        return just the current + previous month (fast, one filtered query)
        and leave the full cache untouched so a later full call still
        fetches everything.
        """
        now = time.time()
        full = self.__class__._cache
        if (
            not force
            and full["rows"] is not None
            and (now - full["ts"]) < self.CACHE_TTL
        ):
            return full["rows"], full["ts"], True, False

        if partial and not force:
            recent = self.__class__._recent_cache
            if (
                recent["rows"] is not None
                and (now - recent["ts"]) < self.CACHE_TTL
            ):
                return recent["rows"], recent["ts"], True, True
            rows = self.fetch_recent_rows()
            recent["rows"] = rows
            recent["ts"] = time.time()
            return rows, recent["ts"], False, True

        # Full fetch — dedupe concurrent callers so a cold start crawls Notion once.
        with self.__class__._full_fetch_lock:
            now = time.time()
            if (
                not force
                and full["rows"] is not None
                and (now - full["ts"]) < self.CACHE_TTL
            ):
                return full["rows"], full["ts"], True, False
            rows = self.fetch_all_rows(None)
            full["rows"] = rows
            full["ts"] = time.time()
            return rows, full["ts"], False, False

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
        """Invalidate all caches so the next request re-fetches."""
        self.__class__._cache["ts"] = 0.0
        self.__class__._recent_cache["ts"] = 0.0
        self.__class__._swid_cache["ids"] = None
