import json

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from .data_layer import ExpensesDataLayer
from .service import ExpensesService
from .splitwise_client import SplitwiseClient, SplitwiseError, SplitwiseNotConfigured
from .splitwise_service import SplitwiseService


class SplitwiseBaseView(View):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.client = SplitwiseClient.from_env()
        self.svc = SplitwiseService(self.client) if self.client.is_configured else None

    def _not_configured(self):
        return JsonResponse(
            {
                "configured": False,
                "error": "Splitwise is not configured. Set SPLITWISE_CONSUMER_KEY, "
                "SPLITWISE_CONSUMER_SECRET and SPLITWISE_API_KEY.",
            },
            status=200,
        )

    @staticmethod
    def _sw_error(exc):
        return JsonResponse({"error": f"Splitwise API error: {exc}"}, status=502)

    def _expenses_service(self):
        dl = ExpensesDataLayer.from_env()
        if not dl.is_configured:
            return None
        return ExpensesService(dl)

    def _body(self, request):
        try:
            return json.loads(request.body or "{}")
        except (json.JSONDecodeError, ValueError):
            return None


class SplitwiseDashboardView(View):
    """Renders the Splitwise tab page (data is loaded client-side)."""

    def get(self, request):
        return render(request, "expenses/splitwise.html")


class SplitwiseOverviewView(SplitwiseBaseView):
    def get(self, request):
        if not self.svc:
            return self._not_configured()
        try:
            return JsonResponse(self.svc.overview())
        except SplitwiseNotConfigured:
            return self._not_configured()
        except SplitwiseError as exc:
            return self._sw_error(exc)


class SplitwiseExpensesView(SplitwiseBaseView):
    def get(self, request):
        if not self.svc:
            return self._not_configured()
        try:
            result = self.svc.recent_expenses(
                limit=request.GET.get("limit", 20),
                offset=request.GET.get("offset", 0),
                group_id=request.GET.get("group_id", ""),
                friend_id=request.GET.get("friend_id", ""),
                dated_after=request.GET.get("dated_after", ""),
                dated_before=request.GET.get("dated_before", ""),
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except SplitwiseNotConfigured:
            return self._not_configured()
        except SplitwiseError as exc:
            return self._sw_error(exc)

        # Flag which of these are already imported into Notion (for the UI)
        expenses_service = self._expenses_service()
        if expenses_service:
            try:
                imported = expenses_service.imported_splitwise_ids()
            except Exception:
                imported = None
            result["dedupe_enabled"] = imported is not None
            result["already_imported"] = sorted(imported) if imported else []
        else:
            result["dedupe_enabled"] = False
            result["already_imported"] = []

        return JsonResponse(result)


class SplitwiseGroupsView(SplitwiseBaseView):
    def get(self, request):
        if not self.svc:
            return self._not_configured()
        try:
            return JsonResponse(
                {"me": self.client.me(), "groups": self.client.get_groups()}
            )
        except SplitwiseNotConfigured:
            return self._not_configured()
        except SplitwiseError as exc:
            return self._sw_error(exc)


class SplitwiseCreateView(SplitwiseBaseView):
    def post(self, request):
        if not self.svc:
            return self._not_configured()
        data = self._body(request)
        if data is None:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        try:
            result = self.svc.create_split(
                description=data.get("description") or data.get("name") or "",
                amount=data.get("amount"),
                participant_ids=data.get("participant_ids") or [],
                group_id=str(data.get("group_id") or ""),
                date_str=(data.get("date") or "").strip(),
                currency=(data.get("currency") or "").strip(),
                category_id=data.get("category_id"),
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except SplitwiseNotConfigured:
            return self._not_configured()
        except SplitwiseError as exc:
            return self._sw_error(exc)
        return JsonResponse({"ok": True, "expense": result}, status=201)


class SplitwisePushEntryView(SplitwiseBaseView):
    """Push a Notion expense row (flagged 'Add to Split') to Splitwise, then
    tick its 'Split Added' checkbox in Notion."""

    def post(self, request, page_id):
        if not self.svc:
            return self._not_configured()
        data = self._body(request)
        if data is None:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        expenses_service = self._expenses_service()
        if not expenses_service:
            return JsonResponse(
                {"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"},
                status=500,
            )

        try:
            entry = expenses_service.get_entry(page_id)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=404)

        if entry.get("split_added"):
            return JsonResponse(
                {"error": "This expense is already marked 'Split Added'."}, status=400
            )

        try:
            created = self.svc.push_entry_split(
                entry,
                mode=(data.get("mode") or "group"),
                group_id=str(data.get("group_id") or "") or None,
                shares=data.get("shares") or {},
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except SplitwiseNotConfigured:
            return self._not_configured()
        except SplitwiseError as exc:
            return self._sw_error(exc)

        try:
            expenses_service.mark_split_added(page_id)
        except requests.RequestException as exc:
            return JsonResponse(
                {
                    "ok": True,
                    "splitwise_expense_id": created.get("id"),
                    "split_added": False,
                    "warning": "Pushed to Splitwise, but couldn't tick 'Split Added' "
                    f"in Notion ({exc}). Please tick it manually.",
                },
                status=201,
            )

        return JsonResponse(
            {
                "ok": True,
                "splitwise_expense_id": created.get("id"),
                "split_added": True,
            },
            status=201,
        )


class SplitwiseImportView(SplitwiseBaseView):
    def post(self, request):
        if not self.svc:
            return self._not_configured()
        data = self._body(request)
        if data is None:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        expense_id = data.get("expense_id")
        if not expense_id:
            return JsonResponse({"error": "expense_id is required"}, status=400)

        expenses_service = self._expenses_service()
        if not expenses_service:
            return JsonResponse(
                {"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"},
                status=500,
            )

        try:
            result = self.svc.import_to_notion(expense_id, expenses_service)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except SplitwiseNotConfigured:
            return self._not_configured()
        except SplitwiseError as exc:
            return self._sw_error(exc)
        return JsonResponse({"ok": True, **result}, status=201)
