"""Lightweight internal data-transfer objects.

These represent Google domain objects and LLM output *in memory*. They are
deliberately plain dataclasses (not ORM models) — we only persist what's worth
keeping (briefs, reminders), and pass these around between service functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class CalendarEvent:
    id: str
    summary: str
    start: datetime
    end: datetime | None = None
    location: str | None = None
    attendees: list[str] = field(default_factory=list)
    is_all_day: bool = False
    hangout_link: str | None = None
    organizer: str | None = None


@dataclass(slots=True)
class InboxMessage:
    id: str
    thread_id: str
    sender: str
    subject: str
    snippet: str
    received_at: datetime
    is_unread: bool = True


@dataclass(slots=True)
class BriefItem:
    kind: str  # "event" | "reply" | "insight"
    title: str
    detail: str | None = None
    priority: str = "normal"  # low | normal | high


@dataclass(slots=True)
class GeneratedBrief:
    headline: str
    items: list[BriefItem]
    body_markdown: str
    events: list[CalendarEvent]
    replies: list[InboxMessage]
