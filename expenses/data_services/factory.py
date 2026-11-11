from django.conf import settings

from users.models import User

from .expense import ExpensesDataService


def data_service_for(request) -> ExpensesDataService:
    """The data service for whoever is making ``request`` — always scoped to ONE person.

    * Bearer-token API call: the uid comes from the token (``request.auth_user``,
      set by ``token_required``).
    * Web session: the signed-in account's uid. A session from before accounts
      existed only has an email, so look the account up by it (or fall back to
      the legacy profile name for rows not linked to an account yet).
    * Anything else gets a service that can see nothing — there is no default
      owner any more.
    """
    if not settings.DATABASES:
        return ExpensesDataService()  # not configured; callers check is_configured

    auth_user = getattr(request, "auth_user", None)
    if auth_user is not None:
        return ExpensesDataService.from_env("", auth_user.id)

    session = request.session
    user_id = session.get("user_id")
    if user_id:
        return ExpensesDataService.from_env("", user_id)

    email = session.get("user_email")
    if not email:
        return ExpensesDataService()  # nobody identified: scope is empty
    user_id = User.objects.filter(email=email).values_list("id", flat=True).first()
    return ExpensesDataService.from_env("", user_id)
