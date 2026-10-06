"""Smart, key-free brief engine.

Produces a genuinely useful daily brief using heuristics only — no external
LLM, no API key, no cost. It's the default engine; if an ANTHROPIC_API_KEY is
configured, `llm.generate_brief` uses Claude instead and falls back to this.

What it figures out on its own:
  * a time-of-day greeting + a natural-language headline
  * schedule shape: first/last meeting, back-to-back runs, overlaps/conflicts
  * the longest free block (focus time)
  * which emails actually need a reply, prioritized by intent keywords
  * concrete, actionable insights (prep before 1:1s, protect focus time, …)
"""

from __future__ import annotations

import re
import zoneinfo
from datetime import datetime, timedelta

from assistant.dto import BriefItem, CalendarEvent, InboxMessage

# Words that signal an email genuinely wants a response / action.
_HIGH_SIGNALS = (
    "urgent", "asap", "eod", "today", "sign-off", "sign off", "approve", "approval",
    "blocked", "blocker", "review", "deadline", "action required", "action needed",
    "overdue", "reminder", "contract", "invoice", "payment", "confirm", "response needed",
    "please reply", "waiting on you", "final",
)
# Senders/subjects that are almost never worth a personal reply.
_LOW_SIGNALS = (
    "newsletter", "no-reply", "noreply", "notifications", "digest", "weekly",
    "unsubscribe", "promo", "sale", "webinar", "automated",
)


def _tz(name: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(name)
    except Exception:
        return zoneinfo.ZoneInfo("UTC")


def _clean_sender(raw: str) -> str:
    """"Priya (Client) <priya@acme.co>" -> "Priya (Client)"."""
    name = raw.split("<", 1)[0].strip().strip('"')
    return name or raw


def _classify(msg: InboxMessage) -> tuple[str, str]:
    """Return (priority, reason) for an inbox message."""
    text = f"{msg.subject} {msg.snippet}".lower()
    sender = msg.sender.lower()

    if any(s in sender or s in text for s in _LOW_SIGNALS):
        return "low", "looks automated / newsletter"
    for signal in _HIGH_SIGNALS:
        if signal in text:
            return "high", f"mentions “{signal}”"
    if "?" in msg.subject:
        return "normal", "asks a question"
    return "normal", "awaiting your reply"


def _greeting(now: datetime) -> str:
    h = now.hour
    if h < 12:
        return "Good morning"
    if h < 17:
        return "Good afternoon"
    return "Good evening"


def _fmt(dt: datetime, tz: zoneinfo.ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%H:%M")


def _analyze_schedule(events: list[CalendarEvent], tz: zoneinfo.ZoneInfo) -> dict:
    timed = sorted((e for e in events if not e.is_all_day), key=lambda e: e.start)
    all_day = [e for e in events if e.is_all_day]

    conflicts: list[tuple[CalendarEvent, CalendarEvent]] = []
    back_to_back: list[tuple[CalendarEvent, CalendarEvent]] = []
    longest_gap = timedelta(0)
    gap_after: CalendarEvent | None = None

    for prev, nxt in zip(timed, timed[1:]):
        prev_end = prev.end or (prev.start + timedelta(minutes=30))
        if nxt.start < prev_end:
            conflicts.append((prev, nxt))
        else:
            gap = nxt.start - prev_end
            if gap <= timedelta(minutes=10):
                back_to_back.append((prev, nxt))
            if gap > longest_gap:
                longest_gap, gap_after = gap, prev

    return {
        "timed": timed,
        "all_day": all_day,
        "conflicts": conflicts,
        "back_to_back": back_to_back,
        "longest_gap": longest_gap,
        "gap_after": gap_after,
        "first": timed[0] if timed else None,
        "last": timed[-1] if timed else None,
        "big_meetings": [e for e in timed if len(e.attendees) >= 3],
    }


def generate(
    events: list[CalendarEvent], messages: list[InboxMessage], timezone_name: str
) -> tuple[str, list[BriefItem], str]:
    """Return (headline, items, body_markdown) — the same contract as the LLM path."""
    tz = _tz(timezone_name)
    now = datetime.now(tz)
    sched = _analyze_schedule(events, tz)

    # Classify emails.
    replies: list[tuple[InboxMessage, str, str]] = []  # (msg, priority, reason)
    for m in messages:
        pr, reason = _classify(m)
        if pr != "low":
            replies.append((m, pr, reason))
    replies.sort(key=lambda r: 0 if r[1] == "high" else 1)
    high_replies = [r for r in replies if r[1] == "high"]

    # ---- Items (prioritized, structured) ----------------------------------
    items: list[BriefItem] = []
    for m, pr, reason in high_replies:
        items.append(BriefItem(kind="reply", title=f"Reply: {m.subject}",
                               detail=f"{_clean_sender(m.sender)} — {reason}", priority="high"))
    if sched["conflicts"]:
        a, b = sched["conflicts"][0]
        items.append(BriefItem(kind="insight", title="⚠️ Schedule conflict",
                               detail=f"“{a.summary}” overlaps “{b.summary}” — resolve this first.",
                               priority="high"))
    for e in sched["timed"][:6]:
        who = f"{len(e.attendees)} people" if e.attendees else "solo / focus"
        items.append(BriefItem(kind="event", title=f"{_fmt(e.start, tz)} — {e.summary}",
                               detail=(e.location or who), priority="normal"))
    for m, pr, reason in replies:
        if pr != "high":
            items.append(BriefItem(kind="reply", title=f"Reply: {m.subject}",
                                   detail=f"{_clean_sender(m.sender)} — {reason}", priority="normal"))

    # ---- Headline (natural language) --------------------------------------
    n_ev, n_hi = len(sched["timed"]), len(high_replies)
    bits: list[str] = []
    if n_ev == 0:
        bits.append("No meetings today — a clear runway")
    else:
        first = sched["first"]
        shape = "packed" if len(sched["back_to_back"]) >= 2 else "manageable"
        bits.append(f"{n_ev} meeting{'s' if n_ev != 1 else ''} ({shape}), starting {_fmt(first.start, tz)}")
    if n_hi:
        bits.append(f"{n_hi} email{'s' if n_hi != 1 else ''} need a reply")
    if sched["conflicts"]:
        bits.append("and a calendar clash to fix")
    headline = f"{_greeting(now)} — " + ", ".join(bits) + "."

    # ---- Body markdown -----------------------------------------------------
    L: list[str] = ["## Schedule"]
    if sched["all_day"]:
        for e in sched["all_day"]:
            L.append(f"- **All day** — {e.summary}")
    if sched["timed"]:
        for e in sched["timed"]:
            end = f"–{_fmt(e.end, tz)}" if e.end else ""
            tags = []
            if len(e.attendees) >= 3:
                tags.append(f"{len(e.attendees)} attendees")
            if e.location:
                tags.append(e.location)
            if e.hangout_link:
                tags.append("video call")
            suffix = f" _({', '.join(tags)})_" if tags else ""
            L.append(f"- **{_fmt(e.start, tz)}{end}** — {e.summary}{suffix}")
    elif not sched["all_day"]:
        L.append("- Nothing scheduled — protect this time for deep work. 🎯")

    L += ["", "## Needs a Reply"]
    if replies:
        for m, pr, reason in replies:
            flag = "🔴 " if pr == "high" else ""
            L.append(f"- {flag}**{m.subject}** — {_clean_sender(m.sender)} ({reason})")
    else:
        L.append("- Inbox is clear. ✅")

    # ---- Insights ----------------------------------------------------------
    insights = _insights(sched, high_replies, tz)
    if insights:
        L += ["", "## Insights"]
        L += [f"- {i}" for i in insights]

    return headline, items, "\n".join(L)


def _insights(sched: dict, high_replies: list, tz: zoneinfo.ZoneInfo) -> list[str]:
    out: list[str] = []
    if sched["conflicts"]:
        out.append("You have overlapping meetings — decline or reschedule one.")
    if len(sched["back_to_back"]) >= 2:
        out.append("Several back-to-back meetings — grab water and a 5-min reset between them.")
    if sched["longest_gap"] >= timedelta(minutes=90) and sched["gap_after"]:
        mins = int(sched["longest_gap"].total_seconds() // 60)
        after = _fmt(sched["gap_after"].end or sched["gap_after"].start, tz)
        out.append(f"Longest free block is ~{mins} min after {after} — ideal for focused work.")
    for e in sched["timed"]:
        if re.search(r"\b1[:\- ]?1\b|one[- ]?on[- ]?one", e.summary, re.I):
            out.append(f"Block 10 min before your 1:1 ({_fmt(e.start, tz)}) to prep talking points.")
            break
    if high_replies:
        out.append(f"Clear the {len(high_replies)} high-priority email(s) first — they're time-sensitive.")
    return out
