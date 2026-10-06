"""Sample data so the product is fully demoable without a connected account.

Used by the dashboard and the "Generate now" action whenever an Account has no
Google credentials attached — the whole flow (fetch → LLM → brief → reminders)
runs end-to-end against realistic fixtures.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from assistant.dto import CalendarEvent, InboxMessage


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
