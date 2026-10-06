"""Deterministic brief engine — REAL DATA ONLY.

Builds the daily brief strictly from the events and messages it is given. It
never invents, simulates, or substitutes placeholder data. When a section has
no real data it emits an explicit empty state ("No items for today.").

Output shape matches the product spec:
  * Summary line (counts derived only from real data)
  * Today's Schedule (only events that occur today; exact times/titles/locations)
  * Needs Your Attention (real emails with action signals; 🔴/🟡/🟢 priority)
  * Insights (1–3, strictly data-driven; omitted when none)
"""

from __future__ import annotations

import zoneinfo
from datetime import datetime, timedelta

from assistant.dto import BriefItem, CalendarEvent, InboxMessage

# Signals that an email genuinely needs a reply / action.
_HIGH_SIGNALS = (
    "urgent", "asap", "eod", "sign-off", "sign off", "approval required", "approve",
    "blocked", "blocker", "action required", "action needed", "deadline", "overdue",
    "response needed", "please reply", "waiting on you", "final notice",
)
_MEDIUM_SIGNALS = ("please review", "review", "follow up", "follow-up", "confirm", "reminder", "contract", "invoice")
_LOW_SIGNALS = (
    "newsletter", "no-reply", "noreply", "notifications", "digest", "weekly",
    "unsubscribe", "promo", "sale", "webinar", "automated",
)

_PRIORITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}


def _tz(name: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(name)
    except Exception:
        return zoneinfo.ZoneInfo("UTC")


def _ampm(dt: datetime, tz: zoneinfo.ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%I:%M %p").lstrip("0")


def _clean_sender(raw: str) -> str:
    return (raw.split("<", 1)[0].strip().strip('"')) or raw


def _greeting(hour: int) -> str:
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def _classify(msg: InboxMessage) -> tuple[str, str] | None:
    """Return (priority, reason) if the email needs a reply, else None."""
    text = f"{msg.subject} {msg.snippet}".lower()
    sender = msg.sender.lower()
    if any(s in sender or s in text for s in _LOW_SIGNALS):
        return None  # informational — not an action item
    for s in _HIGH_SIGNALS:
        if s in text:
            return "high", f"{s} mentioned"
    for s in _MEDIUM_SIGNALS:
        if s in text:
            return "medium", f"{s} requested"
    if "?" in msg.subject:
        return "medium", "question asked"
    return "medium", "awaiting your reply"


def generate(
    events: list[CalendarEvent], messages: list[InboxMessage], timezone_name: str
) -> tuple[str, list[BriefItem], str]:
    """Return (headline, items, body_markdown) from real data only."""
    tz = _tz(timezone_name)
    now = datetime.now(tz)
    today = now.date()

    # --- Today's events (only those that actually occur today) --------------
    todays = sorted(
        (e for e in events if e.start.astimezone(tz).date() == today),
        key=lambda e: e.start,
    )

    # --- Emails needing a reply (real emails only) -------------------------
    attention: list[tuple[InboxMessage, str, str]] = []
    for m in messages:
        verdict = _classify(m)
        if verdict:
            attention.append((m, verdict[0], verdict[1]))
    attention.sort(key=lambda r: 0 if r[1] == "high" else 1)

    # --- Structured items (for the dashboard panels) -----------------------
    items: list[BriefItem] = []
    for e in todays:
        when = _ampm(e.start, tz)
        if e.end:
            when += f" – {_ampm(e.end, tz)}"
        items.append(BriefItem(kind="event", title=f"{when} — {e.summary}", detail=e.location or None, priority="normal"))
    for m, pr, reason in attention:
        items.append(BriefItem(
            kind="reply",
            title=f'Reply: "{m.subject}"',
            detail=f"{_clean_sender(m.sender)} — {reason}",
            priority="high" if pr == "high" else "normal",
        ))

    insights = _insights(todays, attention, tz)
    for text in insights:
        items.append(BriefItem(kind="insight", title=text, detail=None, priority="low"))

    # --- Summary headline ---------------------------------------------------
    n_meet, n_reply = len(todays), len(attention)
    if n_meet == 0 and n_reply == 0:
        headline = f"{_greeting(now.hour)} — your schedule is clear today."
    else:
        parts = []
        if n_meet:
            parts.append(f"{n_meet} meeting{'s' if n_meet != 1 else ''} today")
        if n_reply:
            parts.append(f"{n_reply} email{'s' if n_reply != 1 else ''} requiring a reply")
        headline = f"{_greeting(now.hour)} — you have " + ", and ".join(
            [", ".join(parts[:-1]), parts[-1]] if len(parts) > 1 else parts
        ) + "."

    # --- Markdown body ------------------------------------------------------
    L = [f"## Summary", headline, "", "## Today's Schedule"]
    if todays:
        for e in todays:
            when = _ampm(e.start, tz) + (f" – {_ampm(e.end, tz)}" if e.end else "")
            loc = f" _(Location: {e.location})_" if e.location else ""
            L.append(f"- **{when}** — {e.summary}{loc}")
    else:
        L.append("No items for today.")

    L += ["", "## Needs Your Attention"]
    if attention:
        for m, pr, reason in attention:
            L.append(f'- {_PRIORITY_EMOJI[pr]} **Reply: "{m.subject}"** — {_clean_sender(m.sender)} ({reason})')
    else:
        L.append("No items for today.")

    if insights:
        L += ["", "## Insights"]
        L += [f"- {i}" for i in insights]

    return headline, items, "\n".join(L)


def _insights(todays, attention, tz) -> list[str]:
    """1–3 insights derived strictly from real data."""
    out: list[str] = []

    # Overlapping meetings.
    for prev, nxt in zip(todays, todays[1:]):
        prev_end = prev.end or (prev.start + timedelta(minutes=30))
        if nxt.start < prev_end:
            out.append(f"Your {_ampm(nxt.start, tz)} meeting overlaps with “{prev.summary}”.")
            break

    # Meetings before noon.
    before_noon = [e for e in todays if e.start.astimezone(tz).hour < 12]
    if len(before_noon) >= 2:
        out.append(f"You have {len(before_noon)} meetings before lunch.")

    # High-priority emails.
    highs = [a for a in attention if a[1] == "high"]
    if highs:
        out.append(f"{len(highs)} email{'s' if len(highs) != 1 else ''} need{'s' if len(highs) == 1 else ''} a response today.")

    return out[:3]
