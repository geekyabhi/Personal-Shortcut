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


class ChartsView(View):
    def get(self, request):
        return render(request, "todos/charts.html")


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
        assignee_account_id = body.get("assignee_account_id", "").strip()
        parent_key = (body.get("parent_key") or "").strip()

        try:
            key, url = self.service.create_issue(
                summary=summary,
                issuetype=issuetype,
                description=description,
                duedate=duedate,
                assignee_account_id=assignee_account_id,
                parent_key=parent_key,
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


class SprintView(TodosBaseView):
    def get(self, request):
        if self.service is None:
            return self._creds_error_json()

        try:
            data = self.service.get_active_sprint(sprint_id=request.GET.get("sprint_id", "") or None)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(data)


class IssueTransitionView(TodosBaseView):
    def post(self, request, key):
        if self.service is None:
            return self._creds_error_json()

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        target_status = body.get("status", "").strip()
        if not target_status:
            return JsonResponse({"error": "status is required"}, status=400)

        try:
            result = self.service.move_issue(key, target_status)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(result)


class IssueAssigneeView(TodosBaseView):
    def post(self, request, key):
        if self.service is None:
            return self._creds_error_json()

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        try:
            result = self.service.set_assignee(key, body.get("account_id", ""))
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(result)


class IssueSprintView(TodosBaseView):
    def post(self, request, key):
        if self.service is None:
            return self._creds_error_json()

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        sprint_id = body.get("sprint_id") or None

        try:
            result = self.service.set_issue_sprint(key, sprint_id)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(result)


class SprintCloseView(TodosBaseView):
    def post(self, request):
        if self.service is None:
            return self._creds_error_json()

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        sprint_id = body.get("sprint_id")
        if not sprint_id:
            return JsonResponse({"error": "sprint_id is required"}, status=400)

        try:
            result = self.service.close_sprint(sprint_id)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(result)


class SprintDeleteView(TodosBaseView):
    def post(self, request):
        if self.service is None:
            return self._creds_error_json()

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        sprint_id = body.get("sprint_id")
        if not sprint_id:
            return JsonResponse({"error": "sprint_id is required"}, status=400)

        try:
            result = self.service.delete_sprint(sprint_id)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(result)


class SprintCreateView(TodosBaseView):
    def post(self, request):
        if self.service is None:
            return self._creds_error_json()

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        name = body.get("name", "").strip()
        if not name:
            return JsonResponse({"error": "name is required"}, status=400)

        try:
            duration_days = int(body.get("duration_days") or 7)
        except (TypeError, ValueError):
            return JsonResponse({"error": "duration_days must be a number"}, status=400)
        goal = body.get("goal", "").strip()
        start_date = (body.get("start_date") or "").strip()
        end_date = (body.get("end_date") or "").strip()

        try:
            result = self.service.create_and_start_sprint(
                name, duration_days, goal, start_date=start_date, end_date=end_date
            )
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(result, status=201)


class MetaView(TodosBaseView):
    def get(self, request):
        if self.service is None:
            return self._creds_error_json()

        try:
            data = self.service.get_meta()
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(data)


class IssueDetailView(TodosBaseView):
    def get(self, request, key):
        if self.service is None:
            return self._creds_error_json()

        try:
            data = self.service.get_issue_detail(key)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(data)


class IssueUpdateView(TodosBaseView):
    def post(self, request, key):
        if self.service is None:
            return self._creds_error_json()

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        try:
            result = self.service.update_issue(
                key,
                summary=body.get("summary", "").strip(),
                description=body.get("description", "").strip(),
                duedate=body.get("duedate", "").strip(),
                issuetype=body.get("issuetype", "Task"),
                parent_key=body.get("parent_key", "").strip(),
            )
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(result)


class IssueDeleteView(TodosBaseView):
    def post(self, request, key):
        if self.service is None:
            return self._creds_error_json()

        try:
            result = self.service.delete_issue(key)
        except requests.RequestException as e:
            return JsonResponse({"error": str(e)}, status=502)
        except RuntimeError as e:
            err = e.args[0]
            status_code = err.get("status", 502) if isinstance(err, dict) else 502
            return JsonResponse({"error": err}, status=status_code)

        return JsonResponse(result)


class DueSummaryView(TodosBaseView):
    def get(self, request):
        if self.service is None:
            return self._creds_error_text()

        try:
            summary = self.service.get_due_summary()
        except requests.RequestException as e:
            return HttpResponse(str(e), status=502, content_type="text/plain")
        except RuntimeError as e:
            err = e.args[0]
            if isinstance(err, dict):
                msg = err.get("message") or err.get("errorMessages") or err
            else:
                msg = err
            return HttpResponse(str(msg), status=502, content_type="text/plain")

        fmt = request.GET.get("format", "text")
        if fmt == "json":
            return JsonResponse(summary)

        return HttpResponse(summary["text"], content_type="text/plain")
