from django.core.management.base import BaseCommand, CommandError

from expenses.data_services.options import sync_from_expenses
from users.models import User


class Command(BaseCommand):
    help = (
        "Fill each person's category / source / mode lists from the values their "
        "expenses already use. Safe to re-run — it only adds what is missing."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Only this account (default: every account).")

    def handle(self, *args, **opts):
        users = User.objects.all()
        if opts["email"]:
            users = users.filter(email=opts["email"].strip().lower())
            if not users:
                raise CommandError(f"No account with email {opts['email']}")
        for user in users:
            added = sync_from_expenses(user.id)
            self.stdout.write(
                f"{user.email or user.phone}: +{added['categories']} categories, "
                f"+{added['sources']} sources, +{added['modes']} modes"
            )
