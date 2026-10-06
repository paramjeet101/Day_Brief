"""Gmail access — recent unread inbox messages that may need a reply. Read-only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from assistant.dto import InboxMessage
from assistant.services.google_auth import credentials_from_refresh_token


def _service(refresh_token: str):
    creds = credentials_from_refresh_token(refresh_token)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _parse_received(raw: str) -> datetime:
    try:
        dt = parsedate_to_datetime(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def list_reply_candidates(
    refresh_token: str, *, lookback_hours: int, max_messages: int
) -> list[InboxMessage]:
    """Return recent unread primary-inbox messages, newest first."""
    service = _service(refresh_token)
    after = int((datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp())
    query = f"in:inbox is:unread category:primary after:{after}"
    try:
        listing = (
            service.users().messages().list(userId="me", q=query, maxResults=max_messages).execute()
        )
        messages: list[InboxMessage] = []
        for meta in listing.get("messages", []):
            detail = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=meta["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = detail.get("payload", {}).get("headers", [])
            messages.append(
                InboxMessage(
                    id=detail["id"],
                    thread_id=detail.get("threadId", detail["id"]),
                    sender=_header(headers, "From") or "(unknown sender)",
                    subject=_header(headers, "Subject") or "(no subject)",
                    snippet=detail.get("snippet", ""),
                    received_at=_parse_received(_header(headers, "Date")),
                    is_unread="UNREAD" in detail.get("labelIds", []),
                )
            )
        return messages
    except HttpError as exc:  # pragma: no cover - network
        raise RuntimeError(f"Gmail fetch failed: {exc}") from exc
