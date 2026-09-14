from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .views import (
    CreateIssueView, ListIssuesView, DueSummaryView, SprintView,
    IssueTransitionView, IssueAssigneeView, IssueSprintView, SprintCloseView, SprintCreateView, MetaView,
    IssueDetailView, IssueUpdateView, IssueDeleteView, SprintDeleteView,
)

urlpatterns = [
    path("create/",      csrf_exempt(CreateIssueView.as_view()),  name="api-todos-create"),
    path("issues/",      csrf_exempt(ListIssuesView.as_view()),   name="api-todos-list"),
    path("sprint/",      csrf_exempt(SprintView.as_view()),       name="api-todos-sprint"),
    path("sprint/new/",    csrf_exempt(SprintCreateView.as_view()), name="api-todos-sprint-new"),
    path("sprint/close/",  csrf_exempt(SprintCloseView.as_view()),  name="api-todos-sprint-close"),
    path("sprint/delete/", csrf_exempt(SprintDeleteView.as_view()), name="api-todos-sprint-delete"),
    path("meta/",         csrf_exempt(MetaView.as_view()),         name="api-todos-meta"),
    path("issues/<str:key>/",            csrf_exempt(IssueDetailView.as_view()),     name="api-todos-issue-detail"),
    path("issues/<str:key>/update/",     csrf_exempt(IssueUpdateView.as_view()),     name="api-todos-issue-update"),
    path("issues/<str:key>/delete/",     csrf_exempt(IssueDeleteView.as_view()),     name="api-todos-issue-delete"),
    path("issues/<str:key>/transition/", csrf_exempt(IssueTransitionView.as_view()), name="api-todos-issue-transition"),
    path("issues/<str:key>/assignee/",   csrf_exempt(IssueAssigneeView.as_view()),   name="api-todos-issue-assignee"),
    path("issues/<str:key>/sprint/",     csrf_exempt(IssueSprintView.as_view()),     name="api-todos-issue-sprint"),
    path("due-summary/", csrf_exempt(DueSummaryView.as_view()),   name="api-todos-due-summary"),
]
