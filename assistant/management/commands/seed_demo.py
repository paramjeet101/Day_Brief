"""Seed a demo account and generate a sample brief.

    python manage.py seed_demo

Creates (or reuses) a `demo` user with a fully-populated brief built from the
bundled demo fixtures — so the dashboard looks alive without connecting Google.
Login for the demo user: username `demo`, password `demo12345`.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from assistant.models import Account
from assistant.services import briefing


class Command(BaseCommand):
    help = "Create a demo user and generate a sample brief."

    def handle(self, *args, **options) -> None:
        user, created = User.objects.get_or_create(
            username="demo", defaults={"email": "demo@daybrief.ai"}
        )
        # Make the demo user a superuser so you can log in via /admin/ and then
        # browse the whole app without configuring Google OAuth.
        user.is_staff = True
        user.is_superuser = True
        user.set_password("demo12345")
        user.save()
        if created:
            self.stdout.write(self.style.SUCCESS("Created demo superuser (demo / demo12345)."))

        account = user.account  # auto-created by signal
        account.google_email = "demo@daybrief.ai"
        account.timezone = "Asia/Kolkata"
        account.save()

        brief, _ = briefing.build_brief(account)
        self.stdout.write(
            self.style.SUCCESS(
                f"Generated demo brief for {brief.for_date}: "
                f"{brief.event_count} events, {brief.reply_count} replies."
            )
        )
        self.stdout.write("Visit http://localhost:8000/ and sign in as 'demo' via the admin, "
                          "or connect your own Google account.")
