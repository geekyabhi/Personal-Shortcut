from django.urls import path
from .views import (
    AddHabitView, BackfillView, ChartsView, CheckHabitsView, DashboardView,
    HabitNamesView, HabitsChartView, HabitsListView, HabitsSummaryView,
    HabitsUpdateEntryView, RemoveHabitView, TodayHabitsView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="habits-dashboard"),
    path("charts/", ChartsView.as_view(), name="habits-charts"),
    path("summary/", HabitsSummaryView.as_view(), name="habits-summary"),
    path("list/", HabitsListView.as_view(), name="habits-list"),
    path("chart/", HabitsChartView.as_view(), name="habits-chart"),
    path("backfill/", BackfillView.as_view(), name="habits-backfill"),
    path("today/", TodayHabitsView.as_view(), name="habits-today"),
    path("check/", CheckHabitsView.as_view(), name="habits-check"),
    path("names/", HabitNamesView.as_view(), name="habits-names"),
    path("add/", AddHabitView.as_view(), name="habits-add"),
    path("remove/", RemoveHabitView.as_view(), name="habits-remove"),
    path("<str:page_id>/update/", HabitsUpdateEntryView.as_view(), name="habits-update-entry"),
]
