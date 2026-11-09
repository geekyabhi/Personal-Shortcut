import hashlib
import re
import secrets
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from django.contrib.auth.hashers import check_password, is_password_usable, make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.utils import timezone

from ..models import AuthToken, User


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    # Checked against when the account is unknown, so "no such user" and "wrong
    # password" take the same time.
    return make_password("not-a-real-password")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AuthService:
    MIN_PASSWORD = 8
    MAX_PASSWORD = 128  # bounds the work PBKDF2 does on a hostile input
    TOUCH_INTERVAL = timedelta(minutes=5)  # how often last_used_at is rewritten
    PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")

    # ---------------------------------------------------------------- #
    #  Accounts                                                         #
    # ---------------------------------------------------------------- #

    def create_user(self, password: str, email: str = "", phone: str = "", name: str = "") -> User:
        """Password account from an email and/or a phone number."""
        if not settings.SIGNUP_ENABLED:
            raise AuthError("Signup is disabled", 403)
        email = self._clean_email(email) if (email or "").strip() else None
        phone = self._clean_phone(phone) if (phone or "").strip() else None
        if not email and not phone:
            raise AuthError("Enter an email or a phone number")
        if email and email in settings.ALLOWED_USERS:
            # These addresses unlock the whole app and a typed-in email proves
            # nothing, so they can only be claimed through Google.
            raise AuthError("This email signs in with Google — use the Google button", 409)
        if not isinstance(password, str) or not (self.MIN_PASSWORD <= len(password) <= self.MAX_PASSWORD):
            raise AuthError(f"Password must be {self.MIN_PASSWORD}-{self.MAX_PASSWORD} characters")
        try:
            return User.objects.create(
                email=email,
                phone=phone,
                name=(name or "").strip()[:150],
                password=make_password(password),
            )
        except IntegrityError:
            raise AuthError("An account with this email or phone already exists", 409)

    def authenticate(self, identifier: str, password: str) -> User:
        """The user for an email-or-phone + password pair, else AuthError."""
        user = self._find(identifier)
        now = timezone.now()
        if user and user.locked_until and user.locked_until > now:
            raise AuthError("Too many failed attempts. Try again in a few minutes.", 429)

        stored = user.password if user else _dummy_hash()
        ok = check_password(password if isinstance(password, str) else "", stored)
        if not (user and ok and user.is_active):
            if user:
                user.failed_logins += 1
                if user.failed_logins >= settings.LOGIN_MAX_FAILURES:
                    user.failed_logins = 0
                    user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                user.save(update_fields=["failed_logins", "locked_until"])
            raise AuthError("Invalid email/phone or password", 401)

        user.failed_logins = 0
        user.locked_until = None
        user.last_login_at = now
        user.save(update_fields=["failed_logins", "locked_until", "last_login_at"])
        return user

    def google_login(self, info: dict) -> User:
        """The user for a Google userinfo payload, creating or linking one.

        ``info`` is Google's userinfo (sub, email, email_verified, name, picture).
        """
        sub = str(info.get("sub") or "")
        email = (info.get("email") or "").strip().lower()
        if not sub or not email or not info.get("email_verified"):
            raise AuthError("Your Google email is not verified", 403)

        user = User.objects.filter(google_sub=sub).first()
        if not user:
            user = User.objects.filter(email=email).first()
            if user:
                if not user.email_verified:
                    # Someone registered this address with a password before its
                    # owner ever proved it. Cut those credentials off (the person
                    # can set a fresh password from their Profile; to keep an
                    # existing password, connect Google from the Profile page
                    # while signed in instead of signing in with Google first).
                    if is_password_usable(user.password):
                        user.password_was_reset = True
                    user.password = make_password(None)
                    user.tokens.all().delete()
                user.google_sub = sub
                user.email_verified = True
            else:
                if not (settings.SIGNUP_ENABLED or email in settings.ALLOWED_USERS):
                    raise AuthError("Signup is disabled", 403)
                user = User(email=email, google_sub=sub, email_verified=True,
                            password=make_password(None))
        if not user.is_active:
            raise AuthError("This account is disabled", 403)

        user.name = user.name or (info.get("name") or "").strip()[:150]
        user.picture = info.get("picture") or user.picture
        user.last_login_at = timezone.now()
        user.save()
        return user

    def set_password(self, user: User, new_password: str, current_password: str = None, keep_token_id=None) -> None:
        """Set or change the password of a signed-in account.

        An account that already has a password must give the current one; a
        Google-only account (no password yet) can simply set its first.
        Changing it signs out every other device and API token (the one the
        change was made from, ``keep_token_id``, stays signed in)."""
        if not isinstance(new_password, str) or not (self.MIN_PASSWORD <= len(new_password) <= self.MAX_PASSWORD):
            raise AuthError(f"Password must be {self.MIN_PASSWORD}-{self.MAX_PASSWORD} characters")
        if is_password_usable(user.password):
            if not check_password(current_password if isinstance(current_password, str) else "", user.password):
                raise AuthError("Your current password is incorrect")
        user.password = make_password(new_password)
        user.failed_logins = 0
        user.locked_until = None
        user.save(update_fields=["password", "failed_logins", "locked_until"])
        user.tokens.exclude(pk=keep_token_id).delete()

    def link_google(self, user: User, info: dict) -> User:
        """Attach a Google account to an account that is already signed in.

        Safe by construction — the person has just proved control of BOTH the
        account (they're signed in) and the Google account (they completed
        Google's sign-in) — so nothing is wiped and every existing sign-in
        method keeps working. From then on Google lands in this same account."""
        sub = str(info.get("sub") or "")
        email = (info.get("email") or "").strip().lower()
        if not sub or not email or not info.get("email_verified"):
            raise AuthError("Your Google email is not verified", 403)
        if User.objects.filter(google_sub=sub).exclude(pk=user.pk).exists():
            raise AuthError("That Google account is already connected to a different account", 409)
        if user.google_sub and user.google_sub != sub:
            raise AuthError("A different Google account is already connected to this account", 409)
        if not user.email:
            if User.objects.filter(email=email).exclude(pk=user.pk).exists():
                raise AuthError("That Google email already belongs to a different account", 409)
            user.email, user.email_verified = email, True
        elif user.email == email:
            user.email_verified = True      # Google just proved they own it
        user.google_sub = sub
        user.picture = user.picture or info.get("picture") or ""
        user.name = user.name or (info.get("name") or "").strip()[:150]
        user.save()
        return user

    # ---------------------------------------------------------------- #
    #  API tokens (bearer)                                              #
    # ---------------------------------------------------------------- #

    def signup(self, email: str = "", password: str = "", name: str = "", phone: str = "") -> tuple:
        user = self.create_user(password, email=email, phone=phone, name=name)
        return user, *self._issue_token(user)

    def login(self, identifier: str, password: str) -> tuple:
        user = self.authenticate(identifier, password)
        user.tokens.filter(expires_at__lt=timezone.now()).delete()  # tidy expired ones
        return user, *self._issue_token(user)

    def logout(self, raw_token: str, everywhere: bool = False) -> int:
        """Revoke the presented token (or all of the user's tokens)."""
        token = AuthToken.objects.filter(token_hash=_hash_token(raw_token)).first()
        if not token:
            return 0
        qs = AuthToken.objects.filter(user_id=token.user_id) if everywhere else AuthToken.objects.filter(pk=token.pk)
        deleted, _ = qs.delete()
        return deleted

    def start_web_session(self, user: User) -> int:
        """Every browser login gets its own token row (the cookie only carries its
        id, never a usable token). Deleting the row signs that device out."""
        token = AuthToken.objects.create(
            user=user,
            token_hash=_hash_token(secrets.token_urlsafe(32)),   # never revealed: the cookie holds the row id only
            expires_at=timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE),
        )
        return token.id

    def end_web_session(self, token_id) -> None:
        if token_id:
            AuthToken.objects.filter(pk=token_id).delete()

    def logout_everywhere(self, user: User) -> None:
        """Sign the account out of every device: web sessions and bearer tokens
        are all rows in one table."""
        user.tokens.all().delete()

    @staticmethod
    def session_is_valid(user_id: str, token_id) -> bool:
        """A web session lives only while its token row exists, is unexpired,
        and the account is active."""
        if not token_id:
            return False
        return AuthToken.objects.filter(
            pk=token_id, user_id=user_id, user__is_active=True, expires_at__gt=timezone.now()
        ).exists()

    def user_for_token(self, raw_token: str):
        """The active user a valid, unexpired token belongs to — else None."""
        if not raw_token:
            return None
        now = timezone.now()
        token = (
            AuthToken.objects.select_related("user")
            .filter(token_hash=_hash_token(raw_token), expires_at__gt=now, user__is_active=True)
            .first()
        )
        if not token:
            return None
        if not token.last_used_at or now - token.last_used_at > self.TOUCH_INTERVAL:
            AuthToken.objects.filter(pk=token.pk).update(last_used_at=now)
        return token.user

    # ---------------------------------------------------------------- #
    #  Internals                                                        #
    # ---------------------------------------------------------------- #

    def _find(self, identifier):
        ident = identifier.strip() if isinstance(identifier, str) else ""
        if not ident:
            return None
        if "@" in ident:
            return User.objects.filter(email=ident.lower()).first()
        try:
            return User.objects.filter(phone=self._clean_phone(ident)).first()
        except AuthError:
            return None

    @staticmethod
    def _clean_email(email) -> str:
        email = email.strip().lower() if isinstance(email, str) else ""
        try:
            validate_email(email)
        except ValidationError:
            raise AuthError("Enter a valid email address")
        return email

    def _clean_phone(self, phone) -> str:
        """Normalise to E.164. A bare 10-digit number gets
        DEFAULT_PHONE_COUNTRY_CODE; anything else needs its own + / 00 prefix."""
        raw = phone.strip() if isinstance(phone, str) else ""
        digits = re.sub(r"[\s\-().]", "", raw)
        if digits.startswith("00"):
            digits = "+" + digits[2:]
        elif not digits.startswith("+") and len(digits) == 10:
            digits = settings.DEFAULT_PHONE_COUNTRY_CODE + digits
        if not self.PHONE_RE.match(digits):
            raise AuthError("Enter a valid phone number, e.g. +91 98765 43210")
        return digits

    @staticmethod
    def _issue_token(user: User, days: int = None) -> tuple:
        raw = secrets.token_urlsafe(32)
        expires = timezone.now() + timedelta(days=days or settings.AUTH_TOKEN_TTL_DAYS)
        AuthToken.objects.create(user=user, token_hash=_hash_token(raw), expires_at=expires)
        return raw, expires
