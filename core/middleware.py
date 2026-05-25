from django.shortcuts import redirect

_PUBLIC = {"/login/", "/auth/callback/", "/auth/logout/"}


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path not in _PUBLIC and not request.session.get("user_email"):
            return redirect("/login/")
        return self.get_response(request)
