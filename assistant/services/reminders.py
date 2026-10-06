"""Reminder scheduling and dispatch.

When new calendar events are discovered we pre-compute reminder rows at each
configured offset (e.g. 1 day / 1 hour / 10 min before). A lightweight
periodic task then fires any reminder whose time has arrived.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.utils import timezone as dj_tz

from assistant.dto import CalendarEvent
from assistant.models import Account, Reminder, SeenEvent
from assistant.services import notifier

logger = logging.getLogger(__name__)


def schedule_for_event(account: Account, event: CalendarEvent) -> list[Reminder]:
    """Create reminder rows for one event at each configured offset.

    Idempotent: a unique constraint on (account, event_id, offset) means calling
    this twice for the same event is a no-op.
    """
    now = datetime.now(timezone.utc)
    created: list[Reminder] = []
    for offset in settings.REMINDER_OFFSETS_MINUTES:
        fire_at = event.start - timedelta(minutes=offset)
        if fire_at <= now:
            continue  # don't schedule reminders in the past
        reminder, was_created = Reminder.objects.get_or_create(
            account=account,
            event_id=event.id,
            offset_minutes=offset,
            defaults={
                "event_summary": event.summary,
                "event_starts_at": event.start,
                "fire_at": fire_at,
                "status": Reminder.Status.PENDING,
            },
        )
        if was_created:
            created.append(reminder)
    if created:
        logger.info("Scheduled %d reminder(s) for '%s'", len(created), event.summary)
    return created


def register_new_events(account: Account, events: list[CalendarEvent]) -> int:
    """Detect events we haven't seen and schedule reminders. Returns new count."""
    if not account.reminders_enabled:
        return 0
    known = set(
        SeenEvent.objects.filter(account=account, event_id__in=[e.id for e in events]).values_list(
            "event_id", flat=True
        )
    )
    new_count = 0
    for event in events:
        if event.id in known:
            continue
        SeenEvent.objects.create(
            account=account, event_id=event.id, summary=event.summary, starts_at=event.start
        )
        schedule_for_event(account, event)
        new_count += 1
    return new_count


def dispatch_due(now: datetime | None = None) -> int:
    """Send any pending reminders whose fire time has passed. Returns sent count."""
    now = now or dj_tz.now()
    due = (
        Reminder.objects.select_related("account", "account__user")
        .filter(status=Reminder.Status.PENDING, fire_at__lte=now)
        .order_by("fire_at")[:200]
    )
    sent = 0
    for reminder in due:
        account = reminder.account
        minutes = _human_delta(reminder.event_starts_at - now)
        subject = f"⏰ Reminder: {reminder.event_summary} {minutes}"
        text = (
            f"{reminder.event_summary}\n"
            f"Starts: {reminder.event_starts_at:%a %d %b, %H:%M} ({account.timezone})"
        )
        notifier.notify(to_email=account.google_email or account.user.email, subject=subject, text=text)
        reminder.status = Reminder.Status.SENT
        reminder.save(update_fields=["status", "updated_at"])
        sent += 1
    if sent:
        logger.info("Dispatched %d reminder(s)", sent)
    return sent


def _human_delta(delta: timedelta) -> str:
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes <= 0:
        return "now"
    if total_minutes < 60:
        return f"in {total_minutes} min"
    if total_minutes < 1440:
        return f"in {total_minutes // 60}h"
    return f"in {total_minutes // 1440}d"
