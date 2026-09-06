import json

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from .data_layer import ExpensesDataLayer
from .service import ExpensesService


class ExpensesBaseView(View):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        data_layer = ExpensesDataLayer.from_env()
        if data_layer.is_configured:
            self.service = ExpensesService(data_layer)
        else:
            self.service = None

    def _creds_error(self):
        return JsonResponse(
            {"error": "NOTION_TOKEN and NOTION_EXPENSES_DB_ID must be set"}, status=500
        )

    @staticmethod
    def _api_error(exc):
        return JsonResponse(
            {
                "error": f"Notion API error: {exc}",
                "detail": exc.response.text if exc.response else "",
            },
            status=502,
        )


class DashboardView(View):
    def get(self, request):
        return render(request, "expenses/dashboard.html")


class ChartsView(View):
    def get(self, request):
        return render(request, "expenses/charts.html")


class ExpensesSummaryView(ExpensesBaseView):
    def get(self, request):
        if not self.service:
            return self._creds_error()

        period   = request.GET.get("period", "all")
        group_by = request.GET.get("group_by", "")
        year     = request.GET.get("year", "")
        month    = request.GET.get("month", "")
        week     = request.GET.get("week", "")
        day      = request.GET.get("day", "")
        start    = request.GET.get("start", "")
        end      = request.GET.get("end", "")
        force    = request.GET.get("force", "") in ("1", "true")
        partial  = request.GET.get("partial", "") in ("1", "true")

        try:
            result = self.service.get_summary(
                period, group_by, year, month, week, day, start, end, force,
                partial=partial, filters=request.GET.get("filters", ""),
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse(result)


class ExpensesTimeseriesView(ExpensesBaseView):
    def get(self, request):
        if not self.service:
            return self._creds_error()

        period = request.GET.get("period", "monthly")
        year   = request.GET.get("year", "")
        month  = request.GET.get("month", "")
        week   = request.GET.get("week", "")
        day    = request.GET.get("day", "")
        start  = request.GET.get("start", "")
        end    = request.GET.get("end", "")
        force  = request.GET.get("force", "") in ("1", "true")
        partial = request.GET.get("partial", "") in ("1", "true")

        try:
            result = self.service.get_timeseries(
                period, year, month, week, day, start, end, force, partial=partial, filters=request.GET.get("filters", "")
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse(result)


class ExpensesChartView(ExpensesBaseView):
    def get(self, request):
        if not self.service:
            return self._creds_error()

        period   = request.GET.get("period", "monthly")
        group_by = request.GET.get("group_by", "")
        year     = request.GET.get("year", "")
        month    = request.GET.get("month", "")
        week     = request.GET.get("week", "")
        day      = request.GET.get("day", "")
        start    = request.GET.get("start", "")
        end      = request.GET.get("end", "")
        force    = request.GET.get("force", "") in ("1", "true")
        partial  = request.GET.get("partial", "") in ("1", "true")

        try:
            result = self.service.get_chart(
                period, group_by, year, month, week, day, start, end, force,
                partial=partial, filters=request.GET.get("filters", ""),
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse(result)


class ExpensesCategoryTimeseriesView(ExpensesBaseView):
    def get(self, request):
        if not self.service:
            return self._creds_error()

        period = request.GET.get("period", "monthly")
        year   = request.GET.get("year", "")
        month  = request.GET.get("month", "")
        week   = request.GET.get("week", "")
        day    = request.GET.get("day", "")
        start  = request.GET.get("start", "")
        end    = request.GET.get("end", "")
        force  = request.GET.get("force", "") in ("1", "true")
        partial = request.GET.get("partial", "") in ("1", "true")

        try:
            result = self.service.get_category_timeseries(
                period, year, month, week, day, start, end, force, partial=partial, filters=request.GET.get("filters", "")
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse(result)


class ExpensesInsightsView(ExpensesBaseView):
    def get(self, request):
        if not self.service:
            return self._creds_error()

        period = request.GET.get("period", "all")
        year   = request.GET.get("year", "")
        month  = request.GET.get("month", "")
        week   = request.GET.get("week", "")
        day    = request.GET.get("day", "")
        start  = request.GET.get("start", "")
        end    = request.GET.get("end", "")
        force  = request.GET.get("force", "") in ("1", "true")
        partial = request.GET.get("partial", "") in ("1", "true")

        try:
            result = self.service.get_insights(
                period, year, month, week, day, start, end, force, partial=partial, filters=request.GET.get("filters", "")
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse(result)


class ExpensesListView(ExpensesBaseView):
    def get(self, request):
        if not self.service:
            return self._creds_error()

        period   = request.GET.get("period", "all")
        year     = request.GET.get("year", "")
        month    = request.GET.get("month", "")
        week     = request.GET.get("week", "")
        day      = request.GET.get("day", "")
        start    = request.GET.get("start", "")
        end      = request.GET.get("end", "")
        category = request.GET.get("category", "")
        source   = request.GET.get("source", "")
        min_amt  = request.GET.get("min_amount", "")
        max_amt  = request.GET.get("max_amount", "")
        sort     = request.GET.get("sort", "date_desc")
        search   = request.GET.get("search", "").strip().lower()
        split    = request.GET.get("split", "").strip()
        processed = request.GET.get("processed", "").strip()
        force    = request.GET.get("force", "") in ("1", "true")
        partial  = request.GET.get("partial", "") in ("1", "true")
        want_all = request.GET.get("all", "") in ("1", "true")

        try:
            page      = max(1, int(request.GET.get("page", 1)))
            page_size = max(1, min(100, int(request.GET.get("page_size", 25))))
        except ValueError:
            return JsonResponse({"error": "Invalid page or page_size."}, status=400)

        min_amount = float(min_amt) if min_amt else None
        max_amount = float(max_amt) if max_amt else None

        try:
            result = self.service.list_entries(
                period, year, month, week, day, start, end,
                category, source, min_amount, max_amount,
                sort, search, force, page, page_size, split,
                partial=partial, unpaginated=want_all, processed=processed,
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse(result)


class ExpensesHeatmapView(ExpensesBaseView):
    def get(self, request):
        if not self.service:
            return self._creds_error()

        period = request.GET.get("period", "monthly")
        year   = request.GET.get("year", "")
        month  = request.GET.get("month", "")
        week   = request.GET.get("week", "")
        day    = request.GET.get("day", "")
        start  = request.GET.get("start", "")
        end    = request.GET.get("end", "")
        force  = request.GET.get("force", "") in ("1", "true")
        partial = request.GET.get("partial", "") in ("1", "true")

        try:
            result = self.service.get_heatmap(
                period, year, month, week, day, start, end, force, partial=partial, filters=request.GET.get("filters", "")
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse(result)


_EXTRA_KEYS = (
    "comment", "other_partner", "add_to_split", "from_split",
    "split_added", "processed", "splitwise_id",
)


def _extra_fields(data):
    """Only the optional-column keys the client actually sent (absent = untouched)."""
    return {k: data[k] for k in _EXTRA_KEYS if k in data}


class ExpensesCreateView(ExpensesBaseView):
    def post(self, request):
        if not self.service:
            return self._creds_error()

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        name       = (data.get("name") or "").strip()
        amount     = data.get("amount")
        date_str   = (data.get("date") or "").strip()
        categories = [c for c in (data.get("categories") or []) if c]
        source     = (data.get("source") or "").strip()
        mode       = (data.get("mode") or "").strip()

        try:
            page_id = self.service.create_entry(
                name, amount, date_str, categories, source, mode, **_extra_fields(data)
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse({"ok": True, "page_id": page_id}, status=201)


class ExpensesUpdateView(ExpensesBaseView):
    def patch(self, request, page_id):
        if not self.service:
            return self._creds_error()

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        name       = (data.get("name") or "").strip()
        amount     = data.get("amount")
        date_str   = (data.get("date") or "").strip()
        categories = [c for c in (data.get("categories") or []) if c]
        source     = (data.get("source") or "").strip()
        mode       = (data.get("mode") or "").strip()

        try:
            self.service.update_entry(
                page_id, name, amount, date_str, categories, source, mode, **_extra_fields(data)
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse({"ok": True})


class ExpensesDeleteView(ExpensesBaseView):
    def delete(self, request, page_id):
        if not self.service:
            return self._creds_error()

        try:
            self.service.delete_entry(page_id)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse({"ok": True})


class ExpensesSplitView(ExpensesBaseView):
    def post(self, request, page_id):
        if not self.service:
            return self._creds_error()

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        splits = data.get("splits") or []

        try:
            new_ids = self.service.split_entry(page_id, splits)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._api_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)

        return JsonResponse({"ok": True, "page_ids": new_ids})
