import json

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from .data_layer import get_creds
from .service import (
    backfill_missing_dates,
    check_and_update_habits,
    get_habits_chart_data,
    get_habits_summary,
)


def _get_period_params(request):
    return {
        "period": request.GET.get("period", "monthly"),
        "year":   request.GET.get("year", ""),
        "month":  request.GET.get("month", ""),
        "week":   request.GET.get("week", ""),
        "day":    request.GET.get("day", ""),
        "start":  request.GET.get("start", ""),
        "end":    request.GET.get("end", ""),
    }


def _notion_error_response(exc):
    try:
        body = exc.response.json()
    except Exception:
        body = exc.response.text if exc.response else str(exc)
    status = exc.response.status_code if exc.response else 502
    return JsonResponse({"error": body}, status=status)


class HabitsSummaryView(View):
    def get(self, request):
        token, db_id = get_creds()
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_HABITS_DB_ID must be set"}, status=500)
        try:
            data = get_habits_summary(token, db_id, **_get_period_params(request))
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return _notion_error_response(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)
        return JsonResponse(data)


class HabitsChartView(View):
    def get(self, request):
        token, db_id = get_creds()
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_HABITS_DB_ID must be set"}, status=500)
        try:
            data = get_habits_chart_data(token, db_id, **_get_period_params(request))
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except requests.HTTPError as exc:
            return _notion_error_response(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Network error: {exc}"}, status=502)
        return JsonResponse(data)


class BackfillView(View):
    def post(self, request):
        token, db_id = get_creds()
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_HABITS_DB_ID must be set"}, status=500)
        try:
            result = backfill_missing_dates(token, db_id)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Notion fetch error: {exc}"}, status=502)
        return JsonResponse(result)


class CheckHabitsView(View):
    def post(self, request):
        token, db_id = get_creds()
        if not token or not db_id:
            return JsonResponse({"error": "NOTION_TOKEN and NOTION_HABITS_DB_ID must be set"}, status=500)
        try:
            body = json.loads(request.body)
        except (ValueError, json.JSONDecodeError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)
        habits = body.get("habits", {})
        if not isinstance(habits, dict):
            return JsonResponse({"error": "'habits' must be an object e.g. {\"Exercise\": true}"}, status=400)
        try:
            result = check_and_update_habits(token, db_id, habits)
        except requests.HTTPError as exc:
            return _notion_error_response(exc)
        except requests.RequestException as exc:
            return JsonResponse({"error": f"Failed to update habits: {exc}"}, status=502)
        return JsonResponse(result)


class DashboardView(View):
    def get(self, request):
        return render(request, "habits/dashboard.html")


class ChartsView(View):
    def get(self, request):
        return render(request, "habits/charts.html")
