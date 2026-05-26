import json

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from .data_layer import HabitsDataLayer
from .service import HabitsService


class HabitsBaseView(View):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        data_layer = HabitsDataLayer.from_env()
        self.service = HabitsService(data_layer) if data_layer.is_configured else None

    def _creds_error(self):
        return JsonResponse({"error": "NOTION_TOKEN and NOTION_HABITS_DB_ID must be set"}, status=500)

    @staticmethod
    def _notion_error(exc):
        try:
            body = exc.response.json()
        except Exception:
            body = exc.response.text if exc.response else str(exc)
        status = exc.response.status_code if exc.response else 502
        return JsonResponse({"error": body}, status=status)

    def _period_params(self):
        return {
            "period": self.request.GET.get("period", "monthly"),
            "year":   self.request.GET.get("year", ""),
            "month":  self.request.GET.get("month", ""),
            "week":   self.request.GET.get("week", ""),
            "day":    self.request.GET.get("day", ""),
            "start":  self.request.GET.get("start", ""),
            "end":    self.request.GET.get("end", ""),
        }


class HabitsSummaryView(HabitsBaseView):
    def get(self, request):
        if not self.service:
            return self._creds_error()
        try:
            data = self.service.get_summary(**self._period_params())
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._notion_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)
        return JsonResponse(data)


class HabitsChartView(HabitsBaseView):
    def get(self, request):
        if not self.service:
            return self._creds_error()
        try:
            data = self.service.get_chart_data(**self._period_params())
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return self._notion_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)
        return JsonResponse(data)


class BackfillView(HabitsBaseView):
    def post(self, request):
        if not self.service:
            return self._creds_error()
        try:
            result = self.service.backfill()
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Notion fetch error: {exc}"}, status=502)
        return JsonResponse(result)


class CheckHabitsView(HabitsBaseView):
    def post(self, request):
        if not self.service:
            return self._creds_error()
        try:
            body = json.loads(request.body)
        except (ValueError, json.JSONDecodeError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)
        habits = body.get("habits", {})
        if not isinstance(habits, dict):
            return JsonResponse({"error": "'habits' must be an object e.g. {\"Exercise\": true}"}, status=400)
        try:
            result = self.service.check_habits(habits)
        except requests.HTTPError as exc:
            return self._notion_error(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Failed to update habits: {exc}"}, status=502)
        return JsonResponse(result)


class DashboardView(View):
    def get(self, request):
        return render(request, "habits/dashboard.html")


class ChartsView(View):
    def get(self, request):
        return render(request, "habits/charts.html")
