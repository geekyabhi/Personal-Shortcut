import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.shortcuts import redirect, render


def login_view(request):
    if request.session.get("user_email"):
        return redirect("/")
    error = request.GET.get("error", "")
    return render(request, "login.html", {"error": error})


def auth_start(request):
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    redirect_uri = request.build_absolute_uri("/auth/callback/")
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

    redirect_uri = request.build_absolute_uri("/auth/callback/")

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

    email = info.get("email", "")
    if email != getattr(settings, "ALLOWED_EMAIL", ""):
        return redirect("/login/?error=unauthorized")

    request.session.pop("oauth_state", None)
    request.session["user_email"]   = email
    request.session["user_name"]    = info.get("name", email)
    request.session["user_picture"] = info.get("picture", "")
    return redirect("/")


def logout_view(request):
    request.session.flush()
    return redirect("/login/")
