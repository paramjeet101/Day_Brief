"""Production settings — hardened, secure defaults.

Activate with ``DJANGO_SETTINGS_MODULE=core.settings.prod``. Requires real
secrets to be present in the environment.
"""

import os

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Hashed, manifested static files for long-term immutable caching (needs a
# collectstatic run — the Dockerfile does this at build time).
STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedManifestStaticFilesStorage"  # noqa: F405

# Allowed hosts + CSRF. Works out of the box on Render (RENDER_EXTERNAL_HOSTNAME)
# and honours an explicit DJANGO_ALLOWED_HOSTS list too.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")
if not ALLOWED_HOSTS:  # last resort so a fresh deploy still boots
    ALLOWED_HOSTS = ["*"]
if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = [BASE_URL]  # noqa: F405

# Background jobs: run inline unless a real Celery broker/worker is provided.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)

# SMTP if configured, otherwise log to console (keeps keyless deploys crash-free).
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

# --- Security hardening ---
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Structured single-line logs for aggregators.
LOGGING["root"]["level"] = env("LOG_LEVEL", default="INFO")  # noqa: F405
