"""Service-layer tests: LLM fallback, reminders, briefing orchestration.

None of these touch the network — the LLM falls back to a local brief when no
API key is set, and accounts here are unconnected so the demo fixtures are used.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from assistant.dto import CalendarEvent
from assistant.models import Brief, Reminder, SeenEvent
from assistant.services import briefing, demo, llm, reminders


class LLMFallbackTests(TestCase):
    def test_fallback_brief_has_headline_items_and_sections(self):
        headline, items, body = llm.generate_brief(
            demo.sample_events(), demo.sample_messages(), "UTC"
        )
        self.assertTrue(headline)
        self.assertTrue(items)
        self.assertIn("Schedule", body)
        self.assertIn("Needs a Reply", body)


class ReminderServiceTests(TestCase):
    def setUp(self):
        self.account = User.objects.create_user("carol", "carol@example.com", "pw").account

    def _event(self, hours_ahead: int) -> CalendarEvent:
        return CalendarEvent(
            id=f"evt-{hours_ahead}",
            summary="Team Meeting",
            start=timezone.now() + timedelta(hours=hours_ahead),
        )

    def test_schedule_is_idempotent(self):
        event = self._event(48)
        created = reminders.schedule_for_event(self.account, event)
        self.assertTrue(created)
        # Second call creates no duplicates (unique constraint).
        self.assertEqual(reminders.schedule_for_event(self.account, event), [])

    def test_register_new_events_dedupes(self):
        event = self._event(48)
        self.assertEqual(reminders.register_new_events(self.account, [event]), 1)
        self.assertEqual(reminders.register_new_events(self.account, [event]), 0)
        self.assertEqual(SeenEvent.objects.filter(account=self.account).count(), 1)

    def test_dispatch_due_marks_sent(self):
        reminder = Reminder.objects.create(
            account=self.account,
            event_id="x",
            event_summary="Standup",
            event_starts_at=timezone.now() + timedelta(minutes=5),
            fire_at=timezone.now() - timedelta(minutes=1),
            offset_minutes=10,
        )
        self.assertEqual(reminders.dispatch_due(), 1)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, Reminder.Status.SENT)


class BriefingTests(TestCase):
    def test_build_brief_demo_mode_persists(self):
        account = User.objects.create_user("dave", "dave@example.com", "pw").account
        brief, generated = briefing.build_brief(account)
        self.assertEqual(Brief.objects.filter(account=account).count(), 1)
        self.assertGreater(brief.event_count, 0)
        self.assertTrue(generated.headline)
