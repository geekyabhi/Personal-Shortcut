from django.db import models
from django.db.models.functions import Lower


class UserOption(models.Model):
    """A value a person has defined for one of an expense's pick-lists.

    Each person has their own list (``user`` is the uid). Expenses keep storing
    the plain text value; these tables are what the pickers offer, so a person's
    own categories / sources / modes are saved once and reused everywhere.
    Names are unique per person ignoring case ("Food" and "food" are one entry).
    """

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ExpenseCategory(UserOption):
    class Meta(UserOption.Meta):
        db_table = "expense_categories"
        verbose_name_plural = "expense categories"
        constraints = [
            models.UniqueConstraint(Lower("name"), "user", name="expense_category_unique_per_user"),
        ]


class ExpenseMode(UserOption):
    """How the money moved — UPI, Card, Cash …"""

    class Meta(UserOption.Meta):
        db_table = "expense_modes"
        constraints = [
            models.UniqueConstraint(Lower("name"), "user", name="expense_mode_unique_per_user"),
        ]


class ExpenseSource(UserOption):
    """Where the money came from — an account, card or wallet."""

    class Meta(UserOption.Meta):
        db_table = "expense_sources"
        constraints = [
            models.UniqueConstraint(Lower("name"), "user", name="expense_source_unique_per_user"),
        ]
