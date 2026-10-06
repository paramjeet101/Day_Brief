"""Manual calendar event tests — view, brief integration, and API CRUD."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from assistant.models import Event, Reminder
from assistant.services import briefing


class AddEventViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("gina", "gina@example.com", "pw")
        self.client.force_login(self.user)

    def test_add_event_creates_and_schedules_reminders(self):
        start = (timezone.localtime() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("add_event"),
            {"title": "Dentist", "start": start, "location": "Clinic"},
        )
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(account=self.user.account, title="Dentist")
        self.assertEqual(event.location, "Clinic")
        # Reminders scheduled for the future event.
        self.assertTrue(Reminder.objects.filter(account=self.user.account, event_id=event.event_key).exists())

    def test_add_event_shows_on_dashboard(self):
        start = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(reverse("add_event"), {"title": "Standup Demo", "start": start})
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Standup Demo", html)

    def test_brief_uses_manual_events(self):
        start = (timezone.now() + timedelta(hours=3))
        Event.objects.create(account=self.user.account, title="Investor Call", start=start)
        _, generated = briefing.build_brief(self.user.account)
        titles = " ".join(e.summary for e in generated.events)
        self.assertIn("Investor Call", titles)


class EventAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("hank", "hank@example.com", "pw12345")
        self.client.force_authenticate(self.user)

    def test_create_and_list_event(self):
        start = (timezone.now() + timedelta(days=1)).isoformat()
        create = self.client.post("/api/events/", {"title": "Review", "start": start}, format="json")
        self.assertEqual(create.status_code, 201)
        listing = self.client.get("/api/events/")
        self.assertEqual(listing.status_code, 200)
        titles = [e["title"] for e in listing.json()["results"]]
        self.assertIn("Review", titles)

    def test_delete_event(self):
        event = Event.objects.create(
            account=self.user.account, title="Temp", start=timezone.now() + timedelta(days=1)
        )
        response = self.client.delete(f"/api/events/{event.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Event.objects.filter(id=event.id).exists())
