"""JSON API (Django REST Framework).

Read-only resources for briefs and reminders, plus a couple of action
endpoints. Everything is scoped to the authenticated user's account.
"""

from __future__ import annotations

from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from assistant.models import Brief, Event, Reminder
from assistant.services import briefing, local_events


# --------------------------------------------------------------------------- #
# Serializers
# --------------------------------------------------------------------------- #
class BriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brief
        fields = [
            "id", "for_date", "headline", "body_markdown", "items_json",
            "event_count", "reply_count", "delivered", "created_at",
        ]


class ReminderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reminder
        fields = [
            "id", "event_summary", "event_starts_at", "fire_at",
            "offset_minutes", "status", "created_at",
        ]


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ["id", "title", "start", "end", "location", "notes", "all_day", "source", "created_at"]
        read_only_fields = ["source", "created_at"]


# --------------------------------------------------------------------------- #
# ViewSets
# --------------------------------------------------------------------------- #
class _AccountScopedViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated]

    def _account(self):
        return self.request.user.account


class BriefViewSet(_AccountScopedViewSet):
    serializer_class = BriefSerializer

    def get_queryset(self):
        return Brief.objects.filter(account=self._account()).order_by("-created_at")


class ReminderViewSet(_AccountScopedViewSet):
    serializer_class = ReminderSerializer

    def get_queryset(self):
        return Reminder.objects.filter(account=self._account()).order_by("fire_at")


class EventViewSet(
    mixins.CreateModelMixin, mixins.DestroyModelMixin, _AccountScopedViewSet
):
    """Full CRUD for manual calendar events (create/list/retrieve/delete)."""

    serializer_class = EventSerializer

    def get_queryset(self):
        return Event.objects.filter(account=self._account()).order_by("start")

    def perform_create(self, serializer):
        event = serializer.save(account=self._account(), source=Event.Source.MANUAL)
        local_events.schedule_reminders(self._account(), event)


# --------------------------------------------------------------------------- #
# Function endpoints
# --------------------------------------------------------------------------- #
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    """Liveness/readiness probe (DB round-trip)."""
    from django.db import connection

    db_ok = True
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        db_ok = False
    status = "ok" if db_ok else "degraded"
    return Response(
        {"status": status, "app": "DayBrief AI", "checks": {"database": "ok" if db_ok else "error"}},
        status=200 if db_ok else 503,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def today_brief(request: Request) -> Response:
    """GET returns today's brief; POST regenerates it on demand."""
    account = request.user.account
    if request.method == "POST":
        brief, _ = briefing.build_brief(account)
    else:
        from django.utils import timezone

        brief = Brief.objects.filter(
            account=account, for_date=timezone.localdate().isoformat()
        ).first()
        if brief is None:
            brief, _ = briefing.build_brief(account)
    return Response(BriefSerializer(brief).data)
