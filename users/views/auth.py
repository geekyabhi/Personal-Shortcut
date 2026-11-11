import json

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from ..services import AuthError, AuthService
from .decorators import token_required


def _body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        raise AuthError("Invalid JSON body")
    if not isinstance(data, dict):
        raise AuthError("Expected a JSON object")
    return data


def _token_response(user, token, expires, status=200):
    return JsonResponse(
        {
            "user": user.to_dict(),
            "token": token,
            "token_type": "Bearer",
            "expires_at": expires.isoformat(),
        },
        status=status,
    )


class _AuthView(View):
    """Turns AuthError into a JSON error response."""

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except AuthError as exc:
            return JsonResponse({"error": exc.message}, status=exc.status)


class SignupView(_AuthView):
    http_method_names = ["post"]

    def post(self, request):
        data = _body(request)
        user, token, expires = AuthService().signup(
            email=data.get("email") or "", password=data.get("password"),
            name=data.get("name", ""), phone=data.get("phone") or "",
        )
        return _token_response(user, token, expires, status=201)


class LoginView(_AuthView):
    http_method_names = ["post"]

    def post(self, request):
        data = _body(request)
        # "identifier" is an email or a phone number; "email"/"phone" also work.
        identifier = data.get("identifier") or data.get("email") or data.get("phone")
        user, token, expires = AuthService().login(identifier, data.get("password"))
        return _token_response(user, token, expires)


class GoogleLoginView(_AuthView):
    """``{"id_token": "<Google ID token from the device>"}`` → the same payload
    as login. Lands in the same account as the web Google sign-in."""

    http_method_names = ["post"]

    def post(self, request):
        data = _body(request)
        user, token, expires = AuthService().google_token_login(data.get("id_token"))
        return _token_response(user, token, expires)


@method_decorator(token_required, name="post")
class LogoutView(_AuthView):
    """Revokes the presented token; ``{"all": true}`` revokes every token."""

    http_method_names = ["post"]

    def post(self, request):
        everywhere = bool(_body(request).get("all"))
        AuthService().logout(request.auth_token, everywhere=everywhere)
        return JsonResponse({"ok": True})


@method_decorator(token_required, name="get")
class MeView(_AuthView):
    http_method_names = ["get"]

    def get(self, request):
        return JsonResponse({"user": request.auth_user.to_dict()})
