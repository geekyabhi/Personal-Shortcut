from django.db import models


class AuthToken(models.Model):
    """A bearer token issued at signup/login. Only the SHA-256 of the token is
    stored, so a database leak doesn't hand out usable tokens."""

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "auth_tokens"
