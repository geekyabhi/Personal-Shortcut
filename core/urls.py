from django.shortcuts import render
from django.urls import path, include


def home(request):
    return render(request, "home.html")


urlpatterns = [
    path("", home, name="home"),
    path("expenses/", include("expenses.urls")),
    path("habits/", include("habits.urls")),
    path("todos/",  include("todos.urls")),
    path("books/",  include("books.urls")),
    path("blogs/",  include("blogs.urls")),
]
