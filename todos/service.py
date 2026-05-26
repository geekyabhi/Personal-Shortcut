from datetime import date, datetime, timezone, timedelta
from dateutil import parser as dateparser

from .data_layer import JiraDataLayer


class TodosService:
    def __init__(self, data_layer: JiraDataLayer):
        self.data_layer = data_layer

    def _parse_duedate(self, duedate_str):
        cleaned = duedate_str.replace(" at ", " ")
        parsed = dateparser.parse(cleaned, dayfirst=True)
        if parsed is None:
            raise ValueError(f"Cannot parse date: '{duedate_str}'")
        return parsed.strftime("%Y-%m-%d")

    def create_issue(self, summary, issuetype="Task", description="", duedate=""):
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

        resp = self.data_layer.create_issue(payload)

        if resp.status_code == 201:
            key = resp.json().get("key")
            return key, f"{self.data_layer.base_url}/browse/{key}"

        try:
            err = resp.json()
        except Exception:
            err = {"raw": resp.text}
        raise RuntimeError(err)

    def list_issues(self, status=""):
        status_filter = f' AND status="{status}"' if status else ""
        jql = f"project={self.data_layer.project}{status_filter} ORDER BY created DESC"

        resp = self.data_layer.search_jql(
            jql=jql,
            max_results=50,
            fields="summary,status,issuetype,priority,duedate",
        )

        if not resp.ok:
            try:
                err = resp.json()
            except Exception:
                err = {"raw": resp.text}
            raise RuntimeError(err)

        issues = []
        for issue in resp.json().get("issues", []):
            f = issue.get("fields", {})
            issues.append({
                "key":       issue["key"],
                "summary":   f.get("summary", ""),
                "status":    f.get("status", {}).get("name", ""),
                "issuetype": f.get("issuetype", {}).get("name", "Task"),
                "duedate":   f.get("duedate") or "",
                "url":       f"{self.data_layer.base_url}/browse/{issue['key']}",
            })

        return issues

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
            raise RuntimeError(resp.text)

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
