"""Base Django settings shared across all environments.

Environment-specific overrides live in ``dev.py`` and ``prod.py``. Which one
loads is decided by ``DJANGO_SETTINGS_MODULE`` (see ``manage.py`` — it defaults
to ``core.settings.dev``).

All secrets and deployment knobs are read from the environment via
``django-environ`` so the same image runs anywhere.
"""

from __future__ import annotations

from pathlib import Path

import environ

# BASE_DIR points at the repo root (…/DayBrief_AI).
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Load a local .env if present (never committed). Ignored in prod containers
# where real environment variables are injected.
environ.Env.read_env(BASE_DIR / "core" / ".env")

# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

BASE_URL = env("BASE_URL", default="http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "django_celery_beat",
    "django_extensions",
    # Local
    "assistant",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",  # compress dynamic HTML/JSON responses
    "whitenoise.middleware.WhiteNoiseMiddleware",  # static files without a CDN
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Templates live centrally under core/templates (namespaced per app).
        "DIRS": [BASE_DIR / "core" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "assistant.context_processors.branding",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

# --------------------------------------------------------------------------- #
# Database — SQLite locally, DATABASE_URL (Postgres) in prod
# --------------------------------------------------------------------------- #
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'daybrief.db'}"),
}
# Persistent connections + health checks: avoids per-request connect overhead
# and transparently recycles dropped connections (Django 4.1+).
DATABASES["default"].setdefault("CONN_MAX_AGE", 60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# --------------------------------------------------------------------------- #
# Auth / passwords
# --------------------------------------------------------------------------- #
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "/login/"

# --------------------------------------------------------------------------- #
# I18N / TZ
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- #
# Static & media
# --------------------------------------------------------------------------- #
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "core" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Compress static assets but DON'T require a manifest here — that keeps dev,
    # tests, and any DEBUG=False run working without a prior collectstatic.
    # prod.py swaps in the hashed/manifest variant for cache-busting.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
# Hashed static filenames are immutable → cache them hard (1 year) in prod.
WHITENOISE_MAX_AGE = 31_536_000

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# Django REST Framework
# --------------------------------------------------------------------------- #
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        # Basic auth makes the API easy to call from curl / Postman locally.
        # In production this rides over HTTPS.
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# --------------------------------------------------------------------------- #
# Celery (background jobs + scheduling)
# --------------------------------------------------------------------------- #
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# When Redis/Celery aren't running (e.g. quick local demo), run tasks inline.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)

# --------------------------------------------------------------------------- #
# DayBrief application settings
# --------------------------------------------------------------------------- #
# Fernet key for encrypting OAuth tokens at rest (falls back to SECRET_KEY).
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default=SECRET_KEY)

GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET", default="")
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
]
GOOGLE_REDIRECT_URI = f"{BASE_URL.rstrip('/')}/auth/callback/"

# LLM provider: local (default, no key) | groq | gemini | openai | openrouter | ollama | anthropic
LLM_PROVIDER = env("LLM_PROVIDER", default="local")
LLM_API_KEY = env("LLM_API_KEY", default="")        # for groq/gemini/openai/openrouter
LLM_BASE_URL = env("LLM_BASE_URL", default="")       # override the provider's default endpoint
LLM_MODEL = env("LLM_MODEL", default="")             # override the provider's default model
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
LLM_MAX_TOKENS = env.int("LLM_MAX_TOKENS", default=1500)
LLM_TIMEOUT_SECONDS = env.float("LLM_TIMEOUT_SECONDS", default=30.0)

# Briefing behaviour
BRIEF_DEFAULT_TIME = env("BRIEF_DEFAULT_TIME", default="07:30")
BRIEF_LOOKAHEAD_HOURS = env.int("BRIEF_LOOKAHEAD_HOURS", default=18)
INBOX_LOOKBACK_HOURS = env.int("INBOX_LOOKBACK_HOURS", default=48)
MAX_INBOX_MESSAGES = env.int("MAX_INBOX_MESSAGES", default=40)

# Reminders (minutes before an event)
REMINDER_OFFSETS_MINUTES = env.list("REMINDER_OFFSETS_MINUTES", cast=int, default=[1440, 60, 10])
CALENDAR_POLL_SECONDS = env.int("CALENDAR_POLL_SECONDS", default=300)

# Notifications
NOTIFY_CHANNELS = env.list("NOTIFY_CHANNELS", default=["email"])
NOTIFY_WEBHOOK_URL = env("NOTIFY_WEBHOOK_URL", default="")

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="DayBrief AI <no-reply@daybrief.ai>")

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {"format": "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "datefmt": "%H:%M:%S"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "console"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "googleapiclient.discovery_cache": {"level": "ERROR"},
    },
}
