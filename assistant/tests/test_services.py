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
    def test_brief_has_summary_and_sections(self):
        headline, items, body = llm.generate_brief(
            demo.sample_events(), demo.sample_messages(), "UTC"
        )
        self.assertTrue(headline)
        self.assertIn("## Summary", body)
        self.assertIn("## Today's Schedule", body)
        self.assertIn("## Needs Your Attention", body)

    def test_empty_data_shows_empty_states_not_fake_data(self):
        headline, items, body = llm.generate_brief([], [], "UTC")
        self.assertIn("schedule is clear today", headline)
        self.assertIn("No items for today.", body)
        self.assertEqual(items, [])


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
    def test_build_brief_with_no_data_is_empty_not_fake(self):
        """A fresh account with no real data → empty brief, never demo data."""
        account = User.objects.create_user("dave", "dave@example.com", "pw").account
        brief, generated = briefing.build_brief(account)
        self.assertEqual(Brief.objects.filter(account=account).count(), 1)
        self.assertEqual(brief.event_count, 0)
        self.assertEqual(brief.reply_count, 0)
        self.assertIn("No items for today.", brief.body_markdown)

    def test_build_brief_uses_real_calendar_events(self):
        from assistant.models import Event

        account = User.objects.create_user("erin", "erin@example.com", "pw").account
        start = timezone.now() + timedelta(hours=2)
        Event.objects.create(account=account, title="Board Meeting", start=start, end=start + timedelta(hours=1))
        brief, generated = briefing.build_brief(account)
        self.assertGreaterEqual(brief.event_count, 1)
        # The real event flows into the brief's gathered data (not demo data).
        self.assertIn("Board Meeting", [e.summary for e in generated.events])
