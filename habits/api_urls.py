from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .views import (
    HabitsSummaryView, HabitsListView, HabitsChartView, CheckHabitsView,
    BackfillView, TodayHabitsView, HabitsUpdateEntryView,
    HabitNamesView, AddHabitView, RemoveHabitView,
)

urlpatterns = [
    path("summary/",  csrf_exempt(HabitsSummaryView.as_view()), name="api-habits-summary"),
    path("list/",     csrf_exempt(HabitsListView.as_view()),    name="api-habits-list"),
    path("chart/",    csrf_exempt(HabitsChartView.as_view()),   name="api-habits-chart"),
    path("today/",    csrf_exempt(TodayHabitsView.as_view()),   name="api-habits-today"),
    path("check/",    csrf_exempt(CheckHabitsView.as_view()),   name="api-habits-check"),
    path("backfill/", csrf_exempt(BackfillView.as_view()),      name="api-habits-backfill"),
    path("names/",    csrf_exempt(HabitNamesView.as_view()),    name="api-habits-names"),
    path("add/",      csrf_exempt(AddHabitView.as_view()),      name="api-habits-add"),
    path("remove/",   csrf_exempt(RemoveHabitView.as_view()),   name="api-habits-remove"),
    path("<str:page_id>/update/", csrf_exempt(HabitsUpdateEntryView.as_view()), name="api-habits-update-entry"),
]
