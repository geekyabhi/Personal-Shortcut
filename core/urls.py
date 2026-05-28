from django.shortcuts import render
from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt

from core.auth_views import login_view, auth_start, auth_callback, logout_view
from core.stats_view import HomeStatsView
from core.views_pwa import manifest, service_worker, pwa_icon, apple_touch_icon
from todos.views import CreateIssueView, ListIssuesView, DueSummaryView
from expenses.views import (
    ExpensesSummaryView, ExpensesListView, ExpensesCreateView,
    ExpensesUpdateView, ExpensesDeleteView, ExpensesTimeseriesView,
    ExpensesChartView, ExpensesCategoryTimeseriesView, ExpensesHeatmapView,
    ExpensesInsightsView,
)
from habits.views import HabitsSummaryView, HabitsChartView, CheckHabitsView, BackfillView
from books.views import (
    BooksListView, BooksStatsView, BooksCreateView, BooksUpdateView, BooksDeleteView,
    BooksChartsDataView, BooksDriveFilesView, BooksDriveUploadView, BooksCacheView,
)
from blogs.views import (
    BlogsStatsView, BlogsCacheView,
    ReadBlogsListView, ReadBlogsCreateView, ReadBlogsUpdateView, ReadBlogsDeleteView,
    WriteBlogsListView, WriteBlogsCreateView, WriteBlogsUpdateView, WriteBlogsDeleteView,
)


def home(request):
    user = {
        "name":    request.session.get("user_name", ""),
        "picture": request.session.get("user_picture", ""),
        "email":   request.session.get("user_email", ""),
    }
    return render(request, "home.html", {"user": user})


urlpatterns = [
    path("", home, name="home"),
    path("home/stats/", HomeStatsView.as_view(), name="home-stats"),
    path("login/",          login_view,    name="login"),
    path("auth/google/",    auth_start,    name="auth-start"),
    path("auth/callback/",  auth_callback, name="auth-callback"),
    path("auth/logout/",    logout_view,   name="logout"),
    path("manifest.json",      manifest,       name="manifest"),
    path("service-worker.js",  service_worker, name="service-worker"),
    path("pwa-icon.svg",       pwa_icon,       name="pwa-icon"),
    path("apple-touch-icon.png", apple_touch_icon, name="apple-touch-icon"),
    path("expenses/", include("expenses.urls")),
    path("habits/",   include("habits.urls")),
    path("todos/",    include("todos.urls")),
    path("books/",    include("books.urls")),
    path("blogs/",    include("blogs.urls")),
    # Auth-free API endpoints (no session or CSRF required)
    # Todos
    path("api/todos/create/",      csrf_exempt(CreateIssueView.as_view()),  name="api-todos-create"),
    path("api/todos/issues/",      csrf_exempt(ListIssuesView.as_view()),   name="api-todos-list"),
    path("api/todos/due-summary/", csrf_exempt(DueSummaryView.as_view()),   name="api-todos-due-summary"),
    # Expenses
    path("api/expenses/summary/",                   csrf_exempt(ExpensesSummaryView.as_view()),            name="api-expenses-summary"),
    path("api/expenses/list/",                      csrf_exempt(ExpensesListView.as_view()),               name="api-expenses-list"),
    path("api/expenses/create/",                    csrf_exempt(ExpensesCreateView.as_view()),             name="api-expenses-create"),
    path("api/expenses/<str:page_id>/update/",      csrf_exempt(ExpensesUpdateView.as_view()),             name="api-expenses-update"),
    path("api/expenses/<str:page_id>/delete/",      csrf_exempt(ExpensesDeleteView.as_view()),             name="api-expenses-delete"),
    path("api/expenses/timeseries/",                csrf_exempt(ExpensesTimeseriesView.as_view()),         name="api-expenses-timeseries"),
    path("api/expenses/chart/",                     csrf_exempt(ExpensesChartView.as_view()),              name="api-expenses-chart"),
    path("api/expenses/category-timeseries/",       csrf_exempt(ExpensesCategoryTimeseriesView.as_view()), name="api-expenses-category-timeseries"),
    path("api/expenses/heatmap/",                   csrf_exempt(ExpensesHeatmapView.as_view()),            name="api-expenses-heatmap"),
    path("api/expenses/insights/",                  csrf_exempt(ExpensesInsightsView.as_view()),           name="api-expenses-insights"),
    # Habits
    path("api/habits/summary/",  csrf_exempt(HabitsSummaryView.as_view()), name="api-habits-summary"),
    path("api/habits/chart/",    csrf_exempt(HabitsChartView.as_view()),   name="api-habits-chart"),
    path("api/habits/check/",    csrf_exempt(CheckHabitsView.as_view()),   name="api-habits-check"),
    path("api/habits/backfill/", csrf_exempt(BackfillView.as_view()),      name="api-habits-backfill"),
    # Books
    path("api/books/list/",                     csrf_exempt(BooksListView.as_view()),        name="api-books-list"),
    path("api/books/stats/",                    csrf_exempt(BooksStatsView.as_view()),       name="api-books-stats"),
    path("api/books/create/",                   csrf_exempt(BooksCreateView.as_view()),      name="api-books-create"),
    path("api/books/<str:page_id>/update/",     csrf_exempt(BooksUpdateView.as_view()),      name="api-books-update"),
    path("api/books/<str:page_id>/delete/",     csrf_exempt(BooksDeleteView.as_view()),      name="api-books-delete"),
    path("api/books/charts/data/",              csrf_exempt(BooksChartsDataView.as_view()),  name="api-books-charts-data"),
    path("api/books/drive/files/",              csrf_exempt(BooksDriveFilesView.as_view()),  name="api-books-drive-files"),
    path("api/books/drive/upload/",             csrf_exempt(BooksDriveUploadView.as_view()), name="api-books-drive-upload"),
    path("api/books/cache/bust/",               csrf_exempt(BooksCacheView.as_view()),       name="api-books-cache-bust"),
    # Blogs
    path("api/blogs/stats/",                         csrf_exempt(BlogsStatsView.as_view()),         name="api-blogs-stats"),
    path("api/blogs/cache/bust/",                    csrf_exempt(BlogsCacheView.as_view()),          name="api-blogs-cache-bust"),
    path("api/blogs/read/list/",                     csrf_exempt(ReadBlogsListView.as_view()),       name="api-read-blogs-list"),
    path("api/blogs/read/create/",                   csrf_exempt(ReadBlogsCreateView.as_view()),     name="api-read-blogs-create"),
    path("api/blogs/read/<str:page_id>/update/",     csrf_exempt(ReadBlogsUpdateView.as_view()),     name="api-read-blogs-update"),
    path("api/blogs/read/<str:page_id>/delete/",     csrf_exempt(ReadBlogsDeleteView.as_view()),     name="api-read-blogs-delete"),
    path("api/blogs/write/list/",                    csrf_exempt(WriteBlogsListView.as_view()),      name="api-write-blogs-list"),
    path("api/blogs/write/create/",                  csrf_exempt(WriteBlogsCreateView.as_view()),    name="api-write-blogs-create"),
    path("api/blogs/write/<str:page_id>/update/",    csrf_exempt(WriteBlogsUpdateView.as_view()),    name="api-write-blogs-update"),
    path("api/blogs/write/<str:page_id>/delete/",    csrf_exempt(WriteBlogsDeleteView.as_view()),    name="api-write-blogs-delete"),
]
