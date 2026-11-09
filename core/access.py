from django.conf import settings


def is_full_access(session) -> bool:
    """True only for a session whose verified profile is in FULL_ACCESS_PROFILES.

    Everyone else — a new password signup, a Google account that isn't on the
    allow-list — gets the expenses app only. Default is "restricted": having no
    profile at all is the restricted case.
    """
    return session.get("notion_profile") in settings.FULL_ACCESS_PROFILES


def is_authenticated(session) -> bool:
    # user_email alone is a session from before accounts existed; still valid.
    return bool(session.get("user_id") or session.get("user_email"))


def user_has_full_access(user) -> bool:
    """The account-level twin of ``is_full_access``: a Google-verified account
    whose email is on the allow-list with a full-access profile."""
    if not (user and user.google_sub and user.email_verified and user.email):
        return False
    return settings.ALLOWED_USERS.get(user.email) in settings.FULL_ACCESS_PROFILES
