from django.shortcuts import render
from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt

from core.auth_views import login_view, auth_start, auth_callback, logout_view
from core.stats_view import HomeStatsView
from core.views_pwa import manifest, service_worker, pwa_icon, apple_touch_icon
from todos.views import CreateIssueView, ListIssuesView, DueSummaryView


def home(request):
    user = {
        "name":    request.session.get("user_name", ""),
        "picture": request.session.get("user_picture", ""),
        "email":   request.session.get("user_email", ""),
    }
    return render(request, "home.html", {"user": user})


urlpatterns = [
    path("", home, name="home"),
    path("home/stats/", HomeStatsView.as_view(), name="home-stats"),
    path("login/",          login_view,    name="login"),
    path("auth/google/",    auth_start,    name="auth-start"),
    path("auth/callback/",  auth_callback, name="auth-callback"),
    path("auth/logout/",    logout_view,   name="logout"),
    path("manifest.json",      manifest,       name="manifest"),
    path("service-worker.js",  service_worker, name="service-worker"),
    path("pwa-icon.svg",       pwa_icon,       name="pwa-icon"),
    path("apple-touch-icon.png", apple_touch_icon, name="apple-touch-icon"),
    path("expenses/", include("expenses.urls")),
    path("habits/",   include("habits.urls")),
    path("todos/",    include("todos.urls")),
    path("books/",    include("books.urls")),
    path("blogs/",    include("blogs.urls")),
    # Auth-free API endpoints (no session or CSRF required)
    path("api/todos/create/",      csrf_exempt(CreateIssueView.as_view()),  name="api-todos-create"),
    path("api/todos/issues/",      csrf_exempt(ListIssuesView.as_view()),   name="api-todos-list"),
    path("api/todos/due-summary/", csrf_exempt(DueSummaryView.as_view()),   name="api-todos-due-summary"),
]
