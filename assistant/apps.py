from django.apps import AppConfig


class AssistantConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "assistant"
    verbose_name = "DayBrief Assistant"

    def ready(self) -> None:
        # Import signal handlers (auto-create Account for each new User).
        from assistant import signals  # noqa: F401
