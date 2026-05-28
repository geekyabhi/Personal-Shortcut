from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .views import (
    ExpensesSummaryView, ExpensesListView, ExpensesCreateView,
    ExpensesUpdateView, ExpensesDeleteView, ExpensesTimeseriesView,
    ExpensesChartView, ExpensesCategoryTimeseriesView, ExpensesHeatmapView,
    ExpensesInsightsView,
)

urlpatterns = [
    path("summary/",                   csrf_exempt(ExpensesSummaryView.as_view()),             name="api-expenses-summary"),
    path("list/",                      csrf_exempt(ExpensesListView.as_view()),                name="api-expenses-list"),
    path("create/",                    csrf_exempt(ExpensesCreateView.as_view()),              name="api-expenses-create"),
    path("<str:page_id>/update/",      csrf_exempt(ExpensesUpdateView.as_view()),              name="api-expenses-update"),
    path("<str:page_id>/delete/",      csrf_exempt(ExpensesDeleteView.as_view()),              name="api-expenses-delete"),
    path("timeseries/",                csrf_exempt(ExpensesTimeseriesView.as_view()),          name="api-expenses-timeseries"),
    path("chart/",                     csrf_exempt(ExpensesChartView.as_view()),               name="api-expenses-chart"),
    path("category-timeseries/",       csrf_exempt(ExpensesCategoryTimeseriesView.as_view()), name="api-expenses-category-timeseries"),
    path("heatmap/",                   csrf_exempt(ExpensesHeatmapView.as_view()),             name="api-expenses-heatmap"),
    path("insights/",                  csrf_exempt(ExpensesInsightsView.as_view()),            name="api-expenses-insights"),
]
