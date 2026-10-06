"""Celery tasks — the recurring engine.

* ``send_due_briefs``   fires every minute; delivers each user's brief when
                        their local clock reaches their chosen ``brief_time``.
* ``poll_calendars``    discovers newly-added events and schedules reminders.
* ``dispatch_reminders``sends reminders whose time has come.
* ``deliver_brief``     builds + emails one account's brief (also called on demand).
"""

from __future__ import annotations

import logging
import zoneinfo
from datetime import datetime

from celery import shared_task
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from assistant.models import Account
from assistant.services import briefing, notifier, reminders

logger = logging.getLogger(__name__)


def _local_hhmm(tz_name: str) -> str:
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
    return datetime.now(tz).strftime("%H:%M")


@shared_task(name="assistant.tasks.deliver_brief")
def deliver_brief(account_id: int) -> dict:
    """Build and email the daily brief for one account."""
    account = Account.objects.select_related("user").get(pk=account_id)
    brief_obj, generated = briefing.build_brief(account)

    html = render_to_string(
        "assistant/email/brief.html",
        {"account": account, "brief": brief_obj, "items": generated.items, "APP_NAME": "DayBrief AI"},
    )
    text = f"{brief_obj.headline}\n\n{brief_obj.body_markdown}"
    to = account.google_email or account.user.email
    result = notifier.notify(to_email=to, subject=f"☀️ Your DayBrief — {brief_obj.for_date}", text=text, html=html)

    brief_obj.delivered = any(result.values())
    brief_obj.save(update_fields=["delivered", "updated_at"])
    return {"account": account_id, "delivered": brief_obj.delivered, "channels": result}


@shared_task(name="assistant.tasks.send_due_briefs")
def send_due_briefs() -> int:
    """Deliver briefs for every account whose local time matches its brief_time."""
    sent = 0
    accounts = Account.objects.filter(briefings_enabled=True).select_related("user")
    for account in accounts:
        if _local_hhmm(account.timezone) == account.brief_time:
            deliver_brief.delay(account.id)
            sent += 1
    if sent:
        logger.info("Queued %d morning brief(s)", sent)
    return sent


@shared_task(name="assistant.tasks.poll_calendars")
def poll_calendars() -> int:
    """Poll connected calendars and schedule reminders for new events."""
    total_new = 0
    accounts = Account.objects.filter(reminders_enabled=True).exclude(_refresh_token="")
    for account in accounts:
        try:
            from assistant.services import calendar_client

            events = calendar_client.list_events(
                account.refresh_token, lookahead_hours=max(settings.BRIEF_LOOKAHEAD_HOURS, 48)
            )
            total_new += reminders.register_new_events(account, events)
        except Exception:  # pragma: no cover - network
            logger.exception("Calendar poll failed for %s", account)
    if total_new:
        logger.info("Discovered %d new event(s) across all accounts", total_new)
    return total_new


@shared_task(name="assistant.tasks.dispatch_reminders")
def dispatch_reminders() -> int:
    """Fire any reminders that are now due."""
    return reminders.dispatch_due(now=timezone.now())
