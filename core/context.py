def account(request) -> dict:
    """The signed-in person, for the account button in each page's top bar."""
    session = getattr(request, "session", None)
    if session is None:
        return {}
    email = session.get("user_email") or ""
    name = session.get("user_name") or email
    return {
        "account": {
            "name": name,
            "email": email,
            "picture": session.get("user_picture") or "",
            "initial": (name[:1] or "?").upper(),
        }
    }
