import os
import json
import base64
import requests
from django.views import View
from django.http import JsonResponse
from django.shortcuts import render

def _conf():
    return {
        "base_url":  os.environ.get("JIRA_BASE_URL", "https://abhistrike.atlassian.net"),
        "email":     os.environ.get("JIRA_EMAIL", ""),
        "token":     os.environ.get("JIRA_API_TOKEN", ""),
        "project":   os.environ.get("JIRA_PROJECT_KEY", "TODO"),
    }


def _headers(conf):
    encoded = base64.b64encode(f"{conf['email']}:{conf['token']}".encode()).decode()
    return {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded}",
    }


def _configured(conf):
    return bool(conf["email"] and conf["token"])


class TodoView(View):
    def get(self, request):
        return render(request, "todos/index.html")


class CreateIssueView(View):
    def post(self, request):
        conf = _conf()
        if not _configured(conf):
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
                "project":   {"key": conf["project"]},
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
                f"{conf['base_url']}/rest/api/3/issue",
                headers=_headers(conf),
                json=payload,
                timeout=10,
            )
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)

        if resp.status_code == 201:
            key = resp.json().get("key")
            return JsonResponse(
                {"key": key, "url": f"{conf['base_url']}/browse/{key}"},
                status=201,
            )

        try:
            err = resp.json()
        except Exception:
            err = {"raw": resp.text}
        return JsonResponse({"error": err}, status=resp.status_code)


class ListIssuesView(View):
    def get(self, request):
        conf = _conf()
        if not _configured(conf):
            return JsonResponse({"error": "JIRA_EMAIL and JIRA_API_TOKEN must be set"}, status=500)

        status = request.GET.get("status", "")
        status_filter = f' AND status="{status}"' if status else ""
        jql = f"project={conf['project']}{status_filter} ORDER BY created DESC"
        try:
            resp = requests.get(
                f"{conf['base_url']}/rest/api/3/search/jql",
                headers=_headers(conf),
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
                "url":       f"{conf['base_url']}/browse/{issue['key']}",
            })

        return JsonResponse({"issues": issues})
