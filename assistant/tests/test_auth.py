"""Sign up / sign in and role-based access tests."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from assistant.models import Account


class SignupSigninTests(TestCase):
    def test_signup_creates_user_and_logs_in(self):
        resp = self.client.post(
            reverse("signup"),
            {"full_name": "Jane Doe", "email": "jane@example.com",
             "password": "secretpw123", "confirm": "secretpw123"},
        )
        self.assertRedirects(resp, reverse("dashboard"))
        user = User.objects.get(username="jane@example.com")
        self.assertEqual(user.account.full_name, "Jane Doe")
        # First user becomes admin.
        self.assertTrue(user.account.is_admin)

    def test_signup_rejects_short_password(self):
        resp = self.client.post(
            reverse("signup"),
            {"email": "x@example.com", "password": "short", "confirm": "short"},
        )
        self.assertEqual(resp.status_code, 200)  # re-rendered with error
        self.assertFalse(User.objects.filter(username="x@example.com").exists())

    def test_signup_rejects_mismatched_passwords(self):
        resp = self.client.post(
            reverse("signup"),
            {"email": "y@example.com", "password": "password1", "confirm": "password2"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="y@example.com").exists())

    def test_second_user_is_member(self):
        User.objects.create_user("first@example.com", "first@example.com", "pw")
        self.client.post(
            reverse("signup"),
            {"email": "second@example.com", "password": "secretpw123", "confirm": "secretpw123"},
        )
        second = User.objects.get(username="second@example.com")
        self.assertFalse(second.account.is_admin)
        self.assertEqual(second.account.role, Account.Role.MEMBER)

    def test_signin_with_valid_credentials(self):
        User.objects.create_user("bob@example.com", "bob@example.com", "mypassword1")
        resp = self.client.post(
            reverse("signin"), {"email": "bob@example.com", "password": "mypassword1"}
        )
        self.assertRedirects(resp, reverse("dashboard"))

    def test_signin_with_wrong_password(self):
        User.objects.create_user("carl@example.com", "carl@example.com", "rightpass1")
        resp = self.client.post(
            reverse("signin"), {"email": "carl@example.com", "password": "wrongpass"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


class RoleAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin@x.com", "admin@x.com", "pw")
        self.admin.account.role = Account.Role.ADMIN
        self.admin.account.save()
        self.member = User.objects.create_user("member@x.com", "member@x.com", "pw")

    def test_member_cannot_access_team(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("team"))
        self.assertRedirects(resp, reverse("dashboard"))

    def test_admin_can_access_team(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("team"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "member@x.com")

    def test_admin_can_promote_member(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("set_role", args=[self.member.account.id]), {"role": "admin"}
        )
        self.assertRedirects(resp, reverse("team"))
        self.member.account.refresh_from_db()
        self.assertEqual(self.member.account.role, Account.Role.ADMIN)

    def test_cannot_demote_last_admin(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("set_role", args=[self.admin.account.id]), {"role": "member"}
        )
        self.assertRedirects(resp, reverse("team"))
        self.admin.account.refresh_from_db()
        self.assertEqual(self.admin.account.role, Account.Role.ADMIN)  # unchanged
