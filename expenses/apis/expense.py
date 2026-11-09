"""The expenses REST API (mounted at /api/expenses/).

Every route needs ``Authorization: Bearer <token>``; the uid comes from the
token, so a caller only ever sees and changes their own expenses. Splitwise
routes run on the owner's personal Splitwise login, so they are owner-only.
"""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from users.views import full_access_required, token_required

from ..views import (
    OptionDetailView, OptionsCreateView, OptionsListView,
    ExpensesSummaryView, ExpensesListView, ExpensesCreateView,
    ExpensesUpdateView, ExpensesDeleteView, ExpensesTimeseriesView,
    ExpensesChartView, ExpensesCategoryTimeseriesView, ExpensesHeatmapView,
    ExpensesInsightsView,
)
from ..services.splitwise.splitwise_views import (
    SplitwiseCreateView, SplitwiseExpensesView, SplitwiseGroupsView,
    SplitwiseImportView, SplitwiseOverviewView, SplitwisePushEntryView,
)


def api(view):
    """Any signed-in account, identified by its bearer token."""
    return csrf_exempt(token_required(view.as_view()))


def owner_api(view):
    """The account owner only (Splitwise)."""
    return csrf_exempt(token_required(full_access_required(view.as_view())))


urlpatterns = [
    path("summary/",                    api(ExpensesSummaryView),            name="api-expenses-summary"),
    path("list/",                       api(ExpensesListView),               name="api-expenses-list"),
    path("create/",                     api(ExpensesCreateView),             name="api-expenses-create"),
    path("<str:page_id>/update/",       api(ExpensesUpdateView),             name="api-expenses-update"),
    path("<str:page_id>/delete/",       api(ExpensesDeleteView),             name="api-expenses-delete"),
    path("timeseries/",                 api(ExpensesTimeseriesView),         name="api-expenses-timeseries"),
    path("chart/",                      api(ExpensesChartView),              name="api-expenses-chart"),
    path("category-timeseries/",        api(ExpensesCategoryTimeseriesView), name="api-expenses-category-timeseries"),
    path("heatmap/",                    api(ExpensesHeatmapView),            name="api-expenses-heatmap"),
    path("insights/",                   api(ExpensesInsightsView),           name="api-expenses-insights"),
    path("options/",                    api(OptionsListView),                name="api-expenses-options"),
    path("options/<str:kind>/",         api(OptionsCreateView),              name="api-expenses-options-create"),
    path("options/<str:kind>/<int:option_id>/", api(OptionDetailView),       name="api-expenses-options-detail"),
    path("splitwise/overview/",         owner_api(SplitwiseOverviewView),    name="api-expenses-splitwise-overview"),
    path("splitwise/expenses/",         owner_api(SplitwiseExpensesView),    name="api-expenses-splitwise-expenses"),
    path("splitwise/groups/",           owner_api(SplitwiseGroupsView),      name="api-expenses-splitwise-groups"),
    path("splitwise/create/",           owner_api(SplitwiseCreateView),      name="api-expenses-splitwise-create"),
    path("splitwise/import/",           owner_api(SplitwiseImportView),      name="api-expenses-splitwise-import"),
    path("<str:page_id>/push-split/",   owner_api(SplitwisePushEntryView),   name="api-expenses-push-split"),
]
