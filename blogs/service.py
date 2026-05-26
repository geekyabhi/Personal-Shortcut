from .data_layer import BlogsDataLayer


class BlogsService:
    READ_STATUS_ORDER = ["Reading", "To Read", "Read"]
    WRITE_STATUS_ORDER = ["Draft", "To Write", "Written", "Published"]

    def __init__(self, data_layer: BlogsDataLayer):
        self.data_layer = data_layer
        self.read_db_id = data_layer.read_db_id
        self.write_db_id = data_layer.write_db_id

    def _row_to_read_blog(self, row):
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

    def _row_to_write_blog(self, row):
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

    def get_stats(self):
        read_rows = self.data_layer.fetch_read_blogs()
        write_rows = self.data_layer.fetch_write_blogs()

        read_status, write_status = {}, {}
        for b in [self._row_to_read_blog(r) for r in read_rows]:
            s = b["status"] or "Unknown"
            read_status[s] = read_status.get(s, 0) + 1
        for b in [self._row_to_write_blog(r) for r in write_rows]:
            s = b["status"] or "Unknown"
            write_status[s] = write_status.get(s, 0) + 1

        return {
            "read_total": len(read_rows),
            "read_status": read_status,
            "write_total": len(write_rows),
            "write_status": write_status,
        }

    def list_read(self, status="", q=""):
        rows = self.data_layer.fetch_read_blogs()
        blogs = [self._row_to_read_blog(r) for r in rows]

        if status:
            blogs = [b for b in blogs if b["status"] == status]
        if q:
            blogs = [b for b in blogs if q in b["topic"].lower()]

        blogs.sort(key=lambda b: (
            self.READ_STATUS_ORDER.index(b["status"]) if b["status"] in self.READ_STATUS_ORDER else 99,
            b["topic"].lower(),
        ))
        return {"blogs": blogs, "total": len(blogs)}

    def list_write(self, status="", q=""):
        rows = self.data_layer.fetch_write_blogs()
        blogs = [self._row_to_write_blog(r) for r in rows]

        if status:
            blogs = [b for b in blogs if b["status"] == status]
        if q:
            blogs = [b for b in blogs if q in b["topic"].lower()]

        blogs.sort(key=lambda b: (
            self.WRITE_STATUS_ORDER.index(b["status"]) if b["status"] in self.WRITE_STATUS_ORDER else 99,
            b["topic"].lower(),
        ))
        return {"blogs": blogs, "total": len(blogs)}

    def create_read(self, topic, status, url):
        topic = topic.strip()
        if not topic:
            raise ValueError("Topic is required")

        properties = {
            "Topic": {"title": [{"text": {"content": topic}}]},
            "Status": {"select": {"name": status or "To Read"}},
        }
        url = (url or "").strip()
        if url:
            properties["Resource"] = {"rich_text": [{"text": {"content": url}}]}

        data = self.data_layer.create_page(self.read_db_id, properties)
        self.data_layer.bust_read_cache()
        return data.get("id", "")

    def create_write(self, topic, status, url):
        topic = topic.strip()
        if not topic:
            raise ValueError("Topic is required")

        properties = {
            "Topic": {"title": [{"text": {"content": topic}}]},
            "Status": {"select": {"name": status or "To Write"}},
        }
        url = (url or "").strip()
        if url:
            properties["URL"] = {"url": url}

        data = self.data_layer.create_page(self.write_db_id, properties)
        self.data_layer.bust_write_cache()
        return data.get("id", "")

    def update_read(self, page_id, body):
        properties = {}
        if "topic" in body:
            topic = body["topic"].strip()
            if not topic:
                raise ValueError("Topic required")
            properties["Topic"] = {"title": [{"text": {"content": topic}}]}
        if "status" in body:
            properties["Status"] = {"select": {"name": body["status"]}}
        if "url" in body:
            properties["Resource"] = {"rich_text": [{"text": {"content": body["url"].strip()}}]}

        if not properties:
            raise ValueError("Nothing to update")

        self.data_layer.patch_page(page_id, {"properties": properties})
        self.data_layer.bust_read_cache()

    def update_write(self, page_id, body):
        properties = {}
        if "topic" in body:
            topic = body["topic"].strip()
            if not topic:
                raise ValueError("Topic required")
            properties["Topic"] = {"title": [{"text": {"content": topic}}]}
        if "status" in body:
            properties["Status"] = {"select": {"name": body["status"]}}
        if "url" in body:
            url = body["url"].strip()
            properties["URL"] = {"url": url if url else None}

        if not properties:
            raise ValueError("Nothing to update")

        self.data_layer.patch_page(page_id, {"properties": properties})
        self.data_layer.bust_write_cache()

    def delete_read(self, page_id):
        self.data_layer.patch_page(page_id, {"archived": True})
        self.data_layer.bust_read_cache()

    def delete_write(self, page_id):
        self.data_layer.patch_page(page_id, {"archived": True})
        self.data_layer.bust_write_cache()

    def bust_cache(self):
        self.data_layer.bust_read_cache()
        self.data_layer.bust_write_cache()
