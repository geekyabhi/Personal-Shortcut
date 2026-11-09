import uuid

from django.db import models


class User(models.Model):
    """An account. ``id`` is the uid other tables (e.g. expenses) reference.

    Signs in with email and/or phone plus a password, or with Google. At least
    one of email / phone is always set; both are stored normalised and unique.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Lowercased. NULL (not "") when absent so several users can have no email.
    email = models.EmailField(unique=True, null=True, blank=True)
    # E.164, e.g. +919876543210.
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    name = models.CharField(max_length=150, blank=True, default="")
    picture = models.URLField(max_length=500, blank=True, default="")
    # Django-hashed (PBKDF2); an unusable value ("!…") for Google-only accounts.
    password = models.CharField(max_length=256)
    # Google's stable account id; set once the account has signed in with Google.
    google_sub = models.CharField(max_length=64, unique=True, null=True, blank=True)
    # True only when ownership of the email was proven (Google said so). Typed-in
    # emails stay unverified, so they never unlock anything privileged.
    email_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # Brute-force protection: too many bad passwords locks the account briefly.
    failed_logins = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "users"

    def __str__(self) -> str:
        return self.email or self.phone or str(self.id)

    @property
    def display_name(self) -> str:
        return self.name or self.email or self.phone or "Account"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "email": self.email,
            "phone": self.phone,
            "name": self.name,
        }
