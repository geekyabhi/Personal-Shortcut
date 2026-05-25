from django.urls import path
from .views import (
    BlogsDashboardView, BlogsStatsView, BlogsCacheView,
    ReadBlogsListView, ReadBlogsCreateView, ReadBlogsUpdateView, ReadBlogsDeleteView,
    WriteBlogsListView, WriteBlogsCreateView, WriteBlogsUpdateView, WriteBlogsDeleteView,
)

urlpatterns = [
    path("", BlogsDashboardView.as_view(), name="blogs-dashboard"),
    path("stats/", BlogsStatsView.as_view(), name="blogs-stats"),
    path("cache/bust/", BlogsCacheView.as_view(), name="blogs-cache-bust"),

    path("read/list/", ReadBlogsListView.as_view(), name="read-blogs-list"),
    path("read/create/", ReadBlogsCreateView.as_view(), name="read-blogs-create"),
    path("read/<str:page_id>/update/", ReadBlogsUpdateView.as_view(), name="read-blogs-update"),
    path("read/<str:page_id>/delete/", ReadBlogsDeleteView.as_view(), name="read-blogs-delete"),

    path("write/list/", WriteBlogsListView.as_view(), name="write-blogs-list"),
    path("write/create/", WriteBlogsCreateView.as_view(), name="write-blogs-create"),
    path("write/<str:page_id>/update/", WriteBlogsUpdateView.as_view(), name="write-blogs-update"),
    path("write/<str:page_id>/delete/", WriteBlogsDeleteView.as_view(), name="write-blogs-delete"),
]
