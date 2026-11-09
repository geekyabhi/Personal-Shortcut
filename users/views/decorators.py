from functools import wraps

from django.http import JsonResponse

from ..services import AuthService


def bearer_token(request) -> str:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def token_required(view):
    """Guard a view with ``Authorization: Bearer <token>``. On success sets
    ``request.auth_user`` (the User, whose ``.id`` is the uid) and
    ``request.auth_token`` (the raw token). Works on function views and on
    class-based methods (``@method_decorator`` / direct use)."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        request = args[1] if len(args) > 1 and hasattr(args[1], "META") else args[0]
        raw = bearer_token(request)
        user = AuthService().user_for_token(raw)
        if not user:
            return JsonResponse({"error": "Invalid or expired token"}, status=401)
        request.auth_user = user
        request.auth_token = raw
        return view(*args, **kwargs)

    return wrapper
