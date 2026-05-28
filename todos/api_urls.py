from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .views import CreateIssueView, ListIssuesView, DueSummaryView

urlpatterns = [
    path("create/",      csrf_exempt(CreateIssueView.as_view()),  name="api-todos-create"),
    path("issues/",      csrf_exempt(ListIssuesView.as_view()),   name="api-todos-list"),
    path("due-summary/", csrf_exempt(DueSummaryView.as_view()),   name="api-todos-due-summary"),
]
