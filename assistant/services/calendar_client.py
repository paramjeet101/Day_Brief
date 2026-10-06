"""Google Calendar access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from assistant.dto import CalendarEvent
from assistant.services.google_auth import credentials_from_refresh_token


def _service(refresh_token: str):
    creds = credentials_from_refresh_token(refresh_token)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _parse_dt(node: dict) -> tuple[datetime, bool]:
    """Return (datetime, is_all_day). Google uses 'date' for all-day events."""
    if "dateTime" in node:
        return datetime.fromisoformat(node["dateTime"].replace("Z", "+00:00")), False
    return datetime.fromisoformat(node["date"]).replace(tzinfo=timezone.utc), True


def _to_event(raw: dict) -> CalendarEvent:
    start, all_day = _parse_dt(raw["start"])
    end = _parse_dt(raw["end"])[0] if raw.get("end") else None
    return CalendarEvent(
        id=raw["id"],
        summary=raw.get("summary", "(no title)"),
        start=start,
        end=end,
        location=raw.get("location"),
        attendees=[a.get("email", "") for a in raw.get("attendees", []) if a.get("email")],
        is_all_day=all_day,
        hangout_link=raw.get("hangoutLink"),
        organizer=(raw.get("organizer") or {}).get("email"),
    )


def list_events(
    refresh_token: str, *, lookahead_hours: int, calendar_id: str = "primary"
) -> list[CalendarEvent]:
    """List events from now until now + ``lookahead_hours``, ordered by start."""
    now = datetime.now(timezone.utc)
    try:
        resp = (
            _service(refresh_token)
            .events()
            .list(
                calendarId=calendar_id,
                timeMin=now.isoformat(),
                timeMax=(now + timedelta(hours=lookahead_hours)).isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            )
            .execute()
        )
    except HttpError as exc:  # pragma: no cover - network
        raise RuntimeError(f"Calendar list failed: {exc}") from exc
    return [_to_event(i) for i in resp.get("items", []) if i.get("status") != "cancelled"]
