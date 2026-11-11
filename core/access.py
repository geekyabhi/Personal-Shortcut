from django.conf import settings


def _is_owner(user_id) -> bool:
    # Fails closed: with OWNER_USER_ID unset, nobody is the owner.
    owner = settings.OWNER_USER_ID
    return bool(owner) and str(user_id or "") == owner


def is_full_access(session) -> bool:
    """True only for a session signed in as the owner account.

    Everyone else — a new password signup, any other Google account — gets the
    expenses app only. Default is "restricted": no signed-in account at all is
    the restricted case.
    """
    return _is_owner(session.get("user_id"))


def is_authenticated(session) -> bool:
    # user_email alone is a session from before accounts existed; still valid.
    return bool(session.get("user_id") or session.get("user_email"))


def user_has_full_access(user) -> bool:
    """The account-level twin of ``is_full_access`` (bearer-token requests)."""
    return bool(user) and _is_owner(user.id)
