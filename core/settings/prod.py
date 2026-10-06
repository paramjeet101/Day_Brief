"""Production settings — hardened, secure defaults.

Activate with ``DJANGO_SETTINGS_MODULE=core.settings.prod``. Requires real
secrets to be present in the environment.
"""

import os

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Static files: WhiteNoise serves them straight from the app (no separate CDN
# needed). Hashed + compressed for long-term caching. `build.sh` runs
# collectstatic at deploy time to populate STATIC_ROOT + the manifest.
STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedManifestStaticFilesStorage"  # noqa: F405

# Accept any host (simple for a personal deploy). CSRF still needs the real
# origin(s) for form POSTs — we trust the Render host + any *.onrender.com.
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")
CSRF_TRUSTED_ORIGINS.append("https://*.onrender.com")
if BASE_URL not in CSRF_TRUSTED_ORIGINS:  # noqa: F405
    CSRF_TRUSTED_ORIGINS.append(BASE_URL)  # noqa: F405

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
