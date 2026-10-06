"""Ensure the Celery app is loaded when Django starts so shared_task works."""

from core.celery import app as celery_app

__all__ = ["celery_app"]
