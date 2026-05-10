from django.urls import path
from .views import ChartsView, DashboardView, HabitsChartView, HabitsSummaryView

urlpatterns = [
    path("", DashboardView.as_view(), name="habits-dashboard"),
    path("charts/", ChartsView.as_view(), name="habits-charts"),
    path("summary/", HabitsSummaryView.as_view(), name="habits-summary"),
    path("chart/", HabitsChartView.as_view(), name="habits-chart"),
]
