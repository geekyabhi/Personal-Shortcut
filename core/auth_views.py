import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render

from core.access import is_authenticated


def login_view(request):
    if is_authenticated(request.session):
        return redirect("/")
    error = request.GET.get("error", "")
    return render(request, "login.html", {"error": error})


def auth_start(request):
    return _google_redirect(request)


def connect_google_start(request):
    """Start Google sign-in in 'link' mode for an account that is already
    signed in: the callback attaches the Google account to it instead of
    logging in as whoever Google says."""
    uid = request.session.get("user_id")
    if not uid or not settings.DATABASES:
        return redirect("/login/")
    request.session["link_user_id"] = uid
    return _google_redirect(request)


def _google_redirect(request):
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    params = urllib.parse.urlencode({
        "client_id":     settings.GOOGLE_WEB_CLIENT_ID,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "access_type":   "online",
    })
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


def auth_callback(request):
    linking = bool(request.session.get("link_user_id"))
    back = "/profile/" if linking else "/login/"
    if request.GET.get("state") != request.session.get("oauth_state"):
        request.session.pop("link_user_id", None)
        return redirect(f"{back}?error=state_mismatch")

    code = request.GET.get("code")
    if not code:
        request.session.pop("link_user_id", None)
        return redirect(f"{back}?error={request.GET.get('error', 'cancelled')}")

    redirect_uri = settings.GOOGLE_REDIRECT_URI

    # Exchange code → tokens
    try:
        body = urllib.parse.urlencode({
            "code":          code,
            "client_id":     settings.GOOGLE_WEB_CLIENT_ID,
            "client_secret": settings.GOOGLE_WEB_CLIENT_SECRET,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        }).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token", data=body, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            tokens = json.loads(resp.read())
    except Exception:
        return redirect("/login/?error=token_exchange_failed")

    access_token = tokens.get("access_token")
    if not access_token:
        return redirect("/login/?error=no_access_token")

    # Fetch user info
    try:
        req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            info = json.loads(resp.read())
    except Exception:
        return redirect("/login/?error=userinfo_failed")

    link_uid = request.session.pop("link_user_id", None)
    if link_uid:
        return _complete_link(request, link_uid, info)

    if not settings.DATABASES:
        return redirect("/login/?error=not_configured")

    from users.services import AuthError, AuthService
    try:
        user = AuthService().google_login(info)
    except AuthError:
        return redirect("/login/?error=unauthorized")
    _finish_login(request, user)
    return redirect("/")


def _complete_link(request, link_uid, info):
    """Attach the Google account to the signed-in account that asked for it."""
    from users.models import User
    from users.services import AuthError, AuthService

    user = User.objects.filter(pk=link_uid, is_active=True).first()
    if not user or str(user.id) != request.session.get("user_id"):
        return redirect("/profile/?error=Please+sign+in+again+and+retry")
    try:
        AuthService().link_google(user, info)
    except AuthError as exc:
        return redirect("/profile/?error=" + urllib.parse.quote_plus(exc.message))
    request.session.pop("oauth_state", None)
    request.session["user_name"] = user.display_name
    request.session["user_email"] = user.email or ""
    request.session["user_picture"] = user.picture
    return redirect("/profile/?linked=google")


def _finish_login(request, user):
    """Start the session for ``user``."""
    from users.services import AuthService

    request.session.flush()  # drops oauth_state and any previous login
    if getattr(user, "password_was_reset", False):
        request.session["notice"] = "password_reset"
    request.session["user_id"]        = str(user.id)
    request.session["auth_token_id"]  = AuthService().start_web_session(user)
    request.session["user_email"]     = user.email or ""
    request.session["user_name"]      = user.display_name
    request.session["user_picture"]   = user.picture


def _json_body(request):
    # Requiring a JSON body keeps a cross-site <form> from posting to these.
    if request.method != "POST":
        return None, JsonResponse({"error": "POST only"}, status=405)
    if request.content_type != "application/json":
        return None, JsonResponse({"error": "Expected application/json"}, status=415)
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return None, JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse({"error": "Expected a JSON object"}, status=400)
    if not settings.DATABASES:
        return None, JsonResponse({"error": "Accounts need a database (DATABASE_URL)"}, status=503)
    return data, None


def password_login(request):
    """Email-or-phone + password sign-in for the web UI."""
    data, err = _json_body(request)
    if err:
        return err
    from users.services import AuthError, AuthService
    try:
        user = AuthService().authenticate(data.get("identifier"), data.get("password"))
    except AuthError as exc:
        return JsonResponse({"error": exc.message}, status=exc.status)
    _finish_login(request, user)
    return JsonResponse({"ok": True, "redirect": "/"})


def password_signup(request):
    """Create an email and/or phone + password account, then sign it in."""
    data, err = _json_body(request)
    if err:
        return err
    from users.services import AuthError, AuthService
    if not (data.get("name") or "").strip():
        return JsonResponse({"error": "Enter your name"}, status=400)
    try:
        user = AuthService().create_user(
            data.get("password"), email=data.get("email") or "",
            phone=data.get("phone") or "", name=data.get("name") or "",
        )
    except AuthError as exc:
        return JsonResponse({"error": exc.message}, status=exc.status)
    _finish_login(request, user)
    return JsonResponse({"ok": True, "redirect": "/"}, status=201)


def logout_view(request):
    from users.services import AuthService

    if settings.DATABASES:
        AuthService().end_web_session(request.session.get("auth_token_id"))
    request.session.flush()
    return redirect("/login/")


def logout_all_view(request):
    """Sign out of every device (web sessions and API tokens). POST + JSON only,
    so a link on another site can't trigger it."""
    from users.services import AuthService
    from users.views.profile import session_user

    if request.method != "POST" or request.content_type != "application/json":
        return JsonResponse({"error": "POST application/json required"}, status=405)
    user = session_user(request)
    if user:
        AuthService().logout_everywhere(user)
    request.session.flush()
    return JsonResponse({"ok": True, "redirect": "/login/"})
