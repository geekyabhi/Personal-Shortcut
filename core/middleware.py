from django.conf import settings
from django.shortcuts import redirect

from core.access import is_authenticated, is_full_access

_PUBLIC = {
    "/login/", "/auth/google/", "/auth/callback/", "/auth/logout/",
    "/auth/login/", "/auth/signup/",
    "/manifest.json", "/service-worker.js", "/pwa-icon.svg", "/apple-touch-icon.png",
}


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path not in _PUBLIC
            and not request.path.startswith("/api/")
            and not is_authenticated(request.session)
        ):
            return redirect("/login/")

        uid = request.session.get("user_id")
        if uid and settings.DATABASES and request.path not in _PUBLIC and not request.path.startswith("/api/"):
            from users.services import AuthService

            if not AuthService.session_is_valid(uid, request.session.get("auth_token_id")):
                request.session.flush()
                return redirect("/login/")

        # Anyone without full access only gets the expenses app —
        # everything else (home, books, habits, todos, blogs) bounces back.
        # Splitwise is further restricted even within expenses — it's tied to
        # one shared personal Splitwise account, not per-profile.
        if (
            request.path not in _PUBLIC
            and not request.path.startswith("/api/")
            and not is_full_access(request.session)
        ):
            in_expenses = request.path.startswith("/expenses/") and not request.path.startswith("/expenses/splitwise/")
            in_profile = request.path.startswith("/profile/")
            if not (in_expenses or in_profile):
                return redirect("/expenses/")

        response = self.get_response(request)
        response["Content-Security-Policy"] = "upgrade-insecure-requests"
        return response
