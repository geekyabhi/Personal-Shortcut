from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from ..views import GoogleLoginView, LoginView, LogoutView, MeView, SignupView

urlpatterns = [
    path("signup/", csrf_exempt(SignupView.as_view()), name="api-users-signup"),
    path("login/",  csrf_exempt(LoginView.as_view()),  name="api-users-login"),
    path("google/", csrf_exempt(GoogleLoginView.as_view()), name="api-users-google"),
    path("logout/", csrf_exempt(LogoutView.as_view()), name="api-users-logout"),
    path("me/",     csrf_exempt(MeView.as_view()),     name="api-users-me"),
]
