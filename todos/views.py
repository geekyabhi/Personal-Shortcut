import os
import json
import base64
import requests
from datetime import date, datetime, timezone, timedelta
from dateutil import parser as dateparser
from django.views import View
from django.http import JsonResponse, HttpResponse
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
            try:
                cleaned = duedate.replace(" at ", " ")
                parsed  = dateparser.parse(cleaned, dayfirst=True)
                payload["fields"]["duedate"] = parsed.strftime("%Y-%m-%d")
            except (ValueError, OverflowError, TypeError):
                return JsonResponse({"error": f"Cannot parse date: '{duedate}'"}, status=400)

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


class DueSummaryView(View):
    def get(self, request):
        conf = _conf()
        if not _configured(conf):
            return HttpResponse("JIRA_EMAIL and JIRA_API_TOKEN must be set", status=500, content_type="text/plain")

        jql = (
            f"project={conf['project']} "
            f"AND duedate is not EMPTY "
            f"AND status != Done "
            f"ORDER BY duedate ASC"
        )
        try:
            resp = requests.get(
                f"{conf['base_url']}/rest/api/3/search/jql",
                headers=_headers(conf),
                params={"jql": jql, "maxResults": 50, "fields": "summary,status,duedate"},
                timeout=10,
            )
        except requests.RequestException as e:
            return HttpResponse(str(e), status=502, content_type="text/plain")

        if not resp.ok:
            return HttpResponse(resp.text, status=resp.status_code, content_type="text/plain")

        now       = datetime.now(timezone.utc)
        today     = now.date()
        hour_from_now = now + timedelta(hours=1)

        overdue      = []
        due_next_hour = []
        due_today    = []
        due_soon     = []
        upcoming     = []

        for issue in resp.json().get("issues", []):
            f       = issue.get("fields", {})
            raw_due = f.get("duedate")
            if not raw_due:
                continue
            due  = date.fromisoformat(raw_due)
            diff = (due - today).days
            item = f"{issue['key']}: {f.get('summary', '')}"

            if diff < 0:
                overdue.append((abs(diff), item))
            elif diff == 0:
                # Jira has no time on duedate; treat as end-of-day.
                # If we're within 1 hour of midnight (i.e. hour >= 23), flag as next-hour.
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

        fmt = request.GET.get("format", "text")
        if fmt == "json":
            return JsonResponse({
                "total":          total,
                "overdue":        [i for _, i in overdue],
                "due_next_hour":  due_next_hour,
                "due_today":      due_today,
                "due_soon":       [i for _, i in due_soon],
                "upcoming":       [i for _, i in upcoming],
                "text":           "\n".join(lines),
            })

        return HttpResponse("\n".join(lines), content_type="text/plain")
