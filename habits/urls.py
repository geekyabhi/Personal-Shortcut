from django.urls import path
from .views import (
    BackfillView, ChartsView, CheckHabitsView, DashboardView, HabitsChartView,
    HabitsSummaryView, TodayHabitsView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="habits-dashboard"),
    path("charts/", ChartsView.as_view(), name="habits-charts"),
    path("summary/", HabitsSummaryView.as_view(), name="habits-summary"),
    path("chart/", HabitsChartView.as_view(), name="habits-chart"),
    path("backfill/", BackfillView.as_view(), name="habits-backfill"),
    path("today/", TodayHabitsView.as_view(), name="habits-today"),
    path("check/", CheckHabitsView.as_view(), name="habits-check"),
]
