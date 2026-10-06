"""Brief generation orchestration.

Ties the pieces together: fetch the user's REAL calendar + inbox → synthesize a
brief → persist a Brief row → (optionally) schedule reminders.

Data policy: real data only. We never inject demo/sample/placeholder data into a
brief. When a source isn't connected or has nothing, the brief shows an empty
state ("No items for today.") instead of inventing anything.
"""

from __future__ import annotations

import dataclasses
import logging

from django.conf import settings
from django.utils import timezone

from assistant.dto import GeneratedBrief
from assistant.models import Account, Brief
from assistant.services import calendar_client, gmail_client, llm, local_events, reminders

logger = logging.getLogger(__name__)


def _gather(account: Account):
    """Return (events, messages) — the account's REAL data only.

    * Connected to Google → live Calendar + Gmail.
    * Otherwise → the account's own calendar entries (the Event model). There is
      no connected mailbox, so there are no email messages. No demo data is ever
      substituted for missing real data.
    """
    if account.is_connected:
        token = account.refresh_token
        events = calendar_client.list_events(token, lookahead_hours=settings.BRIEF_LOOKAHEAD_HOURS)
        messages = gmail_client.list_reply_candidates(
            token,
            lookback_hours=settings.INBOX_LOOKBACK_HOURS,
            max_messages=settings.MAX_INBOX_MESSAGES,
        )
        return events, messages

    manual = local_events.upcoming(account, within_hours=settings.BRIEF_LOOKAHEAD_HOURS)
    logger.info("Account %s: %d real calendar event(s), no connected mailbox.", account, len(manual))
    return manual, []


def build_brief(account: Account, *, persist: bool = True) -> tuple[Brief, GeneratedBrief]:
    """Generate today's brief for an account and (optionally) save it."""
    events, messages = _gather(account)

    headline, items, body = llm.generate_brief(events, messages, account.timezone)

    generated = GeneratedBrief(
        headline=headline, items=items, body_markdown=body, events=events, replies=messages
    )

    # Opportunistically schedule reminders for freshly discovered events.
    if account.is_connected and account.reminders_enabled:
        try:
            reminders.register_new_events(account, events)
        except Exception:  # never let reminder bookkeeping break the brief
            logger.exception("Failed to register reminders for %s", account)

    today = timezone.localdate().isoformat()
    brief_obj = Brief(
        account=account,
        for_date=today,
        headline=headline,
        body_markdown=body,
        items_json=[dataclasses.asdict(i) for i in items],
        event_count=len(events),
        reply_count=len(messages),
    )
    if persist:
        brief_obj, _ = Brief.objects.update_or_create(
            account=account,
            for_date=today,
            defaults={
                "headline": headline,
                "body_markdown": body,
                "items_json": brief_obj.items_json,
                "event_count": brief_obj.event_count,
                "reply_count": brief_obj.reply_count,
            },
        )
    return brief_obj, generated
