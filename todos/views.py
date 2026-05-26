import json
import requests
from django.views import View
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render

from .data_layer import JiraDataLayer
from .service import TodosService


class TodosBaseView(View):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        data_layer = JiraDataLayer.from_env()
        if data_layer.is_configured:
            self.service = TodosService(data_layer)
        else:
            self.service = None

    def _creds_error_json(self):
        return JsonResponse(
            {"error": "JIRA_EMAIL and JIRA_API_TOKEN must be set"},
            status=500,
        )

    def _creds_error_text(self):
        return HttpResponse(
            "JIRA_EMAIL and JIRA_API_TOKEN must be set",
            status=500,
            content_type="text/plain",
        )


class TodoView(View):
    def get(self, request):
        return render(request, "todos/index.html")


class CreateIssueView(TodosBaseView):
    def post(self, request):
        if self.service is None:
            return self._creds_error_json()

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        summary = body.get("summary", "").strip()
        if not summary:
            return JsonResponse({"error": "summary is required"}, status=400)

        issuetype = body.get("issuetype", "Task")
        description = body.get("description", "").strip()
        duedate = body.get("duedate", "").strip()

        try:
            key, url = self.service.create_issue(
                summary=summary,
                issuetype=issuetype,
                description=description,
                duedate=duedate,
            )
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            return JsonResponse({"error": e.args[0]}, status=502)

        return JsonResponse({"key": key, "url": url}, status=201)


class ListIssuesView(TodosBaseView):
    def get(self, request):
        if self.service is None:
            return self._creds_error_json()

        status = request.GET.get("status", "")

        try:
            issues = self.service.list_issues(status=status)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            if isinstance(err, dict):
                status_code = err.get("status", 502)
            else:
                status_code = 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse({"issues": issues})


class DueSummaryView(TodosBaseView):
    def get(self, request):
        if self.service is None:
            return self._creds_error_text()

        try:
            summary = self.service.get_due_summary()
        except requests.RequestException as e:
            return HttpResponse(str(e), status=502, content_type="text/plain")
        except RuntimeError as e:
            return HttpResponse(str(e.args[0]), status=502, content_type="text/plain")

        fmt = request.GET.get("format", "text")
        if fmt == "json":
            return JsonResponse(summary)

        return HttpResponse(summary["text"], content_type="text/plain")
