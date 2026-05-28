from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .views import (
    BlogsStatsView, BlogsCacheView,
    ReadBlogsListView, ReadBlogsCreateView, ReadBlogsUpdateView, ReadBlogsDeleteView,
    WriteBlogsListView, WriteBlogsCreateView, WriteBlogsUpdateView, WriteBlogsDeleteView,
)

urlpatterns = [
    path("stats/",                        csrf_exempt(BlogsStatsView.as_view()),         name="api-blogs-stats"),
    path("cache/bust/",                   csrf_exempt(BlogsCacheView.as_view()),          name="api-blogs-cache-bust"),
    path("read/list/",                    csrf_exempt(ReadBlogsListView.as_view()),       name="api-read-blogs-list"),
    path("read/create/",                  csrf_exempt(ReadBlogsCreateView.as_view()),     name="api-read-blogs-create"),
    path("read/<str:page_id>/update/",    csrf_exempt(ReadBlogsUpdateView.as_view()),     name="api-read-blogs-update"),
    path("read/<str:page_id>/delete/",    csrf_exempt(ReadBlogsDeleteView.as_view()),     name="api-read-blogs-delete"),
    path("write/list/",                   csrf_exempt(WriteBlogsListView.as_view()),      name="api-write-blogs-list"),
    path("write/create/",                 csrf_exempt(WriteBlogsCreateView.as_view()),    name="api-write-blogs-create"),
    path("write/<str:page_id>/update/",   csrf_exempt(WriteBlogsUpdateView.as_view()),    name="api-write-blogs-update"),
    path("write/<str:page_id>/delete/",   csrf_exempt(WriteBlogsDeleteView.as_view()),    name="api-write-blogs-delete"),
]
