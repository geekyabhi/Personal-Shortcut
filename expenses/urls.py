from django.urls import path
from .views import (
    ChartsView, DashboardView, ExpensesChartView, ExpensesCategoryTimeseriesView,
    ExpensesCreateView, ExpensesDeleteView, ExpensesHeatmapView, ExpensesInsightsView,
    ExpensesListView, ExpensesSummaryView, ExpensesTimeseriesView, ExpensesUpdateView,
)
from .splitwise_views import (
    SplitwiseCreateView, SplitwiseDashboardView, SplitwiseExpensesView,
    SplitwiseGroupsView, SplitwiseImportView, SplitwiseOverviewView,
    SplitwisePushEntryView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="expenses-dashboard"),
    path("charts/", ChartsView.as_view(), name="expenses-charts"),
    path("splitwise/", SplitwiseDashboardView.as_view(), name="expenses-splitwise"),
    path("summary/", ExpensesSummaryView.as_view(), name="expenses-summary"),
    path("timeseries/", ExpensesTimeseriesView.as_view(), name="expenses-timeseries"),
    path("chart/", ExpensesChartView.as_view(), name="expenses-chart"),
    path("insights/", ExpensesInsightsView.as_view(), name="expenses-insights"),
    path("category-timeseries/", ExpensesCategoryTimeseriesView.as_view(), name="expenses-category-timeseries"),
    path("heatmap/", ExpensesHeatmapView.as_view(), name="expenses-heatmap"),
    path("list/", ExpensesListView.as_view(), name="expenses-list"),
    path("create/", ExpensesCreateView.as_view(), name="expenses-create"),
    path("splitwise/overview/", SplitwiseOverviewView.as_view(), name="expenses-splitwise-overview"),
    path("splitwise/expenses/", SplitwiseExpensesView.as_view(), name="expenses-splitwise-expenses"),
    path("splitwise/groups/", SplitwiseGroupsView.as_view(), name="expenses-splitwise-groups"),
    path("splitwise/create/", SplitwiseCreateView.as_view(), name="expenses-splitwise-create"),
    path("splitwise/import/", SplitwiseImportView.as_view(), name="expenses-splitwise-import"),
    path("<str:page_id>/push-split/", SplitwisePushEntryView.as_view(), name="expenses-push-split"),
    path("<str:page_id>/update/", ExpensesUpdateView.as_view(), name="expenses-update"),
    path("<str:page_id>/delete/", ExpensesDeleteView.as_view(), name="expenses-delete"),
]
