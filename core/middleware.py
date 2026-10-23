from django.conf import settings
from django.shortcuts import redirect

_PUBLIC = {
    "/login/", "/auth/google/", "/auth/callback/", "/auth/logout/",
    "/manifest.json", "/service-worker.js", "/pwa-icon.svg", "/apple-touch-icon.png",
}


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path not in _PUBLIC
            and not request.path.startswith("/api/")
            and not request.session.get("user_email")
        ):
            return redirect("/login/")

        # A profile outside FULL_ACCESS_PROFILES only gets the expenses app —
        # everything else (home, books, habits, todos, blogs) bounces back.
        # Splitwise is further restricted even within expenses — it's tied to
        # one shared personal Splitwise account, not per-profile.
        profile = request.session.get("notion_profile")
        if profile and profile not in settings.FULL_ACCESS_PROFILES:
            in_expenses = request.path.startswith("/expenses/") and not request.path.startswith("/expenses/splitwise/")
            if (
                request.path not in _PUBLIC
                and not request.path.startswith("/api/")
                and not in_expenses
            ):
                return redirect("/expenses/")

        response = self.get_response(request)
        response["Content-Security-Policy"] = "upgrade-insecure-requests"
        return response
