import os
import json
import base64
import requests
from django.views import View
from django.http import JsonResponse
from django.shortcuts import render

JIRA_BASE_URL  = os.environ.get("JIRA_BASE_URL", "https://abhistrike.atlassian.net")
JIRA_EMAIL     = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
JIRA_PROJECT   = os.environ.get("JIRA_PROJECT_KEY", "TODO")


def _headers():
    token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return {
        "Content-Type": "application/json",
        "Authorization": f"Basic {token}",
    }


def _configured():
    return bool(JIRA_EMAIL and JIRA_API_TOKEN)


class TodoView(View):
    def get(self, request):
        return render(request, "todos/index.html")


class CreateIssueView(View):
    def post(self, request):
        if not _configured():
            return JsonResponse({"error": "JIRA_EMAIL and JIRA_API_TOKEN must be set"}, status=500)

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        summary = body.get("summary", "").strip()
        if not summary:
            return JsonResponse({"error": "summary is required"}, status=400)

        issuetype       = body.get("issuetype", "Task")
        description_txt = body.get("description", "").strip()
        duedate         = body.get("duedate", "").strip()

        payload = {
            "fields": {
                "project":   {"key": JIRA_PROJECT},
                "summary":   summary,
                "issuetype": {"name": issuetype},
            }
        }

        if description_txt:
            payload["fields"]["description"] = {
                "type": "doc", "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description_txt}]
                }]
            }

        if duedate:
            payload["fields"]["duedate"] = duedate

        try:
            resp = requests.post(
                f"{JIRA_BASE_URL}/rest/api/3/issue",
                headers=_headers(),
                json=payload,
                timeout=10,
            )
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)

        if resp.status_code == 201:
            key = resp.json().get("key")
            return JsonResponse(
                {"key": key, "url": f"{JIRA_BASE_URL}/browse/{key}"},
                status=201,
            )

        try:
            err = resp.json()
        except Exception:
            err = {"raw": resp.text}
        return JsonResponse({"error": err}, status=resp.status_code)


class ListIssuesView(View):
    def get(self, request):
        if not _configured():
            return JsonResponse({"error": "JIRA_EMAIL and JIRA_API_TOKEN must be set"}, status=500)

        status = request.GET.get("status", "")
        status_filter = f' AND status="{status}"' if status else ""
        jql = f"project={JIRA_PROJECT}{status_filter} ORDER BY created DESC"
        try:
            resp = requests.get(
                f"{JIRA_BASE_URL}/rest/api/3/search/jql",
                headers=_headers(),
                params={
                    "jql": jql,
                    "maxResults": 50,
                    "fields": "summary,status,issuetype,priority,duedate",
                },
                timeout=10,
            )
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)

        if not resp.ok:
            try:
                err = resp.json()
            except Exception:
                err = {"raw": resp.text}
            return JsonResponse({"error": err}, status=resp.status_code)

        issues = []
        for issue in resp.json().get("issues", []):
            f = issue.get("fields", {})
            issues.append({
                "key":       issue["key"],
                "summary":   f.get("summary", ""),
                "status":    f.get("status", {}).get("name", ""),
                "issuetype": f.get("issuetype", {}).get("name", "Task"),
                "duedate":   f.get("duedate") or "",
                "url":       f"{JIRA_BASE_URL}/browse/{issue['key']}",
            })

        return JsonResponse({"issues": issues})
