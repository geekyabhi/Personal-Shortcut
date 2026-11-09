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
    if request.GET.get("state") != request.session.get("oauth_state"):
        return redirect("/login/?error=state_mismatch")

    code = request.GET.get("code")
    if not code:
        return redirect(f"/login/?error={request.GET.get('error', 'cancelled')}")

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

    email = (info.get("email", "") or "").strip().lower()

    if not settings.DATABASES:
        # No database configured: the original Google-only, allow-list login.
        profile = settings.ALLOWED_USERS.get(email)
        if not profile:
            return redirect("/login/?error=unauthorized")
        request.session.pop("oauth_state", None)
        request.session["user_email"]     = email
        request.session["user_name"]      = info.get("name", email)
        request.session["user_picture"]   = info.get("picture", "")
        request.session["notion_profile"] = profile
        return redirect("/")

    from users.services import AuthError, AuthService
    try:
        user = AuthService().google_login(info)
    except AuthError:
        return redirect("/login/?error=unauthorized")
    _finish_login(request, user)
    return redirect("/")


def _finish_login(request, user):
    """Start the session for ``user``.

    ``notion_profile`` (the full-access marker) is only ever set for an
    allow-listed email that Google verified — never for a typed-in email or a
    phone number — so password signups can't claim it. Rows from the old
    per-profile databases are attached to the account the first time its owner
    signs in.
    """
    from expenses.models import Expense

    profile = ""
    if user.google_sub and user.email_verified and user.email:
        profile = settings.ALLOWED_USERS.get(user.email, "")

    request.session.flush()  # drops oauth_state and any previous login
    request.session["user_id"]        = str(user.id)
    request.session["user_email"]     = user.email or ""
    request.session["user_name"]      = user.display_name
    request.session["user_picture"]   = user.picture
    request.session["notion_profile"] = profile

    if profile:
        linked = Expense.objects.filter(profile=profile, user__isnull=True).update(user=user)
        if linked:  # their old expenses just became theirs — build their pick-lists from them
            from expenses.data_services.options import sync_from_expenses
            sync_from_expenses(user.id)


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
    request.session.flush()
    return redirect("/login/")
