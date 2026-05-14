from django.urls import path
from .views import TodoView, CreateIssueView, ListIssuesView

urlpatterns = [
    path("",        TodoView.as_view(),        name="todos-index"),
    path("create/", CreateIssueView.as_view(), name="todos-create"),
    path("issues/", ListIssuesView.as_view(),  name="todos-list"),
]
