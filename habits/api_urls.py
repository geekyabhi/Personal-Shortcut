from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .views import HabitsSummaryView, HabitsChartView, CheckHabitsView, BackfillView

urlpatterns = [
    path("summary/",  csrf_exempt(HabitsSummaryView.as_view()), name="api-habits-summary"),
    path("chart/",    csrf_exempt(HabitsChartView.as_view()),   name="api-habits-chart"),
    path("check/",    csrf_exempt(CheckHabitsView.as_view()),   name="api-habits-check"),
    path("backfill/", csrf_exempt(BackfillView.as_view()),      name="api-habits-backfill"),
]
