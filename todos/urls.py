from django.urls import path
from .views import (
    TodoView, ChartsView, CreateIssueView, ListIssuesView, DueSummaryView, SprintView,
    IssueTransitionView, IssueAssigneeView, IssueSprintView, SprintCloseView, SprintCreateView, MetaView,
    IssueDetailView, IssueUpdateView, IssueDeleteView, SprintDeleteView,
)

urlpatterns = [
    path("",            TodoView.as_view(),        name="todos-index"),
    path("charts/",      ChartsView.as_view(),      name="todos-charts"),
    path("create/",     CreateIssueView.as_view(), name="todos-create"),
    path("issues/",     ListIssuesView.as_view(),  name="todos-list"),
    path("sprint/",     SprintView.as_view(),      name="todos-sprint"),
    path("sprint/new/",    SprintCreateView.as_view(), name="todos-sprint-new"),
    path("sprint/close/",  SprintCloseView.as_view(),  name="todos-sprint-close"),
    path("sprint/delete/", SprintDeleteView.as_view(), name="todos-sprint-delete"),
    path("meta/",        MetaView.as_view(),        name="todos-meta"),
    path("issues/<str:key>/",            IssueDetailView.as_view(),     name="todos-issue-detail"),
    path("issues/<str:key>/update/",     IssueUpdateView.as_view(),     name="todos-issue-update"),
    path("issues/<str:key>/delete/",     IssueDeleteView.as_view(),     name="todos-issue-delete"),
    path("issues/<str:key>/transition/", IssueTransitionView.as_view(), name="todos-issue-transition"),
    path("issues/<str:key>/assignee/",   IssueAssigneeView.as_view(),   name="todos-issue-assignee"),
    path("issues/<str:key>/sprint/",     IssueSprintView.as_view(),     name="todos-issue-sprint"),
    path("due-summary/", DueSummaryView.as_view(), name="todos-due-summary"),
]
