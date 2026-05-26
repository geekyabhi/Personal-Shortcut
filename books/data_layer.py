import os
import time

import requests


class BooksDataLayer:
    NOTION_VERSION = "2022-06-28"
    NOTION_DB_QUERY_URL = "https://api.notion.com/v1/databases/{db_id}/query"
    NOTION_PAGES_URL = "https://api.notion.com/v1/pages"
    NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
    CACHE_TTL = 300

    _cache: dict = {"rows": None, "ts": 0.0}

    def __init__(self, token: str, db_id: str):
        self.token = token
        self.db_id = db_id

    @classmethod
    def from_env(cls) -> "BooksDataLayer":
        return cls(
            token=os.environ.get("NOTION_TOKEN", ""),
            db_id=os.environ.get("NOTION_BOOKS_DB_ID", "752ac6b0-8422-42dc-9439-b60a411f3c3d"),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def fetch_all_books(self) -> list:
        now = time.time()
        if self._cache["rows"] is not None and now - self._cache["ts"] < self.CACHE_TTL:
            return self._cache["rows"]

        url = self.NOTION_DB_QUERY_URL.format(db_id=self.db_id)
        rows, cursor = [], None
        while True:
            body: dict = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            resp = requests.post(url, headers=self._headers(), json=body, timeout=15)
            data = resp.json()
            rows.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        self._cache["rows"] = rows
        self._cache["ts"] = now
        return rows

    def create_page(self, properties: dict) -> dict:
        resp = requests.post(
            self.NOTION_PAGES_URL,
            headers=self._headers(),
            json={"parent": {"database_id": self.db_id}, "properties": properties},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def patch_page(self, page_id: str, payload: dict) -> dict:
        url = self.NOTION_PAGE_URL.format(page_id=page_id)
        resp = requests.patch(url, headers=self._headers(), json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def bust_cache(self):
        self._cache["ts"] = 0.0


class DriveDataLayer:
    CACHE_TTL = 300

    _drive_cache: dict = {"files": None, "ts": 0.0}

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

    @classmethod
    def from_env(cls) -> "DriveDataLayer":
        return cls(
            client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
            client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            refresh_token=os.environ.get("GOOGLE_REFRESH_TOKEN", ""),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def _build_service(self):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        creds.refresh(Request())
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def list_files(self) -> list:
        now = time.time()
        if self._drive_cache["files"] is not None and now - self._drive_cache["ts"] < self.CACHE_TTL:
            return self._drive_cache["files"]

        service = self._build_service()
        files, page_token = [], None
        while True:
            resp = service.files().list(
                q="(mimeType='application/pdf' or mimeType='application/vnd.google-apps.document') and trashed=false",
                fields="nextPageToken, files(id, name, webViewLink, mimeType)",
                pageSize=100,
                pageToken=page_token,
            ).execute()

            for f in resp.get("files", []):
                files.append({
                    "id": f["id"],
                    "name": f.get("name", "Untitled"),
                    "url": f.get("webViewLink", ""),
                    "type": "pdf" if f["mimeType"] == "application/pdf" else "doc",
                })

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        files.sort(key=lambda f: f["name"].lower())
        self._drive_cache["files"] = files
        self._drive_cache["ts"] = now
        return files

    def upload_file(self, upload, folder_id: str = "") -> dict:
        import io
        from googleapiclient.http import MediaIoBaseUpload

        service = self._build_service()
        media = MediaIoBaseUpload(
            io.BytesIO(upload.read()),
            mimetype=upload.content_type or "application/octet-stream",
            resumable=False,
        )
        file_meta: dict = {"name": upload.name}
        if folder_id:
            file_meta["parents"] = [folder_id]

        drive_file = service.files().create(
            body=file_meta,
            media_body=media,
            fields="id, name, webViewLink",
        ).execute()

        self._drive_cache["ts"] = 0.0
        return drive_file
