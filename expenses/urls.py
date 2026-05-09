from django.urls import path
from .views import ExpensesSummaryView

urlpatterns = [
    path("summary/", ExpensesSummaryView.as_view(), name="expenses-summary"),
]
