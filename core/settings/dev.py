"""Development settings — friendly defaults for local work.

Selected by default (see ``manage.py``). Optimised for fast iteration, not
security: never run this in production.
"""

from __future__ import annotations

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

# Convenience: let the app run end-to-end without Redis/Celery by executing
# background tasks synchronously. Flip to False once a worker is running.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)

# Print emails to the console instead of sending them.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

INTERNAL_IPS = ["127.0.0.1"]

# Allow http OAuth redirects locally (Google permits localhost).
import os  # noqa: E402

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
