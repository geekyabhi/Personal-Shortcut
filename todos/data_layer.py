import os
import base64
import requests


class JiraDataLayer:
    def __init__(self, base_url, email, token, project):
        self.base_url = base_url
        self.email = email
        self.token = token
        self.project = project

    @classmethod
    def from_env(cls):
        return cls(
            base_url=os.environ.get("JIRA_BASE_URL", "https://abhistrike.atlassian.net"),
            email=os.environ.get("JIRA_EMAIL", ""),
            token=os.environ.get("JIRA_API_TOKEN", ""),
            project=os.environ.get("JIRA_PROJECT_KEY", "TODO"),
        )

    @property
    def is_configured(self):
        return bool(self.email and self.token)

    def _headers(self):
        encoded = base64.b64encode(f"{self.email}:{self.token}".encode()).decode()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded}",
        }

    def create_issue(self, payload):
        return requests.post(
            f"{self.base_url}/rest/api/3/issue",
            headers=self._headers(),
            json=payload,
            timeout=10,
        )

    def search_jql(self, jql, max_results=50, fields=""):
        return requests.get(
            f"{self.base_url}/rest/api/3/search/jql",
            headers=self._headers(),
            params={
                "jql": jql,
                "maxResults": max_results,
                "fields": fields,
            },
            timeout=10,
        )

    def get_issue(self, issue_key, fields=""):
        return requests.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            headers=self._headers(),
            params={"fields": fields},
            timeout=10,
        )

    def update_issue(self, issue_key, fields):
        return requests.put(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            headers=self._headers(),
            json={"fields": fields},
            timeout=10,
        )

    def delete_issue(self, issue_key):
        return requests.delete(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            headers=self._headers(),
            params={"deleteSubtasks": "true"},
            timeout=10,
        )

    def get_boards(self, project_key):
        """Agile boards for the project — a project typically has exactly one."""
        return requests.get(
            f"{self.base_url}/rest/agile/1.0/board",
            headers=self._headers(),
            params={"projectKeyOrId": project_key},
            timeout=10,
        )

    def get_sprints(self, board_id, state=None):
        params = {"maxResults": 50}
        if state:
            params["state"] = state
        return requests.get(
            f"{self.base_url}/rest/agile/1.0/board/{board_id}/sprint",
            headers=self._headers(),
            params=params,
            timeout=10,
        )

    def get_sprint_issues(self, sprint_id, fields=""):
        return requests.get(
            f"{self.base_url}/rest/agile/1.0/sprint/{sprint_id}/issue",
            headers=self._headers(),
            params={"fields": fields, "maxResults": 100},
            timeout=10,
        )

    def get_backlog_issues(self, board_id, fields=""):
        return requests.get(
            f"{self.base_url}/rest/agile/1.0/board/{board_id}/backlog",
            headers=self._headers(),
            params={"fields": fields, "maxResults": 100},
            timeout=10,
        )

    def get_board_configuration(self, board_id):
        """The board's actual column setup — names, order, and which
        statuses fall into each column — exactly as configured in Jira."""
        return requests.get(
            f"{self.base_url}/rest/agile/1.0/board/{board_id}/configuration",
            headers=self._headers(),
            timeout=10,
        )

    def get_project_statuses(self, project_key):
        return requests.get(
            f"{self.base_url}/rest/api/3/project/{project_key}/statuses",
            headers=self._headers(),
            timeout=10,
        )

    def get_project(self, project_key):
        return requests.get(
            f"{self.base_url}/rest/api/3/project/{project_key}",
            headers=self._headers(),
            timeout=10,
        )

    def get_assignable_users(self, project_key):
        return requests.get(
            f"{self.base_url}/rest/api/3/user/assignable/search",
            headers=self._headers(),
            params={"project": project_key},
            timeout=10,
        )

    def get_transitions(self, issue_key):
        return requests.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions",
            headers=self._headers(),
            timeout=10,
        )

    def do_transition(self, issue_key, transition_id):
        return requests.post(
            f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions",
            headers=self._headers(),
            json={"transition": {"id": transition_id}},
            timeout=10,
        )

    def set_assignee(self, issue_key, account_id):
        """`account_id=None` unassigns the issue — Jira requires an explicit
        null, not just an absent field."""
        return requests.put(
            f"{self.base_url}/rest/api/3/issue/{issue_key}/assignee",
            headers=self._headers(),
            json={"accountId": account_id},
            timeout=10,
        )

    def create_sprint(self, board_id, name, goal=""):
        payload = {"name": name, "originBoardId": board_id}
        if goal:
            payload["goal"] = goal
        return requests.post(
            f"{self.base_url}/rest/agile/1.0/sprint",
            headers=self._headers(),
            json=payload,
            timeout=10,
        )

    def update_sprint(self, sprint_id, **fields):
        """Partial update — Jira's Agile API uses POST (not PUT) for this,
        and only touches the fields given."""
        return requests.post(
            f"{self.base_url}/rest/agile/1.0/sprint/{sprint_id}",
            headers=self._headers(),
            json=fields,
            timeout=10,
        )

    def delete_sprint(self, sprint_id):
        return requests.delete(
            f"{self.base_url}/rest/agile/1.0/sprint/{sprint_id}",
            headers=self._headers(),
            timeout=10,
        )

    def get_fields(self):
        return requests.get(
            f"{self.base_url}/rest/api/3/field",
            headers=self._headers(),
            timeout=10,
        )

    def move_to_backlog(self, issue_keys):
        return requests.post(
            f"{self.base_url}/rest/agile/1.0/backlog/issue",
            headers=self._headers(),
            json={"issues": issue_keys},
            timeout=10,
        )

    def move_to_sprint(self, sprint_id, issue_keys):
        return requests.post(
            f"{self.base_url}/rest/agile/1.0/sprint/{sprint_id}/issue",
            headers=self._headers(),
            json={"issues": issue_keys},
            timeout=10,
        )
