"""Signal handlers."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from assistant.models import Account


@receiver(post_save, sender=User)
def ensure_account(sender, instance: User, created: bool, **kwargs) -> None:
    """Every Django user gets exactly one DayBrief Account profile."""
    if created:
        Account.objects.get_or_create(user=instance)
