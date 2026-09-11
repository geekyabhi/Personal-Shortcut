from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .views import HabitsSummaryView, HabitsChartView, CheckHabitsView, BackfillView, TodayHabitsView

urlpatterns = [
    path("summary/",  csrf_exempt(HabitsSummaryView.as_view()), name="api-habits-summary"),
    path("chart/",    csrf_exempt(HabitsChartView.as_view()),   name="api-habits-chart"),
    path("today/",    csrf_exempt(TodayHabitsView.as_view()),   name="api-habits-today"),
    path("check/",    csrf_exempt(CheckHabitsView.as_view()),   name="api-habits-check"),
    path("backfill/", csrf_exempt(BackfillView.as_view()),      name="api-habits-backfill"),
]
