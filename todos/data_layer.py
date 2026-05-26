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
