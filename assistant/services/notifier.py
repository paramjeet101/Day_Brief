"""Notification delivery across configured channels (email, webhook).

Each channel is best-effort and isolated: a failure in one never blocks the
others. Channels are chosen via ``settings.NOTIFY_CHANNELS``.
"""

from __future__ import annotations

import logging

import httpx
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def _send_email(*, to: str, subject: str, text: str, html: str | None = None) -> bool:
    try:
        msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to])
        if html:
            msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:  # pragma: no cover - transport
        logger.exception("Email delivery failed to %s", to)
        return False


def _send_webhook(*, subject: str, text: str) -> bool:
    url = settings.NOTIFY_WEBHOOK_URL
    if not url:
        return False
    try:
        # Slack/Discord/Teams all accept a JSON body with a text field.
        httpx.post(url, json={"text": f"*{subject}*\n{text}"}, timeout=10).raise_for_status()
        return True
    except Exception:  # pragma: no cover - transport
        logger.exception("Webhook delivery failed")
        return False


def notify(*, to_email: str, subject: str, text: str, html: str | None = None) -> dict[str, bool]:
    """Dispatch to every configured channel. Returns per-channel success map."""
    results: dict[str, bool] = {}
    channels = settings.NOTIFY_CHANNELS or ["email"]
    if "email" in channels and to_email:
        results["email"] = _send_email(to=to_email, subject=subject, text=text, html=html)
    if "webhook" in channels:
        results["webhook"] = _send_webhook(subject=subject, text=text)
    logger.info("Notification '%s' -> %s", subject, results)
    return results
