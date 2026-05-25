from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-default-change-me")
DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "expenses",
    "todos",
    "books",
    "blogs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.middleware.LoginRequiredMiddleware",
]

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 days

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")       # Drive (Desktop app)
GOOGLE_WEB_CLIENT_ID     = os.environ.get("GOOGLE_WEB_CLIENT_ID", "")
GOOGLE_WEB_CLIENT_SECRET = os.environ.get("GOOGLE_WEB_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI      = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback/")
ALLOWED_EMAIL = os.environ.get("ALLOWED_EMAIL", "abhi0strike@gmail.com")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "core" / "templates",
            BASE_DIR / "expenses" / "templates",
            BASE_DIR / "habits" / "templates",
            BASE_DIR / "todos" / "templates",
            BASE_DIR / "books" / "templates",
            BASE_DIR / "blogs" / "templates",
        ],
        "APP_DIRS": False,
        "OPTIONS": {"context_processors": []},
    },
]

ROOT_URLCONF = "core.urls"

WSGI_APPLICATION = "core.wsgi.application"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
