import json
import urllib.request
import urllib.error

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render


def login_view(request):
    if request.session.get("user_email"):
        return redirect("/")
    return render(request, "login.html", {"client_id": settings.GOOGLE_CLIENT_ID})


def auth_callback(request):
    if request.method != "POST":
        return redirect("/login/")

    try:
        data = json.loads(request.body)
        credential = data.get("credential", "").strip()
    except Exception:
        return JsonResponse({"error": "Invalid request"}, status=400)

    if not credential:
        return JsonResponse({"error": "Missing credential"}, status=400)

    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            info = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return JsonResponse({"error": "Token verification failed"}, status=401)
    except Exception:
        return JsonResponse({"error": "Could not reach Google"}, status=502)

    email = info.get("email", "")
    allowed = getattr(settings, "ALLOWED_EMAIL", "")

    if email != allowed:
        return JsonResponse({"error": "Not authorised"}, status=403)

    request.session["user_email"] = email
    request.session["user_name"] = info.get("name", email)
    request.session["user_picture"] = info.get("picture", "")
    return JsonResponse({"ok": True})


def logout_view(request):
    request.session.flush()
    return redirect("/login/")
