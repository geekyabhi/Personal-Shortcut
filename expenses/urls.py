from django.urls import path
from .views import ChartsView, DashboardView, ExpensesChartView, ExpensesSummaryView, ExpensesTimeseriesView

urlpatterns = [
    path("", DashboardView.as_view(), name="expenses-dashboard"),
    path("charts/", ChartsView.as_view(), name="expenses-charts"),
    path("summary/", ExpensesSummaryView.as_view(), name="expenses-summary"),
    path("timeseries/", ExpensesTimeseriesView.as_view(), name="expenses-timeseries"),
    path("chart/", ExpensesChartView.as_view(), name="expenses-chart"),
]
