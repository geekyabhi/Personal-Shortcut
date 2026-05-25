from django.urls import path
from .views import (
    BooksCacheView, BooksChartsDataView, BooksChartsView,
    BooksCreateView, BooksDashboardView, BooksDriveFilesView,
    BooksDriveUploadView, BooksListView, BooksStatsView,
    BooksUpdateView, BooksDeleteView,
)

urlpatterns = [
    path("", BooksDashboardView.as_view(), name="books-dashboard"),
    path("charts/", BooksChartsView.as_view(), name="books-charts"),
    path("charts/data/", BooksChartsDataView.as_view(), name="books-charts-data"),
    path("list/", BooksListView.as_view(), name="books-list"),
    path("stats/", BooksStatsView.as_view(), name="books-stats"),
    path("create/", BooksCreateView.as_view(), name="books-create"),
    path("<str:page_id>/update/", BooksUpdateView.as_view(), name="books-update"),
    path("<str:page_id>/delete/", BooksDeleteView.as_view(), name="books-delete"),
    path("drive/files/", BooksDriveFilesView.as_view(), name="books-drive-files"),
    path("drive/upload/", BooksDriveUploadView.as_view(), name="books-drive-upload"),
    path("cache/bust/", BooksCacheView.as_view(), name="books-cache-bust"),
]
