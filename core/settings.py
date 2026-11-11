from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-default-change-me")
DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "users",
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
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 days

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")       # Drive (Desktop app)
GOOGLE_WEB_CLIENT_ID     = os.environ.get("GOOGLE_WEB_CLIENT_ID", "")
GOOGLE_WEB_CLIENT_SECRET = os.environ.get("GOOGLE_WEB_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI      = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback/")
# Mobile apps sign in with Google on-device and send us the ID token
# (POST /api/users/google/). Its audience must be one of these client IDs:
# the web client (when the app uses it as its "server client ID") plus any
# comma-separated GOOGLE_ANDROID_CLIENT_ID / GOOGLE_IOS_CLIENT_ID.
GOOGLE_ID_TOKEN_AUDIENCES = [
    c.strip() for c in ",".join([
        GOOGLE_WEB_CLIENT_ID,
        os.environ.get("GOOGLE_ANDROID_CLIENT_ID", ""),
        os.environ.get("GOOGLE_IOS_CLIENT_ID", ""),
    ]).split(",") if c.strip()
]

# The one account that gets every app (Home/Books/Habits/Todos/Blogs/Splitwise);
# everyone else gets the expenses app only. Unset = nobody has full access.
OWNER_USER_ID = os.environ.get("OWNER_USER_ID", "").strip()

# Token auth for the users app (/api/users/). SIGNUP_ENABLED=False closes
# public signup once the accounts you want exist.
AUTH_TOKEN_TTL_DAYS = int(os.environ.get("AUTH_TOKEN_TTL_DAYS", "30"))
# Platform-wide key for internal tools (server-to-server). It can act as ANY user
# when the caller passes a uid, so keep it in the environment only. Anything
# shorter than 32 characters is treated as "not configured" (endpoints refuse).
INTERNAL_API_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "").strip()

# One line per internal call (who it acted as — never the token).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {"internal_api": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}

SIGNUP_ENABLED = os.environ.get("SIGNUP_ENABLED", "True") == "True"
# A bare 10-digit phone number is assumed to belong to this country.
DEFAULT_PHONE_COUNTRY_CODE = os.environ.get("DEFAULT_PHONE_COUNTRY_CODE", "+91")
# After this many wrong passwords an account is locked for LOGIN_LOCK_MINUTES.
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "5"))
LOGIN_LOCK_MINUTES = int(os.environ.get("LOGIN_LOCK_MINUTES", "15"))

# Postgres (currently only the expenses app's models use it). Left unset when
# DATABASE_URL is absent so everything else keeps running as before — the rest
# of the app doesn't touch the ORM, and Django falls back to a dummy backend.
if os.environ.get("DATABASE_URL"):
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.config(
            env="DATABASE_URL",
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=os.environ.get("DATABASE_SSL_REQUIRE", "True") == "True",
        )
    }
    # A pooled endpoint (Neon's "-pooler" host) runs PgBouncer in transaction
    # mode, where a server connection isn't tied to us between statements —
    # so no server-side cursors and no prepared statements.
    if "-pooler" in (DATABASES["default"].get("HOST") or ""):
        DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
        DATABASES["default"].setdefault("OPTIONS", {})["prepare_threshold"] = None

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
        "OPTIONS": {"context_processors": ["core.context.account"]},
    },
]

ROOT_URLCONF = "core.urls"

WSGI_APPLICATION = "core.wsgi.application"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
