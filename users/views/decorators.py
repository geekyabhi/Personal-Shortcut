import hmac
import json
import logging
import uuid
from functools import wraps

from django.conf import settings
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


def full_access_required(view):
    """Stack *under* ``token_required``: only the account owner may call it
    (e.g. Splitwise, which runs on the owner's own Splitwise credentials)."""
    from core.access import user_has_full_access

    @wraps(view)
    def wrapper(*args, **kwargs):
        request = args[1] if len(args) > 1 and hasattr(args[1], "META") else args[0]
        if not user_has_full_access(getattr(request, "auth_user", None)):
            return JsonResponse({"error": "This endpoint is only available to the account owner"}, status=403)
        return view(*args, **kwargs)

    return wrapper


logger = logging.getLogger("internal_api")
MIN_INTERNAL_TOKEN_LENGTH = 32


def _internal_uid(request) -> str:
    """The uid an internal tool wants to act as: ``X-User-Id`` header, else
    ``uid`` / ``user_id`` in a JSON body, else ``?uid=`` / ``?user_id=``."""
    header = request.META.get("HTTP_X_USER_ID", "").strip()
    if header:
        return header
    if request.content_type == "application/json" and request.body:
        try:
            body = json.loads(request.body)
        except ValueError:
            body = None
        if isinstance(body, dict):
            for key in ("uid", "user_id"):
                if body.get(key):
                    return str(body[key]).strip()
    return (request.GET.get("uid") or request.GET.get("user_id") or "").strip()


def internal_token_required(view):
    """Guard for internal tools: ``X-Internal-Token: <platform key>`` plus the uid
    to act as (header / body / query). Sets ``request.auth_user`` to that user, so
    the normal views then run scoped to them. Fails closed: with no key
    configured, nothing gets through."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        request = args[1] if len(args) > 1 and hasattr(args[1], "META") else args[0]
        expected = settings.INTERNAL_API_TOKEN
        if len(expected) < MIN_INTERNAL_TOKEN_LENGTH:
            return JsonResponse({"error": "The internal API is not configured"}, status=503)
        provided = request.META.get("HTTP_X_INTERNAL_TOKEN", "")
        if not hmac.compare_digest(provided.encode(), expected.encode()):  # constant time
            return JsonResponse({"error": "Invalid internal token"}, status=401)

        raw_uid = _internal_uid(request)
        if not raw_uid:
            return JsonResponse(
                {"error": "uid is required: X-User-Id header, `uid` in the JSON body, or ?uid="}, status=400
            )
        try:
            uid = uuid.UUID(raw_uid)
        except ValueError:
            return JsonResponse({"error": "uid must be a UUID"}, status=400)
        from ..models import User

        user = User.objects.filter(pk=uid, is_active=True).first()
        if not user:
            return JsonResponse({"error": "No such user"}, status=404)

        request.auth_user = user
        logger.info("%s %s as user %s", request.method, request.path, user.id)
        return view(*args, **kwargs)

    return wrapper
