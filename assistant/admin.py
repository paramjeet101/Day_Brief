"""Django admin registrations."""

from __future__ import annotations

from django.contrib import admin

from assistant.models import Account, Brief, Event, Reminder, SeenEvent


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("google_email", "timezone", "brief_time", "briefings_enabled", "reminders_enabled", "is_connected")
    search_fields = ("google_email", "user__username")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(boolean=True, description="Google connected")
    def is_connected(self, obj: Account) -> bool:
        return obj.is_connected


@admin.register(Brief)
class BriefAdmin(admin.ModelAdmin):
    list_display = ("for_date", "account", "headline", "event_count", "reply_count", "delivered")
    list_filter = ("delivered", "for_date")
    search_fields = ("account__google_email", "headline")
    date_hierarchy = "created_at"


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("event_summary", "account", "event_starts_at", "fire_at", "offset_minutes", "status")
    list_filter = ("status",)
    search_fields = ("event_summary", "account__google_email")


@admin.register(SeenEvent)
class SeenEventAdmin(admin.ModelAdmin):
    list_display = ("summary", "account", "starts_at")
    search_fields = ("summary", "account__google_email")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "account", "start", "end", "location", "all_day", "source")
    list_filter = ("source", "all_day")
    search_fields = ("title", "account__google_email")
    date_hierarchy = "start"
