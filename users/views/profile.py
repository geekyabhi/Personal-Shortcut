import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from core.access import is_full_access

from ..models import User
from ..services import AuthError, AuthService, ProfileService


def session_user(request):
    """The signed-in account for a web session, or None.

    Sessions from before accounts existed only carry an email, so fall back to
    looking the account up by it."""
    if not settings.DATABASES:
        return None
    user_id = request.session.get("user_id")
    if user_id:
        return User.objects.filter(pk=user_id, is_active=True).first()
    email = request.session.get("user_email")
    return User.objects.filter(email=email, is_active=True).first() if email else None


class ProfilePageView(View):
    def get(self, request):
        user = session_user(request)
        # Messages from the Connect-Google round trip / a forced password reset.
        notice = request.session.pop("notice", "")
        banner = None
        if request.GET.get("linked") == "google":
            banner = ("ok", "Google is connected. You can now sign in with Google, email or phone — they all open this same account.")
        elif request.GET.get("error"):
            banner = ("error", request.GET["error"][:200])
        elif notice == "password_reset":
            banner = ("error", "For safety your old password was cleared when this email was verified through Google. Set a new password below to keep email / phone sign-in.")
        return render(request, "profile.html", {
            "banner": banner,
            "profile": ProfileService.to_dict(user) if user else None,
            "initial": (user.display_name[:1] if user else "?").upper(),
            "restricted": not is_full_access(request.session),
        })


class ProfileDataView(View):
    http_method_names = ["get", "post"]

    def get(self, request):
        user = session_user(request)
        if not user:
            return JsonResponse({"error": "Please sign in again"}, status=401)
        return JsonResponse({"profile": ProfileService.to_dict(user)})

    def post(self, request):
        # Requiring a JSON body keeps a cross-site <form> from posting here.
        if request.content_type != "application/json":
            return JsonResponse({"error": "Expected application/json"}, status=415)
        user = session_user(request)
        if not user:
            return JsonResponse({"error": "Please sign in again"}, status=401)
        try:
            data = json.loads(request.body or b"{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        try:
            user = ProfileService().update(
                user, data.get("name"), data.get("email"), data.get("phone")
            )
        except AuthError as exc:
            return JsonResponse({"error": exc.message}, status=exc.status)

        # Keep the header chip in step with the saved profile.
        request.session["user_name"] = user.display_name
        request.session["user_email"] = user.email or ""
        request.session["user_id"] = str(user.id)
        return JsonResponse({"ok": True, "profile": ProfileService.to_dict(user)})


class PasswordView(View):
    """Set or change the password of the signed-in account.

    This is what lets a Google-created account also sign in with email or
    phone + password (and any password account keep one after connecting
    Google) — they all resolve to the same account."""

    http_method_names = ["post"]

    def post(self, request):
        if request.content_type != "application/json":
            return JsonResponse({"error": "Expected application/json"}, status=415)
        user = session_user(request)
        if not user:
            return JsonResponse({"error": "Please sign in again"}, status=401)
        try:
            data = json.loads(request.body or b"{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        try:
            AuthService().set_password(
                user, data.get("new_password"), data.get("current_password"),
                keep_token_id=request.session.get("auth_token_id"),
            )
        except AuthError as exc:
            return JsonResponse({"error": exc.message}, status=exc.status)
        return JsonResponse({"ok": True, "profile": ProfileService.to_dict(user)})
