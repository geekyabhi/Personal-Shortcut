from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .views import (
    BooksListView, BooksStatsView, BooksCreateView, BooksUpdateView, BooksDeleteView,
    BooksChartsDataView, BooksDriveFilesView, BooksDriveUploadView, BooksCacheView,
)

urlpatterns = [
    path("list/",                    csrf_exempt(BooksListView.as_view()),        name="api-books-list"),
    path("stats/",                   csrf_exempt(BooksStatsView.as_view()),       name="api-books-stats"),
    path("create/",                  csrf_exempt(BooksCreateView.as_view()),      name="api-books-create"),
    path("<str:page_id>/update/",    csrf_exempt(BooksUpdateView.as_view()),      name="api-books-update"),
    path("<str:page_id>/delete/",    csrf_exempt(BooksDeleteView.as_view()),      name="api-books-delete"),
    path("charts/data/",             csrf_exempt(BooksChartsDataView.as_view()),  name="api-books-charts-data"),
    path("drive/files/",             csrf_exempt(BooksDriveFilesView.as_view()),  name="api-books-drive-files"),
    path("drive/upload/",            csrf_exempt(BooksDriveUploadView.as_view()), name="api-books-drive-upload"),
    path("cache/bust/",              csrf_exempt(BooksCacheView.as_view()),       name="api-books-cache-bust"),
]
