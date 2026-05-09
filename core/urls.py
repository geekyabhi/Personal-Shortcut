from django.urls import path, include

urlpatterns = [
    path("expenses/", include("expenses.urls")),
]
