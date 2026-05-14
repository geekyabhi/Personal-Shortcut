from django.urls import path
from .views import TodoView, CreateIssueView, ListIssuesView, DueSummaryView

urlpatterns = [
    path("",            TodoView.as_view(),        name="todos-index"),
    path("create/",     CreateIssueView.as_view(), name="todos-create"),
    path("issues/",     ListIssuesView.as_view(),  name="todos-list"),
    path("due-summary/", DueSummaryView.as_view(), name="todos-due-summary"),
]
