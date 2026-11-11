from django.conf import settings
from django.contrib.auth.hashers import is_password_usable
from django.db import IntegrityError

from ..models import User
from .auth import AuthError, AuthService


class ProfileService:
    """Reads and edits an account's contact details (name, email, phone)."""

    @staticmethod
    def to_dict(user: User) -> dict:
        return {
            "name": user.name,
            "email": user.email or "",
            "phone": user.phone or "",
            "picture": user.picture,
            "google": bool(user.google_sub),
            "has_password": is_password_usable(user.password),
            "email_verified": bool(user.email_verified),
            # A Google-verified email is the account's identity — and what unlocks
            # the full app for allow-listed addresses — so it can't be edited here.
            "email_locked": bool(user.email_verified),
            "created_at": user.created_at.isoformat(),
        }

    def update(self, user: User, name, email, phone) -> User:
        auth = AuthService()

        name = (name or "").strip() if isinstance(name, str) else ""
        if not name:
            raise AuthError("Enter your name")
        if len(name) > 150:
            raise AuthError("Name is too long")

        new_email = (email or "").strip() if isinstance(email, str) else ""
        if user.email_verified:
            if new_email and new_email.lower() != (user.email or ""):
                raise AuthError("Your email is verified through Google and can't be changed here")
            new_email = user.email
        elif new_email:
            new_email = auth._clean_email(new_email)
        else:
            new_email = None

        new_phone = (phone or "").strip() if isinstance(phone, str) else ""
        new_phone = auth._clean_phone(new_phone) if new_phone else None

        if not new_email and not new_phone:
            raise AuthError("Keep at least an email or a phone number")

        user.name = name
        user.email = new_email
        user.phone = new_phone
        try:
            user.save(update_fields=["name", "email", "phone"])
        except IntegrityError:
            raise AuthError("That email or phone number is already used by another account", 409)
        return user
