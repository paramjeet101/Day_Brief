"""URL routes for the assistant app (pages + JSON API)."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from assistant import api, views

router = DefaultRouter()
router.register("briefs", api.BriefViewSet, basename="brief")
router.register("reminders", api.ReminderViewSet, basename="reminder")
router.register("events", api.EventViewSet, basename="event")

urlpatterns = [
    # Pages
    path("", views.landing, name="landing"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("briefs/<int:brief_id>/", views.brief_detail, name="brief_detail"),
    path("reminders/", views.reminders_list, name="reminders"),
    path("settings/", views.update_settings, name="update_settings"),
    path("generate/", views.generate_now, name="generate_now"),
    # Calendar (manual events)
    path("events/add/", views.add_event, name="add_event"),
    path("events/<int:event_id>/delete/", views.delete_event, name="delete_event"),
    # Team (admin, role-based)
    path("team/", views.team, name="team"),
    path("team/<int:account_id>/role/", views.set_role, name="set_role"),
    # Auth — email + password
    path("signup/", views.signup, name="signup"),
    path("login/", views.signin, name="signin"),
    # Auth / Google OAuth + demo
    path("demo/", views.demo_login, name="demo_login"),
    path("auth/start/", views.auth_start, name="auth_start"),
    path("auth/callback/", views.auth_callback, name="auth_callback"),
    path("auth/signout/", views.sign_out, name="sign_out"),
    # JSON API
    path("api/", include((router.urls, "api"), namespace="api")),
    path("api/health/", api.health, name="health"),
    path("api/brief/today/", api.today_brief, name="today_brief"),
]
