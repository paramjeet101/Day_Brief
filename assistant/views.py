"""HTTP views — server-rendered pages + a few POST actions.

Authentication *is* the Google connect flow: signing in with Google both logs
the user in and stores their (encrypted) refresh token, so there's one clean
path to a fully-connected account.
"""

from __future__ import annotations

import functools
import logging
import secrets
import zoneinfo
from collections import OrderedDict
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages as flash
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from assistant.models import Account, Brief, Event, Reminder
from assistant.services import briefing, demo, google_auth, local_events

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Public
# --------------------------------------------------------------------------- #
def landing(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "assistant/landing.html", {"google_ready": bool(settings.GOOGLE_CLIENT_ID)})


# --------------------------------------------------------------------------- #
# Auth — email + password sign up / sign in
# --------------------------------------------------------------------------- #
def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        confirm = request.POST.get("confirm") or ""

        error = None
        if not email or "@" not in email:
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords don't match."
        elif User.objects.filter(username=email).exists():
            error = "An account with this email already exists. Try signing in."

        if error:
            flash.error(request, error)
            return render(request, "assistant/signup.html", {"email": email, "full_name": full_name})

        user = User.objects.create_user(username=email, email=email, password=password)
        # The very first user becomes the Admin; everyone else is a Member.
        account = user.account
        account.full_name = full_name
        account.google_email = email
        account.role = Account.Role.ADMIN if User.objects.count() == 1 else Account.Role.MEMBER
        if account.timezone == "UTC":
            account.timezone = settings.TIME_ZONE
        account.save()

        login(request, user)
        briefing.build_brief(account)  # land on a populated dashboard
        flash.success(request, f"Welcome aboard, {account.display_name}! 🎉")
        return redirect("dashboard")

    return render(request, "assistant/signup.html", {})


def signin(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=email, password=password)
        if user is None:
            flash.error(request, "Invalid email or password.")
            return render(request, "assistant/signin.html", {"email": email})
        login(request, user)
        flash.success(request, f"Welcome back, {user.account.display_name}! 👋")
        return redirect(request.GET.get("next") or "dashboard")

    return render(request, "assistant/signin.html", {})


def admin_required(view):
    """Allow only Admin-role accounts (or Django superusers)."""

    @functools.wraps(view)
    @login_required
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.account.is_admin:
            flash.error(request, "That area is for admins only.")
            return redirect("dashboard")
        return view(request, *args, **kwargs)

    return _wrapped


# --------------------------------------------------------------------------- #
# Auth / Google OAuth
# --------------------------------------------------------------------------- #
def auth_start(request: HttpRequest) -> HttpResponse:
    if not settings.GOOGLE_CLIENT_ID:
        # Google isn't set up — don't dead-end the user; drop them into the app
        # in demo mode instead of showing a scary error.
        flash.info(request, "Google isn't configured — entering demo mode. Add keys in core/.env for live data.")
        return redirect("demo_login")
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    return redirect(google_auth.build_authorization_url(state))


def auth_callback(request: HttpRequest) -> HttpResponse:
    if request.GET.get("state") != request.session.get("oauth_state"):
        flash.error(request, "Authentication state mismatch. Please try again.")
        return redirect("landing")
    code = request.GET.get("code")
    if not code:
        flash.error(request, "Google sign-in was cancelled.")
        return redirect("landing")

    creds = google_auth.exchange_code(code)
    email = _email_from_credentials(creds)
    if not email:
        flash.error(request, "Couldn't read your Google email. Please try again.")
        return redirect("landing")

    user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
    account, _ = Account.objects.get_or_create(user=user)
    account.google_email = email
    if creds.refresh_token:  # only present on first consent / prompt=consent
        account.refresh_token = creds.refresh_token
    account.save()

    login(request, user)
    flash.success(request, f"Connected as {email}. Your Chief of Staff is on duty. ✨")
    return redirect("dashboard")


def _email_from_credentials(creds) -> str | None:
    """Read the user's email from the OAuth id_token (no extra API call)."""
    try:
        import google.auth.transport.requests
        from google.oauth2 import id_token

        info = id_token.verify_oauth2_token(
            creds.id_token, google.auth.transport.requests.Request(), settings.GOOGLE_CLIENT_ID
        )
        return info.get("email")
    except Exception:  # pragma: no cover - fall back to userinfo endpoint
        try:
            from googleapiclient.discovery import build

            svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
            return svc.userinfo().get().execute().get("email")
        except Exception:
            logger.exception("Failed to resolve Google email")
            return None


def demo_login(request: HttpRequest) -> HttpResponse:
    """Keyless entry — sign in to the demo account and use the app right away.

    This is how you use DayBrief without configuring Google OAuth. It's enabled
    in dev, or whenever Google isn't configured (i.e. a personal/local setup);
    once real Google credentials are set in production it's turned off.
    """
    if settings.GOOGLE_CLIENT_ID and not settings.DEBUG:
        flash.info(request, "Demo mode is off in production — please connect Google.")
        return redirect("landing")

    user, created = User.objects.get_or_create(
        username="demo", defaults={"email": "demo@daybrief.ai"}
    )
    if created:
        user.set_password("demo12345")
        user.is_staff = True
        user.is_superuser = True
        user.save()

    account = user.account  # auto-created by signal
    account.google_email = account.google_email or "demo@daybrief.ai"
    if account.timezone == "UTC":
        account.timezone = settings.TIME_ZONE
    account.save()

    login(request, user)

    # Seed the demo account with REAL calendar records (once), then build today's
    # brief so the dashboard lands populated with genuine data — not fake values.
    demo.seed_calendar(account)
    today = timezone.localdate().isoformat()
    if not Brief.objects.filter(account=account, for_date=today).exists():
        try:
            briefing.build_brief(account)
        except Exception:
            logger.exception("Failed to pre-build demo brief")

    flash.success(request, "Welcome to DayBrief — demo mode. Add Google/AI keys anytime for live data. ✨")
    return redirect("dashboard")


def sign_out(request: HttpRequest) -> HttpResponse:
    logout(request)
    flash.info(request, "Signed out. See you tomorrow. 👋")
    return redirect("landing")


# --------------------------------------------------------------------------- #
# App (authenticated)
# --------------------------------------------------------------------------- #
@login_required
@ensure_csrf_cookie  # set the csrftoken cookie so the dashboard's fetch() POSTs work
def dashboard(request: HttpRequest) -> HttpResponse:
    account = request.user.account
    today = timezone.localdate().isoformat()
    brief = Brief.objects.filter(account=account, for_date=today).first()
    upcoming = (
        Reminder.objects.filter(account=account, status=Reminder.Status.PENDING)
        .only("id", "event_summary", "event_starts_at", "fire_at", "offset_minutes", "status")
        .order_by("fire_at")[:8]
    )
    # History list doesn't render the body/items — defer those heavy columns.
    recent_briefs = (
        Brief.objects.filter(account=account)
        .only("id", "for_date", "headline", "event_count", "reply_count", "created_at")
        .order_by("-created_at")[:7]
    )

    schedule, action_items = _split_brief_items(brief)
    tz = _tz(account.timezone)
    now_local = timezone.localtime(timezone=tz)
    pending_count = Reminder.objects.filter(account=account, status=Reminder.Status.PENDING).count()

    # Counts derived strictly from the brief's real items.
    brief_items = (brief.items_json if brief else []) or []
    meetings_today = sum(1 for it in brief_items if it.get("kind") == "event")
    emails_to_reply = sum(1 for it in brief_items if it.get("kind") == "reply")

    return render(
        request,
        "assistant/dashboard.html",
        {
            "account": account,
            "brief": brief,
            "upcoming": upcoming,
            "recent_briefs": recent_briefs,
            "connected": account.is_connected,
            "events_by_date": _grouped_events(account),
            "today_input": now_local.strftime("%Y-%m-%dT%H:%M"),
            "greeting": _greeting(now_local.hour),
            "today_str": now_local.strftime("%a, %d %b %Y"),
            "schedule": schedule,
            "action_items": action_items,
            "stats": {
                "meetings": meetings_today,
                "emails": emails_to_reply,
                "follow_ups": pending_count,
            },
        },
    )


def _greeting(hour: int) -> str:
    if hour < 12:
        return "Good morning!"
    if hour < 17:
        return "Good afternoon!"
    return "Good evening!"


def _split_brief_items(brief) -> tuple[list[dict], list[dict]]:
    """Split a brief's items into schedule rows and action items for the UI."""
    schedule: list[dict] = []
    actions: list[dict] = []
    if not brief:
        return schedule, actions
    for item in brief.items_json or []:
        kind = item.get("kind")
        title = (item.get("title") or "").strip()
        if not title:
            continue
        if kind == "event":
            # Titles look like "15:00 — Engineering Standup"; split time from name.
            time_part, _, name = title.partition(" — ")
            if name:
                schedule.append({"time": time_part, "title": name, "loc": item.get("detail")})
            else:
                schedule.append({"time": "", "title": title, "loc": item.get("detail")})
        else:  # reply / insight → action items
            actions.append({"title": title, "detail": item.get("detail"), "priority": item.get("priority", "normal")})
    return schedule, actions


def _tz(name: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(name)
    except Exception:
        return zoneinfo.ZoneInfo("UTC")


def _parse_local(raw: str | None, tz: zoneinfo.ZoneInfo) -> datetime | None:
    """Parse a datetime-local string ('YYYY-MM-DDTHH:MM') in the user's tz."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=tz)
        except (ValueError, TypeError):
            continue
    return None


def _grouped_events(account: Account) -> list[dict]:
    """Upcoming manual events grouped by local date, for the dashboard calendar."""
    tz = _tz(account.timezone)
    events = account.events.filter(start__gte=timezone.now() - timedelta(hours=12)).order_by("start")[:30]
    grouped: OrderedDict = OrderedDict()
    for event in events:
        local_start = event.start.astimezone(tz)
        grouped.setdefault(local_start.date(), []).append(
            {
                "id": event.id,
                "title": event.title,
                "time": "All day" if event.all_day else local_start.strftime("%H:%M"),
                "location": event.location,
            }
        )
    today = timezone.localtime(timezone=tz).date()
    out: list[dict] = []
    for day, items in grouped.items():
        if day == today:
            label = "Today"
        elif day == today + timedelta(days=1):
            label = "Tomorrow"
        else:
            label = day.strftime("%A, %d %b")
        out.append({"label": label, "date": day.strftime("%Y-%m-%d"), "items": items})
    return out


@login_required
@require_POST
def generate_now(request: HttpRequest) -> HttpResponse:
    """Build (or rebuild) today's brief on demand."""
    account = request.user.account
    try:
        briefing.build_brief(account)
        flash.success(request, "Fresh brief generated. ✅")
    except Exception:
        logger.exception("On-demand brief failed")
        flash.error(request, "Couldn't generate the brief — check your connection and API keys.")
    return redirect("dashboard")


@login_required
def brief_detail(request: HttpRequest, brief_id: int) -> HttpResponse:
    brief = get_object_or_404(Brief, pk=brief_id, account=request.user.account)
    return render(request, "assistant/brief_detail.html", {"brief": brief})


@login_required
def reminders_list(request: HttpRequest) -> HttpResponse:
    account = request.user.account
    pending = Reminder.objects.filter(account=account, status=Reminder.Status.PENDING).order_by("fire_at")
    sent = Reminder.objects.filter(account=account, status=Reminder.Status.SENT).order_by("-fire_at")[:25]
    return render(request, "assistant/reminders.html", {"pending": pending, "sent": sent})


@login_required
@require_POST
def update_settings(request: HttpRequest) -> HttpResponse:
    account = request.user.account
    account.brief_time = request.POST.get("brief_time", account.brief_time)[:5]
    account.timezone = request.POST.get("timezone", account.timezone)[:64]
    account.briefings_enabled = request.POST.get("briefings_enabled") == "on"
    account.reminders_enabled = request.POST.get("reminders_enabled") == "on"
    account.full_name = request.POST.get("full_name", account.full_name)[:150]
    account.save()
    flash.success(request, "Preferences saved.")
    return redirect("dashboard")


# --------------------------------------------------------------------------- #
# Admin — role-based team management
# --------------------------------------------------------------------------- #
@admin_required
def team(request: HttpRequest) -> HttpResponse:
    """Admin-only overview of every member + their activity."""
    members = (
        Account.objects.select_related("user")
        .annotate(n_briefs=Count("briefs", distinct=True), n_events=Count("events", distinct=True))
        .order_by("role", "-created_at")
    )
    return render(
        request,
        "assistant/team.html",
        {"members": members, "roles": Account.Role.choices},
    )


@admin_required
@require_POST
def set_role(request: HttpRequest, account_id: int) -> HttpResponse:
    """Promote/demote a member. Guards against removing the last admin."""
    target = get_object_or_404(Account, pk=account_id)
    new_role = request.POST.get("role")
    if new_role not in (Account.Role.ADMIN, Account.Role.MEMBER):
        flash.error(request, "Unknown role.")
        return redirect("team")

    if new_role == Account.Role.MEMBER and target.role == Account.Role.ADMIN:
        if Account.objects.filter(role=Account.Role.ADMIN).count() <= 1:
            flash.error(request, "Can't demote the last admin — promote someone else first.")
            return redirect("team")

    target.role = new_role
    target.save(update_fields=["role", "updated_at"])
    flash.success(request, f"{target.display_name} is now {target.get_role_display()}.")
    return redirect("team")


@login_required
@require_POST
def add_event(request: HttpRequest) -> HttpResponse:
    """Add a calendar event manually — it appears on its date and feeds the brief."""
    account = request.user.account
    title = (request.POST.get("title") or "").strip()
    all_day = request.POST.get("all_day") == "on"
    tz = _tz(account.timezone)
    start = _parse_local(request.POST.get("start"), tz)
    end = _parse_local(request.POST.get("end"), tz)

    if not title or start is None:
        flash.error(request, "Please give the event a title and a start time.")
        return redirect("dashboard")

    event = Event.objects.create(
        account=account,
        title=title[:300],
        start=start,
        end=end,
        location=(request.POST.get("location") or "").strip()[:300],
        all_day=all_day,
    )
    count = local_events.schedule_reminders(account, event)
    flash.success(
        request,
        f"Added “{event.title}” on {start.strftime('%d %b, %H:%M')}"
        + (f" · {count} reminder(s) set." if count else "."),
    )
    return redirect("dashboard")


@login_required
@require_POST
def delete_event(request: HttpRequest, event_id: int) -> HttpResponse:
    Event.objects.filter(pk=event_id, account=request.user.account).delete()
    flash.info(request, "Event removed.")
    return redirect("dashboard")
