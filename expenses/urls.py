from django.urls import path
from .views import (
    ChartsView, DashboardView, ExpensesChartView, ExpensesCategoryTimeseriesView,
    ExpensesCreateView, ExpensesHeatmapView, ExpensesInsightsView, ExpensesListView,
    ExpensesSummaryView, ExpensesTimeseriesView, ExpensesUpdateView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="expenses-dashboard"),
    path("charts/", ChartsView.as_view(), name="expenses-charts"),
    path("summary/", ExpensesSummaryView.as_view(), name="expenses-summary"),
    path("timeseries/", ExpensesTimeseriesView.as_view(), name="expenses-timeseries"),
    path("chart/", ExpensesChartView.as_view(), name="expenses-chart"),
    path("insights/", ExpensesInsightsView.as_view(), name="expenses-insights"),
    path("category-timeseries/", ExpensesCategoryTimeseriesView.as_view(), name="expenses-category-timeseries"),
    path("heatmap/", ExpensesHeatmapView.as_view(), name="expenses-heatmap"),
    path("list/", ExpensesListView.as_view(), name="expenses-list"),
    path("create/", ExpensesCreateView.as_view(), name="expenses-create"),
    path("<str:page_id>/update/", ExpensesUpdateView.as_view(), name="expenses-update"),
]
