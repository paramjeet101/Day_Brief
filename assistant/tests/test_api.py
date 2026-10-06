"""JSON API tests (DRF)."""

from __future__ import annotations

from django.contrib.auth.models import User
from rest_framework.test import APITestCase


class APITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("frank", "frank@example.com", "pw12345")

    def test_health_is_public(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_briefs_requires_auth(self):
        self.assertIn(self.client.get("/api/briefs/").status_code, (401, 403))

    def test_briefs_list_when_authenticated(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/briefs/").status_code, 200)

    def test_today_brief_get_then_regenerate(self):
        self.client.force_authenticate(self.user)
        get = self.client.get("/api/brief/today/")
        self.assertEqual(get.status_code, 200)
        self.assertIn("headline", get.json())

        post = self.client.post("/api/brief/today/")
        self.assertEqual(post.status_code, 200)

    def test_reminders_list_when_authenticated(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/reminders/").status_code, 200)
