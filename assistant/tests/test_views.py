"""View / page tests."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from assistant.models import Brief


class ViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("eve", "eve@example.com", "pw")

    def test_landing_ok_for_anonymous(self):
        self.assertEqual(self.client.get(reverse("landing")).status_code, 200)

    def test_demo_login_signs_in_without_google(self):
        response = self.client.get(reverse("demo_login"))
        self.assertRedirects(response, reverse("dashboard"))
        # Now authenticated → dashboard renders.
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_auth_start_falls_back_to_demo_when_google_unset(self):
        # GOOGLE_CLIENT_ID is empty in test settings → no dead-end error.
        response = self.client.get(reverse("auth_start"))
        self.assertRedirects(response, reverse("demo_login"), target_status_code=302)

    def test_dashboard_requires_login(self):
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_dashboard_renders_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calendar")  # user-facing dashboard content

    def test_generate_now_creates_brief_and_redirects(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("generate_now"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Brief.objects.filter(account=self.user.account).exists())

    def test_update_settings_persists(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("update_settings"),
            {"brief_time": "08:15", "timezone": "Asia/Kolkata", "briefings_enabled": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.user.account.refresh_from_db()
        self.assertEqual(self.user.account.brief_time, "08:15")
        self.assertEqual(self.user.account.timezone, "Asia/Kolkata")
