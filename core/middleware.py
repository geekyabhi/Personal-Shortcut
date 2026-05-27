from django.shortcuts import redirect

_PUBLIC = {
    "/login/", "/auth/google/", "/auth/callback/", "/auth/logout/",
    "/manifest.json", "/service-worker.js", "/pwa-icon.svg", "/apple-touch-icon.png",
}


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path not in _PUBLIC and not request.session.get("user_email"):
            return redirect("/login/")
        response = self.get_response(request)
        response["Content-Security-Policy"] = "upgrade-insecure-requests"
        return response
