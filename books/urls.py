from django.urls import path
from .views import BooksCacheView, BooksDashboardView, BooksListView, BooksStatsView

urlpatterns = [
    path("", BooksDashboardView.as_view(), name="books-dashboard"),
    path("list/", BooksListView.as_view(), name="books-list"),
    path("stats/", BooksStatsView.as_view(), name="books-stats"),
    path("cache/bust/", BooksCacheView.as_view(), name="books-cache-bust"),
]
