"""Database models.

We layer DayBrief data on top of Django's built-in ``User`` via a one-to-one
``Account`` profile that holds the (encrypted) Google refresh token and each
person's briefing preferences.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from assistant.security import decrypt, encrypt


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Account(TimeStamped):
    """A user's DayBrief profile + connected Google credentials."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="account")
    google_email = models.EmailField(blank=True)
    full_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    timezone = models.CharField(max_length=64, default="UTC")

    # Encrypted Google OAuth refresh token (see assistant.security).
    _refresh_token = models.TextField(blank=True, db_column="refresh_token_enc")

    # Preferences
    brief_time = models.CharField(max_length=5, default="07:30", help_text="Local HH:MM")
    briefings_enabled = models.BooleanField(default=True)
    reminders_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "accounts"

    def __str__(self) -> str:
        return self.google_email or self.user.username

    # --- Encrypted token helpers ------------------------------------------ #
    @property
    def refresh_token(self) -> str | None:
        return decrypt(self._refresh_token) if self._refresh_token else None

    @refresh_token.setter
    def refresh_token(self, value: str | None) -> None:
        self._refresh_token = encrypt(value) if value else ""

    @property
    def is_connected(self) -> bool:
        return bool(self._refresh_token)

    @property
    def is_admin(self) -> bool:
        """Admins (explicit role or Django superusers) can access team views."""
        return self.role == self.Role.ADMIN or self.user.is_superuser

    @property
    def display_name(self) -> str:
        return self.full_name or self.google_email or self.user.username


class SeenEvent(TimeStamped):
    """Calendar events already processed by the poller (dedupe key)."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="seen_events")
    event_id = models.CharField(max_length=1024)
    summary = models.CharField(max_length=1024, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "seen_events"
        constraints = [
            models.UniqueConstraint(fields=["account", "event_id"], name="uq_account_event"),
        ]
        indexes = [models.Index(fields=["account", "event_id"])]


class Reminder(TimeStamped):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        CANCELLED = "cancelled", "Cancelled"

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="reminders")
    event_id = models.CharField(max_length=1024)
    event_summary = models.CharField(max_length=1024)
    event_starts_at = models.DateTimeField()
    fire_at = models.DateTimeField(db_index=True)
    offset_minutes = models.IntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)

    class Meta:
        db_table = "reminders"
        ordering = ["fire_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "event_id", "offset_minutes"], name="uq_reminder_offset"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_summary} (T-{self.offset_minutes}m)"


class Brief(TimeStamped):
    """A generated daily brief, kept for history and re-delivery."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="briefs")
    for_date = models.CharField(max_length=10, db_index=True)  # YYYY-MM-DD
    headline = models.CharField(max_length=500)
    body_markdown = models.TextField()
    items_json = models.JSONField(default=list)
    event_count = models.IntegerField(default=0)
    reply_count = models.IntegerField(default=0)
    delivered = models.BooleanField(default=False)

    class Meta:
        db_table = "briefs"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["account", "for_date"], name="uq_account_date"),
        ]

    def __str__(self) -> str:
        return f"Brief {self.for_date} — {self.account}"

    @property
    def is_today(self) -> bool:
        return self.for_date == timezone.localdate().isoformat()


class Event(TimeStamped):
    """A calendar event the user adds manually inside the app.

    Lets DayBrief work as a real personal calendar without Google — added
    events show up on their date, feed the daily brief, and get reminders.
    """

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        GOOGLE = "google", "Google"

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="events")
    title = models.CharField(max_length=300)
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)
    all_day = models.BooleanField(default=False)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)

    class Meta:
        db_table = "events"
        ordering = ["start"]
        indexes = [models.Index(fields=["account", "start"])]

    def __str__(self) -> str:
        return f"{self.title} @ {self.start:%Y-%m-%d %H:%M}"

    @property
    def event_key(self) -> str:
        """Stable id used for reminder de-duplication."""
        return f"local-{self.pk}"
