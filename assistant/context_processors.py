"""Template context processors — inject branding into every page."""

from __future__ import annotations

from django.conf import settings


def branding(request) -> dict:
    return {
        "APP_NAME": "DayBrief AI",
        "APP_TAGLINE": "Your AI Chief of Staff",
        "ENVIRONMENT": getattr(settings, "ENVIRONMENT", "dev"),
        # Lets templates show "Connect Google" only when OAuth is actually set up.
        "GOOGLE_READY": bool(settings.GOOGLE_CLIENT_ID),
    }
