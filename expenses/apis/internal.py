"""Internal-tool API (mounted at /api/internal/expenses/).

Not for end users. Callers authenticate with the platform key
(``X-Internal-Token``) and say which account to act as (``X-User-Id`` header,
``uid`` in the body, or ``?uid=``). Only these two operations exist here.
"""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from users.views import internal_token_required

from ..views import ExpensesCreateView, ExpensesListView


def internal(view):
    return csrf_exempt(internal_token_required(view.as_view()))


urlpatterns = [
    path("create/", internal(ExpensesCreateView), name="internal-expenses-create"),
    path("list/",   internal(ExpensesListView),   name="internal-expenses-list"),
]
