from django.conf import settings

from users.models import User

from .expense import ExpensesDataService


def data_service_for(request) -> ExpensesDataService:
    """The data service for whoever is making ``request``.

    A signed-in account sees its own rows (scoped by user id). The open /api/
    routes have no session, so they act as the DEFAULT_EXPENSE_PROFILE's owner —
    today's single-user behaviour, unchanged. Where there's no account yet (a
    session from before accounts existed, or the default profile's owner hasn't
    signed in), it falls back to the legacy profile name.
    """
    session = request.session
    if not settings.DATABASES:
        return ExpensesDataService()  # not configured; callers check is_configured

    user_id = session.get("user_id")
    if user_id:
        return ExpensesDataService.from_env(session.get("notion_profile") or "", user_id)

    email = session.get("user_email")
    profile = session.get("notion_profile") or ""
    if not email:  # no session at all: the open /api/ routes
        profile = settings.DEFAULT_EXPENSE_PROFILE
        email = next((e for e, p in settings.ALLOWED_USERS.items() if p == profile), "")
    user_id = User.objects.filter(email=email).values_list("id", flat=True).first() if email else None
    return ExpensesDataService.from_env(profile, user_id)
