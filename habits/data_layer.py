import os

import requests

NOTION_PAGES_URL = "https://api.notion.com/v1/pages"
NOTION_DB_QUERY_URL = "https://api.notion.com/v1/databases/{db_id}/query"
NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{page_id}"
NOTION_VERSION = "2022-06-28"


def get_creds():
    return os.environ.get("NOTION_TOKEN"), os.environ.get("NOTION_HABITS_DB_ID")


def get_notion_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def fetch_all_rows(token, db_id, notion_filter=None):
    url = NOTION_DB_QUERY_URL.format(db_id=db_id)
    payload = {}
    if notion_filter:
        payload["filter"] = notion_filter
    rows = []
    has_more = True
    while has_more:
        resp = requests.post(url, headers=get_notion_headers(token), json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        if has_more:
            payload["start_cursor"] = data["next_cursor"]
    return rows


def create_page(token, db_id, date_str):
    payload = {
        "parent": {"database_id": db_id},
        "properties": {"Date": {"date": {"start": date_str}}},
    }
    resp = requests.post(NOTION_PAGES_URL, headers=get_notion_headers(token), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def patch_page(token, page_id, properties):
    resp = requests.patch(
        NOTION_PAGE_URL.format(page_id=page_id),
        headers=get_notion_headers(token),
        json={"properties": properties},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
