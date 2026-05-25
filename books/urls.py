from django.urls import path
from .views import BooksCacheView, BooksCreateView, BooksDashboardView, BooksListView, BooksStatsView

urlpatterns = [
    path("", BooksDashboardView.as_view(), name="books-dashboard"),
    path("list/", BooksListView.as_view(), name="books-list"),
    path("stats/", BooksStatsView.as_view(), name="books-stats"),
    path("create/", BooksCreateView.as_view(), name="books-create"),
    path("cache/bust/", BooksCacheView.as_view(), name="books-cache-bust"),
]
