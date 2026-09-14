from datetime import date, datetime, timezone, timedelta
from dateutil import parser as dateparser

from .data_layer import JiraDataLayer


def _extract_error(resp):
    content_type = resp.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            return resp.json()
        except ValueError:
            pass
    return {"message": f"Jira returned an unexpected response (status {resp.status_code}). It may be temporarily unavailable."}


class TodosService:
    def __init__(self, data_layer: JiraDataLayer):
        self.data_layer = data_layer

    def _parse_duedate(self, duedate_str):
        cleaned = duedate_str.replace(" at ", " ")
        parsed = dateparser.parse(cleaned, dayfirst=True)
        if parsed is None:
            raise ValueError(f"Cannot parse date: '{duedate_str}'")
        return parsed.strftime("%Y-%m-%d")

    def create_issue(self, summary, issuetype="Task", description="", duedate="", assignee_account_id="", parent_key=""):
        if issuetype == "Subtask" and not parent_key:
            raise ValueError("A Subtask needs a parent")

        payload = {
            "fields": {
                "project":   {"key": self.data_layer.project},
                "summary":   summary,
                "issuetype": {"name": issuetype},
            }
        }

        if description:
            payload["fields"]["description"] = {
                "type": "doc", "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}],
                }],
            }

        if duedate:
            payload["fields"]["duedate"] = self._parse_duedate(duedate)

        if parent_key:
            payload["fields"]["parent"] = {"key": parent_key}

        if assignee_account_id:
            payload["fields"]["assignee"] = {"accountId": assignee_account_id}

        resp = self.data_layer.create_issue(payload)

        if resp.status_code == 201:
            key = resp.json().get("key")
            return key, f"{self.data_layer.base_url}/browse/{key}"

        raise RuntimeError(_extract_error(resp))

    def list_issues(self, status=""):
        status_filter = f' AND status="{status}"' if status else ""
        jql = f"project={self.data_layer.project}{status_filter} ORDER BY created DESC"

        resp = self.data_layer.search_jql(
            jql=jql,
            max_results=50,
            fields="summary,status,issuetype,priority,duedate,parent",
        )

        if not resp.ok:
            raise RuntimeError(_extract_error(resp))

        issues = []
        for issue in resp.json().get("issues", []):
            f = issue.get("fields", {})
            parent = f.get("parent") or {}
            issues.append({
                "key":            issue["key"],
                "summary":        f.get("summary", ""),
                "status":         f.get("status", {}).get("name", ""),
                "issuetype":      f.get("issuetype", {}).get("name", "Task"),
                "duedate":        f.get("duedate") or "",
                "parent_key":     parent.get("key", ""),
                "parent_summary": (parent.get("fields") or {}).get("summary", ""),
                "url":            f"{self.data_layer.base_url}/browse/{issue['key']}",
            })

        return issues

    def _board_id(self):
        resp = self.data_layer.get_boards(self.data_layer.project)
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        boards = resp.json().get("values", [])
        if not boards:
            raise RuntimeError({"message": "No Jira board found for this project"})
        return boards[0]["id"]

    def _board_columns(self, board_id):
        """The board's actual columns, in Jira's own order — e.g. To Do / In
        Progress / Done / Blocked — each mapped to the exact status name(s)
        it contains. Built from the live board config rather than status
        category, since a status's category doesn't always match its
        column (this project's "Blocked" status is miscategorized as
        "done", for instance)."""
        cfg_resp = self.data_layer.get_board_configuration(board_id)
        if not cfg_resp.ok:
            raise RuntimeError(_extract_error(cfg_resp))
        columns_cfg = cfg_resp.json().get("columnConfig", {}).get("columns", [])

        statuses_resp = self.data_layer.get_project_statuses(self.data_layer.project)
        if not statuses_resp.ok:
            raise RuntimeError(_extract_error(statuses_resp))
        id_to_name = {}
        for it in statuses_resp.json():
            for s in it.get("statuses", []):
                id_to_name[s["id"]] = s["name"]

        columns = []
        for col in columns_cfg:
            names = [id_to_name[s["id"]] for s in col.get("statuses", []) if s["id"] in id_to_name]
            if names:
                columns.append({"name": col.get("name") or names[0], "statuses": names})
        return columns

    @staticmethod
    def _parse_sprint_issues(raw_issues):
        issues = []
        for issue in raw_issues:
            f = issue.get("fields", {})
            status = f.get("status", {})
            assignee = f.get("assignee") or {}
            parent = f.get("parent") or {}
            issues.append({
                "key":             issue["key"],
                "summary":         f.get("summary", ""),
                "status":          status.get("name", ""),
                "status_category": status.get("statusCategory", {}).get("key", "new"),
                "issuetype":       f.get("issuetype", {}).get("name", "Task"),
                "priority":        (f.get("priority") or {}).get("name", ""),
                "duedate":         f.get("duedate") or "",
                "assignee":        assignee.get("displayName", ""),
                "assignee_id":     assignee.get("accountId", ""),
                "parent_key":      parent.get("key", ""),
                "parent_summary":  (parent.get("fields") or {}).get("summary", ""),
            })
        return issues

    def get_active_sprint(self, sprint_id=None):
        """One board view: a specific sprint (`sprint_id` given), the
        backlog (`sprint_id == "backlog"`), or — with nothing given —
        whichever sprint is active, falling back to the next future one.
        Always includes the full sprint list so the UI can offer a
        switcher regardless of which view is showing."""
        board_id = self._board_id()
        columns = self._board_columns(board_id)

        sprints_resp = self.data_layer.get_sprints(board_id)
        if not sprints_resp.ok:
            raise RuntimeError(_extract_error(sprints_resp))
        raw_sprints = sprints_resp.json().get("values", [])

        order = {"active": 0, "future": 1, "closed": 2}
        all_sprints = sorted(
            [
                {
                    "id": s["id"],
                    "name": s.get("name", ""),
                    "state": s.get("state", ""),
                    "start_date": s.get("startDate", ""),
                    "end_date": s.get("endDate", ""),
                    "goal": s.get("goal", ""),
                }
                for s in raw_sprints
            ],
            key=lambda s: (order.get(s["state"], 3), -s["id"]),
        )

        def build(sprint_meta, issues):
            for i in issues:
                i["url"] = f"{self.data_layer.base_url}/browse/{i['key']}"
            return {
                "sprint": sprint_meta,
                "columns": columns,
                "issues": issues,
                "all_sprints": all_sprints,
                "board_id": board_id,
            }

        if sprint_id == "backlog":
            resp = self.data_layer.get_backlog_issues(
                board_id, fields="summary,status,issuetype,priority,duedate,assignee,parent"
            )
            if not resp.ok:
                raise RuntimeError(_extract_error(resp))
            sprint_meta = {"id": None, "name": "Backlog", "state": "backlog", "start_date": "", "end_date": "", "goal": ""}
            return build(sprint_meta, self._parse_sprint_issues(resp.json().get("issues", [])))

        if sprint_id:
            full = next((s for s in raw_sprints if str(s["id"]) == str(sprint_id)), None)
            if not full:
                raise ValueError(f"Sprint {sprint_id} not found")
        else:
            active = [s for s in raw_sprints if s.get("state") == "active"]
            future = [s for s in raw_sprints if s.get("state") == "future"]
            if active:
                full = active[0]
            elif future:
                full = future[0]
            else:
                return build(None, [])

        issues_resp = self.data_layer.get_sprint_issues(
            full["id"], fields="summary,status,issuetype,priority,duedate,assignee,parent"
        )
        if not issues_resp.ok:
            raise RuntimeError(_extract_error(issues_resp))

        sprint_meta = {
            "id":         full["id"],
            "name":       full.get("name", ""),
            "state":      full.get("state", ""),
            "start_date": full.get("startDate", ""),
            "end_date":   full.get("endDate", ""),
            "goal":       full.get("goal", ""),
        }
        return build(sprint_meta, self._parse_sprint_issues(issues_resp.json().get("issues", [])))

    def move_issue(self, issue_key, target_status):
        """Transition an issue to `target_status` — the drag-and-drop
        backing call. Only succeeds if the issue's workflow has a direct
        transition to that status from wherever it is now."""
        resp = self.data_layer.get_transitions(issue_key)
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        transitions = resp.json().get("transitions", [])
        match = next(
            (t for t in transitions if t.get("to", {}).get("name", "").lower() == target_status.lower()),
            None,
        )
        if not match:
            raise ValueError(f'"{issue_key}" has no direct transition to "{target_status}"')

        do_resp = self.data_layer.do_transition(issue_key, match["id"])
        if not do_resp.ok:
            raise RuntimeError(_extract_error(do_resp))
        return {"key": issue_key, "status": target_status}

    def set_assignee(self, issue_key, account_id):
        resp = self.data_layer.set_assignee(issue_key, account_id or None)
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        return {"key": issue_key, "account_id": account_id or None}

    def get_issue_types(self):
        resp = self.data_layer.get_project(self.data_layer.project)
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        return [{"id": t["id"], "name": t["name"]} for t in resp.json().get("issueTypes", [])]

    def get_issue_type_levels(self):
        """Jira's parent-child hierarchy level per issue type (Epic=1,
        Story/Task/etc=0, Subtask=-1 in this project). A ticket's parent
        must be exactly one level above it — Jira enforces this itself, but
        without this the Parent dropdown can't know which candidates are
        actually valid ahead of time."""
        resp = self.data_layer.get_project(self.data_layer.project)
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        return {t["name"]: t.get("hierarchyLevel", 0) for t in resp.json().get("issueTypes", [])}

    def get_assignees(self):
        resp = self.data_layer.get_assignable_users(self.data_layer.project)
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        return [
            {"account_id": u["accountId"], "display_name": u.get("displayName", "")}
            for u in resp.json()
        ]

    def get_parentable_issues(self):
        """Every issue that could sensibly be picked as a parent — anything
        but a subtask — for the detail modal's Parent list. Subtasks are
        excluded since Jira doesn't allow a subtask to parent anything."""
        jql = f"project={self.data_layer.project} AND issuetype != Subtask ORDER BY created DESC"
        resp = self.data_layer.search_jql(jql=jql, max_results=100, fields="summary,issuetype")
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        return [
            {
                "key": i["key"],
                "summary": i.get("fields", {}).get("summary", ""),
                "issuetype": i.get("fields", {}).get("issuetype", {}).get("name", "Task"),
            }
            for i in resp.json().get("issues", [])
        ]

    def get_meta(self):
        """Everything the create-issue form and issue detail modal need to
        populate their dropdowns, fetched fresh from Jira rather than
        hardcoded."""
        board_id = self._board_id()
        columns = self._board_columns(board_id)
        statuses = [name for col in columns for name in col["statuses"]]
        return {
            "issue_types": self.get_issue_types(),
            "assignees": self.get_assignees(),
            "parentable_issues": self.get_parentable_issues(),
            "issue_type_levels": self.get_issue_type_levels(),
            "sprints": self.get_available_sprints(),
            "statuses": statuses,
        }

    @staticmethod
    def _adf_to_text(adf):
        """Flatten an Atlassian Document Format description into plain text
        — lossy, but matches the single-paragraph description this app
        writes back on save."""
        if not adf:
            return ""
        if isinstance(adf, str):
            return adf

        parts = []

        def walk(node):
            if not isinstance(node, dict):
                return
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            for child in node.get("content") or []:
                walk(child)
            if node.get("type") in ("paragraph", "heading"):
                parts.append("\n")

        for block in adf.get("content") or []:
            walk(block)
        return "".join(parts).strip()

    def _sprint_field_id(self):
        """Resolve the Sprint custom field's id by its schema type rather
        than hardcoding "customfield_10020" — that id isn't guaranteed to
        be stable across projects or Jira sites."""
        resp = self.data_layer.get_fields()
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        for f in resp.json():
            if f.get("schema", {}).get("custom") == "com.pyxis.greenhopper.jira:gh-sprint":
                return f["id"]
        return None

    def get_issue_detail(self, issue_key):
        sprint_field = self._sprint_field_id()
        fields = "summary,description,status,issuetype,priority,duedate,assignee,parent"
        if sprint_field:
            fields += f",{sprint_field}"

        resp = self.data_layer.get_issue(issue_key, fields=fields)
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))

        f = resp.json().get("fields", {})
        status = f.get("status", {})
        assignee = f.get("assignee") or {}
        parent = f.get("parent") or {}

        sprint_id, sprint_name = None, "Backlog"
        sprints = f.get(sprint_field) if sprint_field else None
        if sprints:
            chosen = next((s for s in sprints if s.get("state") == "active"), sprints[-1])
            sprint_id, sprint_name = chosen.get("id"), chosen.get("name", "")

        return {
            "key":             issue_key,
            "summary":         f.get("summary", ""),
            "description":     self._adf_to_text(f.get("description")),
            "status":          status.get("name", ""),
            "issuetype":       f.get("issuetype", {}).get("name", "Task"),
            "priority":        (f.get("priority") or {}).get("name", ""),
            "duedate":         f.get("duedate") or "",
            "assignee_id":     assignee.get("accountId", ""),
            "assignee_name":   assignee.get("displayName", ""),
            "parent_key":      parent.get("key", ""),
            "parent_summary":  (parent.get("fields") or {}).get("summary", ""),
            "sprint_id":       sprint_id,
            "sprint_name":     sprint_name,
            "url":             f"{self.data_layer.base_url}/browse/{issue_key}",
        }

    def get_available_sprints(self):
        """Active and future sprints on the board, for the detail modal's
        Sprint picker — closed sprints are left out since moving a ticket
        into one isn't a normal action."""
        board_id = self._board_id()
        resp = self.data_layer.get_sprints(board_id)
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        return [
            {"id": s["id"], "name": s.get("name", ""), "state": s.get("state", "")}
            for s in resp.json().get("values", [])
            if s.get("state") in ("active", "future")
        ]

    def set_issue_sprint(self, issue_key, sprint_id):
        """`sprint_id=None` moves the ticket to the backlog; otherwise into
        that sprint. Two different Jira endpoints, not a plain field edit."""
        if sprint_id:
            resp = self.data_layer.move_to_sprint(sprint_id, [issue_key])
        else:
            resp = self.data_layer.move_to_backlog([issue_key])
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        return {"key": issue_key, "sprint_id": sprint_id}

    def update_issue(self, issue_key, summary, description, duedate, issuetype, parent_key):
        """Full replace of the editable fields shown in the detail modal —
        the modal always sends back its whole current state, so there's no
        partial-update ambiguity. Status and assignee are handled by their
        own endpoints (transitions and assignment have different Jira
        semantics from a plain field edit)."""
        if not summary:
            raise ValueError("Summary is required")

        fields = {
            "summary": summary,
            "issuetype": {"name": issuetype},
            "description": (
                {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
                }
                if description else None
            ),
            "duedate": self._parse_duedate(duedate) if duedate else None,
            "parent": {"key": parent_key} if parent_key else None,
        }

        resp = self.data_layer.update_issue(issue_key, fields)
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        return {"key": issue_key, "updated": True}

    def delete_issue(self, issue_key):
        """Permanently deletes the issue — and, since we always pass
        deleteSubtasks, any of its subtasks too. Jira gives no undo."""
        resp = self.data_layer.delete_issue(issue_key)
        if resp.status_code != 204:
            raise RuntimeError(_extract_error(resp))
        return {"key": issue_key, "deleted": True}

    def create_and_start_sprint(self, name, duration_days=7, goal="", start_date="", end_date=""):
        """Create a new sprint on the board and start it immediately (Jira
        creates sprints in the "future" state; starting one requires a
        separate update with dates). `start_date`/`end_date` (YYYY-MM-DD)
        take priority when given; `duration_days` from today is the
        fallback for callers that don't care about exact dates."""
        # Resolve and validate dates before touching Jira at all — creating
        # the sprint first and validating after would leave a dangling,
        # never-started sprint behind on a bad date range.
        if start_date:
            start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        else:
            start = datetime.now(timezone.utc)

        if end_date:
            end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        else:
            end = start + timedelta(days=duration_days)

        if end <= start:
            raise ValueError("End date must be after the start date")

        board_id = self._board_id()

        create_resp = self.data_layer.create_sprint(board_id, name, goal=goal)
        if create_resp.status_code != 201:
            raise RuntimeError(_extract_error(create_resp))
        sprint_id = create_resp.json()["id"]

        update_fields = {
            "state": "active",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
        }
        if goal:
            update_fields["goal"] = goal

        update_resp = self.data_layer.update_sprint(sprint_id, **update_fields)
        if not update_resp.ok:
            raise RuntimeError(_extract_error(update_resp))

        return {"id": sprint_id, "name": name, "state": "active"}

    def close_sprint(self, sprint_id):
        resp = self.data_layer.update_sprint(sprint_id, state="closed")
        if not resp.ok:
            raise RuntimeError(_extract_error(resp))
        return {"id": sprint_id, "state": "closed"}

    def delete_sprint(self, sprint_id):
        """Deletes the sprint itself — its issues aren't deleted, they just
        fall back to the backlog. No undo."""
        resp = self.data_layer.delete_sprint(sprint_id)
        if resp.status_code != 204:
            raise RuntimeError(_extract_error(resp))
        return {"id": sprint_id, "deleted": True}

    def get_due_summary(self):
        jql = (
            f"project={self.data_layer.project} "
            f"AND duedate is not EMPTY "
            f"AND status != Done "
            f"ORDER BY duedate ASC"
        )

        resp = self.data_layer.search_jql(
            jql=jql,
            max_results=50,
            fields="summary,status,duedate",
        )

        if not resp.ok:
            raise RuntimeError(_extract_error(resp))

        now = datetime.now(timezone.utc)
        today = now.date()
        hour_from_now = now + timedelta(hours=1)

        overdue = []
        due_next_hour = []
        due_today = []
        due_soon = []
        upcoming = []

        for issue in resp.json().get("issues", []):
            f = issue.get("fields", {})
            raw_due = f.get("duedate")
            if not raw_due:
                continue
            due = date.fromisoformat(raw_due)
            diff = (due - today).days
            item = f"{issue['key']}: {f.get('summary', '')}"

            if diff < 0:
                overdue.append((abs(diff), item))
            elif diff == 0:
                if hour_from_now.date() > today:
                    due_next_hour.append(item)
                else:
                    due_today.append(item)
            elif diff <= 3:
                due_soon.append((diff, item))
            else:
                upcoming.append((diff, item))

        lines = []
        total = len(overdue) + len(due_next_hour) + len(due_today) + len(due_soon) + len(upcoming)

        if total == 0:
            lines.append("No due todos. All clear!")
        else:
            lines.append(f"{total} todo(s) with due dates:\n")

            if overdue:
                lines.append(f"OVERDUE ({len(overdue)})")
                for days, item in sorted(overdue, reverse=True):
                    lines.append(f"  - {item}  [{days}d overdue]")

            if due_next_hour:
                lines.append(f"\nDUE IN NEXT 1 HOUR ({len(due_next_hour)})")
                for item in due_next_hour:
                    lines.append(f"  - {item}")

            if due_today:
                lines.append(f"\nDUE TODAY ({len(due_today)})")
                for item in due_today:
                    lines.append(f"  - {item}")

            if due_soon:
                lines.append(f"\nDUE SOON — next 3 days ({len(due_soon)})")
                for days, item in sorted(due_soon):
                    lines.append(f"  - {item}  [in {days}d]")

            if upcoming:
                lines.append(f"\nUPCOMING ({len(upcoming)})")
                for days, item in sorted(upcoming):
                    lines.append(f"  - {item}  [in {days}d]")

        return {
            "total":         total,
            "overdue":       [i for _, i in overdue],
            "due_next_hour": due_next_hour,
            "due_today":     due_today,
            "due_soon":      [i for _, i in due_soon],
            "upcoming":      [i for _, i in upcoming],
            "text":          "\n".join(lines),
        }
