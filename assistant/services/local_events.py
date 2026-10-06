"""Helpers for user-added (manual) calendar events.

Bridges the ``Event`` model to the in-memory ``CalendarEvent`` DTO the brief
engine consumes, and schedules reminders for newly added events.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from assistant.dto import CalendarEvent
from assistant.models import Account, Event
from assistant.services import reminders

logger = logging.getLogger(__name__)


def to_dto(event: Event) -> CalendarEvent:
    return CalendarEvent(
        id=event.event_key,
        summary=event.title,
        start=event.start,
        end=event.end,
        location=event.location or None,
        is_all_day=event.all_day,
    )


def upcoming(account: Account, *, within_hours: int | None = None) -> list[CalendarEvent]:
    """Manual events from now onward (optionally capped to a horizon)."""
    qs = account.events.filter(start__gte=timezone.now() - timedelta(hours=1)).order_by("start")
    if within_hours is not None:
        qs = qs.filter(start__lte=timezone.now() + timedelta(hours=within_hours))
    return [to_dto(e) for e in qs]


def schedule_reminders(account: Account, event: Event) -> int:
    """Schedule reminders for a freshly-added event. Returns count created."""
    if not account.reminders_enabled:
        return 0
    created = reminders.schedule_for_event(account, to_dto(event))
    return len(created)
