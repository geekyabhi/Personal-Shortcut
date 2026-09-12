import os

import requests


class HabitsDataLayer:
    NOTION_PAGES_URL = "https://api.notion.com/v1/pages"
    NOTION_DB_QUERY_URL = "https://api.notion.com/v1/databases/{db_id}/query"
    NOTION_DB_URL = "https://api.notion.com/v1/databases/{db_id}"
    NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
    NOTION_VERSION = "2022-06-28"

    def __init__(self, token, db_id):
        self.token = token
        self.db_id = db_id

    @classmethod
    def from_env(cls):
        return cls(
            token=os.environ.get("NOTION_TOKEN"),
            db_id=os.environ.get("NOTION_HABITS_DB_ID"),
        )

    @property
    def is_configured(self):
        return bool(self.token and self.db_id)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def fetch_all_rows(self, notion_filter=None):
        url = self.NOTION_DB_QUERY_URL.format(db_id=self.db_id)
        payload = {}
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

    def fetch_schema(self):
        """Database properties, independent of whether any row exists yet."""
        resp = requests.get(
            self.NOTION_DB_URL.format(db_id=self.db_id), headers=self._headers(), timeout=15
        )
        resp.raise_for_status()
        return resp.json().get("properties", {})

    def add_checkbox_property(self, name):
        """Add a new checkbox column to the database schema."""
        resp = requests.patch(
            self.NOTION_DB_URL.format(db_id=self.db_id),
            headers=self._headers(),
            json={"properties": {name: {"checkbox": {}}}},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def add_number_property(self, name):
        """Add (or convert an existing column to) a plain number column — used
        to mirror the dashboard's computed Score back into Notion, since a
        formula property can't be set directly via the API."""
        resp = requests.patch(
            self.NOTION_DB_URL.format(db_id=self.db_id),
            headers=self._headers(),
            json={"properties": {name: {"number": {}}}},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def remove_property(self, name):
        """Delete a column from the database schema — permanent, drops that
        column's data on every row."""
        resp = requests.patch(
            self.NOTION_DB_URL.format(db_id=self.db_id),
            headers=self._headers(),
            json={"properties": {name: None}},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def create_page(self, date_str):
        payload = {
            "parent": {"database_id": self.db_id},
            "properties": {"Date": {"date": {"start": date_str}}},
        }
        resp = requests.post(self.NOTION_PAGES_URL, headers=self._headers(), json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def patch_page(self, page_id, properties):
        resp = requests.patch(
            self.NOTION_PAGE_URL.format(page_id=page_id),
            headers=self._headers(),
            json={"properties": properties},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
