import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from core.access import is_full_access

from ..models import User
from ..services import AuthError, ProfileService


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
        return render(request, "profile.html", {
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
