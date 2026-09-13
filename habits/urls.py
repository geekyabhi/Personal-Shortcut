from django.urls import path
from .views import (
    AddHabitView, BackfillPreviewView, BackfillView, BulkSetHabitView, ChartsView,
    CheckHabitsView, DashboardView, HabitNamesView, HabitsChartView, HabitsListView,
    HabitsSummaryView, HabitsUpdateEntryView, RemoveHabitView, RenameHabitView,
    TodayHabitsView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="habits-dashboard"),
    path("charts/", ChartsView.as_view(), name="habits-charts"),
    path("summary/", HabitsSummaryView.as_view(), name="habits-summary"),
    path("list/", HabitsListView.as_view(), name="habits-list"),
    path("chart/", HabitsChartView.as_view(), name="habits-chart"),
    path("backfill/preview/", BackfillPreviewView.as_view(), name="habits-backfill-preview"),
    path("backfill/", BackfillView.as_view(), name="habits-backfill"),
    path("today/", TodayHabitsView.as_view(), name="habits-today"),
    path("check/", CheckHabitsView.as_view(), name="habits-check"),
    path("names/", HabitNamesView.as_view(), name="habits-names"),
    path("add/", AddHabitView.as_view(), name="habits-add"),
    path("remove/", RemoveHabitView.as_view(), name="habits-remove"),
    path("rename/", RenameHabitView.as_view(), name="habits-rename"),
    path("bulk-set/", BulkSetHabitView.as_view(), name="habits-bulk-set"),
    path("<str:page_id>/update/", HabitsUpdateEntryView.as_view(), name="habits-update-entry"),
]
