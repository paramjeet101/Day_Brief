"""Demo fixtures + seeding.

IMPORTANT: this is used ONLY to seed the explicit demo account (via
``demo_login``) with **real** calendar records so the demo isn't a blank page.
It is never used to fabricate data inside a real user's brief — briefs read the
account's real data only (see ``briefing._gather``).

``sample_events`` / ``sample_messages`` return in-memory DTOs used by unit tests
of the brief engine.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from assistant.dto import CalendarEvent, InboxMessage


def seed_calendar(account) -> int:
    """Create a few *real* calendar events (today) for a demo account if it has
    none. Returns the number created. These become genuine Event rows that the
    brief reads like any other real data — nothing is faked at render time."""
    from assistant.models import Event
    from assistant.services import local_events

    if account.events.exists():
        return 0

    import zoneinfo

    try:
        tz = zoneinfo.ZoneInfo(account.timezone)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")

    today = datetime.now(tz).date()

    def at(hour: int, minute: int = 0) -> datetime:
        return datetime.combine(today, time(hour, minute), tzinfo=tz)

    specs = [
        ("Team Standup", at(10, 0), at(10, 30), "Google Meet"),
        ("1:1 with Manager", at(14, 0), at(14, 30), "Room 4B"),
        ("Q3 Roadmap Review", at(16, 0), at(17, 0), "Boardroom"),
    ]
    created = 0
    for title, start, end, location in specs:
        event = Event.objects.create(
            account=account, title=title, start=start, end=end, location=location
        )
        local_events.schedule_reminders(account, event)
        created += 1
    return created


def sample_events() -> list[CalendarEvent]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [
        CalendarEvent(
            id="demo-standup",
            summary="Engineering Standup",
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=1, minutes=15),
            attendees=["alex@team.dev", "sam@team.dev"],
            hangout_link="https://meet.google.com/demo",
        ),
        CalendarEvent(
            id="demo-1on1",
            summary="1:1 with Manager",
            start=now + timedelta(hours=3),
            end=now + timedelta(hours=3, minutes=30),
            location="Room 4B",
            attendees=["manager@team.dev"],
        ),
        CalendarEvent(
            id="demo-review",
            summary="Q3 Roadmap Review",
            start=now + timedelta(hours=5),
            end=now + timedelta(hours=6),
            location="Boardroom",
            attendees=["vp@team.dev", "pm@team.dev", "design@team.dev"],
        ),
    ]


def sample_messages() -> list[InboxMessage]:
    now = datetime.now(timezone.utc)
    return [
        InboxMessage(
            id="demo-m1",
            thread_id="t1",
            sender="Priya (Client) <priya@acme.co>",
            subject="Re: Contract renewal — need your sign-off",
            snippet="Hi, could you confirm the updated terms by EOD so legal can proceed?",
            received_at=now - timedelta(hours=2),
        ),
        InboxMessage(
            id="demo-m2",
            thread_id="t2",
            sender="Jordan <jordan@team.dev>",
            subject="Deploy blocked — can you review PR #482?",
            snippet="The release is waiting on your review. Should be quick — 40 lines.",
            received_at=now - timedelta(hours=5),
        ),
        InboxMessage(
            id="demo-m3",
            thread_id="t3",
            sender="Newsletter <news@devweekly.io>",
            subject="This week in Python",
            snippet="Django 5.1 highlights, async ORM tips, and more.",
            received_at=now - timedelta(hours=9),
        ),
    ]
