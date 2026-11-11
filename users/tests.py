import json
from unittest import mock

from django.test import TestCase, override_settings

from users.models import User

GOOD = {"sub": "g-123", "email": "new@example.com", "email_verified": True, "name": "New Person", "picture": ""}


def _post(client, token="tok"):
    return client.post("/api/users/google/", json.dumps({"id_token": token}), content_type="application/json")


@override_settings(GOOGLE_ID_TOKEN_AUDIENCES=["web-client-id"], SIGNUP_ENABLED=True)
class GoogleTokenLoginTests(TestCase):
    verify = "google.oauth2.id_token.verify_oauth2_token"

    def test_new_user_gets_bearer_token_that_works(self):
        with mock.patch(self.verify, return_value=GOOD) as verify:
            resp = _post(self.client)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(verify.call_args.kwargs["audience"], ["web-client-id"])
        body = resp.json()
        self.assertEqual(body["user"]["email"], "new@example.com")
        me = self.client.get("/api/users/me/", HTTP_AUTHORIZATION=f"Bearer {body['token']}")
        self.assertEqual(me.status_code, 200)

    def test_same_account_as_web_google_sign_in(self):
        existing = User.objects.create(email="new@example.com", google_sub="g-123", email_verified=True, password="!")
        with mock.patch(self.verify, return_value=GOOD):
            resp = _post(self.client)
        self.assertEqual(resp.json()["user"]["id"], str(existing.id))
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_token_is_401(self):
        with mock.patch(self.verify, side_effect=ValueError("bad")):
            self.assertEqual(_post(self.client).status_code, 401)

    def test_missing_token_is_400(self):
        self.assertEqual(_post(self.client, token="").status_code, 400)

    def test_unverified_email_refused(self):
        with mock.patch(self.verify, return_value={**GOOD, "email_verified": False}):
            self.assertEqual(_post(self.client).status_code, 403)

    @override_settings(GOOGLE_ID_TOKEN_AUDIENCES=[])
    def test_not_configured_is_503(self):
        self.assertEqual(_post(self.client).status_code, 503)

    @override_settings(SIGNUP_ENABLED=False)
    def test_signup_closed_blocks_new_accounts(self):
        with mock.patch(self.verify, return_value=GOOD):
            self.assertEqual(_post(self.client).status_code, 403)

    @override_settings(SIGNUP_ENABLED=False)
    def test_signup_closed_still_lets_existing_accounts_in(self):
        User.objects.create(email="new@example.com", google_sub="g-123", email_verified=True, password="!")
        with mock.patch(self.verify, return_value=GOOD):
            self.assertEqual(_post(self.client).status_code, 200)
