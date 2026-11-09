from django.contrib.postgres.fields import ArrayField
from django.db import models


class Expense(models.Model):
    """One expense row — or, when ``is_mandate`` is set, a recurring-payment
    template (excluded from spend totals; real occurrences point back at it
    through ``mandate``). Mirrors the columns of the Notion expenses database.
    """

    FREQUENCY_CHOICES = [
        ("Weekly", "Weekly"),
        ("Monthly", "Monthly"),
        ("Quarterly", "Quarterly"),
        ("Yearly", "Yearly"),
    ]

    # Legacy owner key: the EXPENSE_PROFILES name (e.g. "ABHINAV") of the old
    # per-profile Notion databases. Empty for accounts created since; ``user``
    # is what rows are scoped by.
    profile = models.CharField(max_length=64, blank=True, default="", db_index=True)

    # Owner. Nullable while rows are still keyed only by ``profile``; the
    # Notion import fills it in once the person has an account.
    user = models.ForeignKey(
        "users.User", null=True, blank=True, on_delete=models.PROTECT, related_name="expenses"
    )

    title = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Day the money moved; ``occurred_at`` additionally keeps the time of day
    # when one was recorded (Notion dates are either bare or full datetimes).
    date = models.DateField(null=True, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    # Minutes east of UTC the time was entered in (e.g. 330 for +05:30). The UI
    # shows the wall-clock digits of the datetime string, so reads rebuild the
    # string in this offset instead of handing back UTC.
    occurred_offset_min = models.SmallIntegerField(null=True, blank=True)

    categories = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    # Notion's Source is multi-select and Splitwise imports tag one per payer;
    # the app displays the first, so order matters.
    sources = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    mode = models.CharField(max_length=100, blank=True, default="")
    comment = models.TextField(blank=True, default="")
    other_partner = models.TextField(blank=True, default="")

    # Splitwise bookkeeping
    add_to_split = models.BooleanField(default=False)
    from_split = models.BooleanField(default=False)
    split_added = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    splitwise_id = models.BigIntegerField(null=True, blank=True)

    # Recurring mandates
    is_mandate = models.BooleanField(default=False)
    mandate_frequency = models.CharField(
        max_length=16, choices=FREQUENCY_CHOICES, blank=True, default=""
    )
    mandate_start = models.DateField(null=True, blank=True)
    mandate_end = models.DateField(null=True, blank=True)
    # Set on real expense rows generated from a mandate template.
    mandate = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="occurrences",
    )
    recurring = models.BooleanField(default=False)

    # Original Notion page id — lets the one-time import be re-run safely.
    notion_page_id = models.CharField(max_length=64, null=True, blank=True, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "expenses"
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["profile", "-date"], name="expense_profile_date_idx"),
            models.Index(fields=["user", "-date"], name="expense_user_date_idx"),
            models.Index(fields=["profile", "is_mandate"], name="expense_profile_mandate_idx"),
        ]
        constraints = [
            # A Splitwise expense can only be imported once per person.
            models.UniqueConstraint(
                fields=["profile", "splitwise_id"],
                condition=models.Q(splitwise_id__isnull=False) & ~models.Q(profile=""),
                name="expense_unique_splitwise_per_profile",
            ),
            models.UniqueConstraint(
                fields=["user", "splitwise_id"],
                condition=models.Q(splitwise_id__isnull=False),
                name="expense_unique_splitwise_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.amount})"
