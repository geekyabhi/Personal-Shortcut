"""
One-time command to authorize Google Drive access and print the refresh token.

Usage:
    python manage.py authorize_google

Then add the printed GOOGLE_REFRESH_TOKEN to your .env file.
"""
import os

from django.core.management.base import BaseCommand


SCOPES = [
    "https://www.googleapis.com/auth/drive",  # full access — needed to upload into existing folders
]


class Command(BaseCommand):
    help = "Authorize Google Drive and print the refresh token to store in .env"

    def handle(self, *args, **options):
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

        if not client_id or not client_secret:
            self.stderr.write(
                "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first.\n"
                "1. Go to https://console.cloud.google.com/\n"
                "2. Create a project → Enable Google Drive API\n"
                "3. Create OAuth 2.0 credentials (Desktop app type)\n"
                "4. Add client_id and client_secret to .env"
            )
            return

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            self.stderr.write("Run: pip install google-auth-oauthlib")
            return

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        creds = flow.run_local_server(port=0)

        self.stdout.write("\n✅ Authorization successful! Add this to your .env:\n")
        self.stdout.write(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}\n")
