"""Model + signal + encryption tests."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase

from assistant.models import Account


class AccountModelTests(TestCase):
    def test_account_auto_created_for_new_user(self):
        user = User.objects.create_user("alice", "alice@example.com", "pw")
        self.assertTrue(hasattr(user, "account"))
        self.assertIsInstance(user.account, Account)

    def test_refresh_token_encryption_roundtrip(self):
        user = User.objects.create_user("bob", "bob@example.com", "pw")
        account = user.account
        self.assertFalse(account.is_connected)

        account.refresh_token = "super-secret-refresh-token"
        account.save()
        account.refresh_from_db()

        # Decrypts back to the original value…
        self.assertTrue(account.is_connected)
        self.assertEqual(account.refresh_token, "super-secret-refresh-token")
        # …but is NOT stored in plaintext.
        self.assertNotIn("super-secret-refresh-token", account._refresh_token)
