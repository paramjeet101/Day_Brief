"""Celery application + the recurring beat schedule.

Three periodic jobs power the "Chief of Staff" behaviour:

* ``send_due_briefs``       — every minute, delivers each user's morning brief
                              when their local clock hits their chosen time.
* ``poll_calendars``        — every few minutes, discovers newly-added events
                              and schedules reminders for them.
* ``dispatch_reminders``    — every minute, fires reminders whose time has come.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.dev")

app = Celery("daybrief")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "send-due-briefs": {
        "task": "assistant.tasks.send_due_briefs",
        "schedule": crontab(minute="*"),  # every minute; task checks per-user time
    },
    "poll-calendars": {
        "task": "assistant.tasks.poll_calendars",
        "schedule": 300.0,  # seconds; overridden by CALENDAR_POLL_SECONDS if desired
    },
    "dispatch-reminders": {
        "task": "assistant.tasks.dispatch_reminders",
        "schedule": crontab(minute="*"),
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover
    print(f"Request: {self.request!r}")
