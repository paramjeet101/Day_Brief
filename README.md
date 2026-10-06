# ☀︎ DayBrief AI — your AI Chief of Staff

DayBrief reads your **Google Calendar** and **Gmail** every morning and sends a
sharp, 30-second brief: what's coming up, what needs a reply, and what not to
miss. Whenever a new event lands on your calendar, it automatically schedules
smart reminders so nothing slips.

Built with **Django + Django REST Framework**, **Celery** for scheduling, and
**Claude** for the intelligence. Full-stack (server-rendered UI + JSON API),
containerized, and ready to deploy.

---

## ✨ Features

- **Morning brief, on time** — delivered at each user's chosen hour, in their timezone.
- **Knows what needs a reply** — scans recent unread mail and surfaces what matters.
- **Built-in calendar** — add events manually (no Google needed); they appear on their date and feed the brief.
- **Automatic reminders** — new calendar events get reminders at 1 day / 1 hour / 10 min before (configurable).
- **Multi-channel notifications** — email out of the box; Slack/Discord/Teams via webhook.
- **Encrypted tokens** — Google refresh tokens are Fernet-encrypted at rest.
- **Graceful fallback** — no API key? It generates a deterministic local brief so the app is always demoable.
- **Clean architecture** — `core/` (project config, settings split) + `assistant/` (domain app, services layer).

---

## 🏗️ Architecture

```
DayBrief_AI/
├── manage.py
├── core/                     # project package (config)
│   ├── settings/
│   │   ├── base.py           # shared settings
│   │   ├── dev.py            # local defaults
│   │   └── prod.py           # hardened production
│   ├── urls.py  wsgi.py  asgi.py
│   ├── celery.py             # Celery app + beat schedule
│   ├── templates/assistant/  # all HTML templates (namespaced)
│   ├── static/  (css/js)     # all frontend assets
│   └── .env                  # environment config (git-ignored)
├── assistant/                # the AI Chief of Staff domain app
│   ├── models.py             # Account, Brief, Reminder, SeenEvent
│   ├── views.py              # server-rendered pages + OAuth flow
│   ├── api.py                # DRF viewsets + health/brief endpoints
│   ├── tasks.py              # Celery tasks (briefs, polling, reminders)
│   ├── security.py           # Fernet encryption for tokens
│   ├── dto.py                # in-memory data objects
│   └── services/             # business logic
│       ├── google_auth.py    # OAuth flow
│       ├── calendar_client.py
│       ├── gmail_client.py
│       ├── llm.py            # Claude client (+ local fallback)
│       ├── briefing.py       # orchestration
│       ├── reminders.py      # scheduling + dispatch
│       ├── notifier.py       # email / webhook delivery
│       └── demo.py           # sample fixtures
├── render.yaml  build.sh      # free deploy on Render
└── requirements.txt
```

**Request flow:** morning → Celery Beat fires `send_due_briefs` → `deliver_brief`
gathers calendar + inbox → Claude synthesizes → `Brief` saved → emailed. In
parallel, `poll_calendars` finds new events and creates `Reminder` rows;
`dispatch_reminders` sends them when due.

---

## 🚀 Quickstart (local, no Docker)

```bash
# 1. Create a virtualenv and install deps
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt

# 2. Configure  (env file lives in core/)
copy core\.env.example core\.env  # Windows  (cp on macOS/Linux)
#   Fill in ANTHROPIC_API_KEY and Google OAuth keys (optional for demo).
#   Generate an encryption key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 3. Migrate + seed demo data
python manage.py migrate
python manage.py seed_demo        # creates demo user + a sample brief
python manage.py createsuperuser  # optional: for /admin

# 4. Run
python manage.py runserver
```

Open **http://localhost:8000/**.

> In dev, `CELERY_TASK_ALWAYS_EAGER=True` runs background tasks inline, so you
> don't need Redis or a worker to try things out. Emails print to the console.

### Running the scheduler for real

```bash
# Terminal 1 — worker
celery -A core worker -l info
# Terminal 2 — beat (periodic jobs)
celery -A core beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```
Set `CELERY_TASK_ALWAYS_EAGER=False` and point `REDIS_URL` at a running Redis.

---

## 🔑 Google OAuth setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Enable the **Google Calendar API** and **Gmail API**.
3. Create an **OAuth client ID** (type: Web application).
4. Add the authorized redirect URI: `http://localhost:8000/auth/callback/`
   (and your production `{BASE_URL}/auth/callback/`).
5. Put the client ID/secret in `.env`.

Then click **Connect Google** in the app — signing in connects the account and
stores an encrypted refresh token.

---

## 🔌 API

| Method | Endpoint                | Description                          |
|-------:|-------------------------|--------------------------------------|
| GET    | `/api/health/`          | Liveness/readiness (DB check)        |
| GET    | `/api/brief/today/`     | Today's brief (generates if missing) |
| POST   | `/api/brief/today/`     | Regenerate today's brief             |
| GET    | `/api/briefs/`          | Paginated brief history              |
| GET    | `/api/reminders/`       | Your reminders                       |
| GET/POST | `/api/events/`        | List / add calendar events           |
| DELETE | `/api/events/{id}/`     | Remove a calendar event              |

Authentication: **HTTP Basic** (e.g. `curl -u demo:demo12345 …`) or the web
session. Ready-made collections:

- **curl:** [`docs/api_curls.sh`](docs/api_curls.sh) — run `bash docs/api_curls.sh`
- **Postman:** import [`docs/DayBrief.postman_collection.json`](docs/DayBrief.postman_collection.json)

```bash
# quick examples
curl -s http://localhost:8000/api/health/
curl -s -u demo:demo12345 http://localhost:8000/api/brief/today/
curl -s -X POST -u demo:demo12345 http://localhost:8000/api/brief/today/   # regenerate
curl -s -u demo:demo12345 http://localhost:8000/api/briefs/
curl -s -u demo:demo12345 http://localhost:8000/api/reminders/
```

---

## ⚙️ Configuration reference

All settings are environment-driven — see [`.env.example`](.env.example) for the
full list (brief time, lookahead windows, reminder offsets, notification
channels, SMTP, model choice, etc.).

---

## 🧠 Model

Defaults to **`claude-sonnet-5`** (fast + capable). Override with `LLM_MODEL`.
The LLM call is retried with exponential backoff and bounded by a hard timeout,
so a slow response never stalls the morning job.

---

## 🔒 Security notes

- OAuth refresh tokens are Fernet-encrypted at rest (`FIELD_ENCRYPTION_KEY`).
- Production settings enforce HTTPS redirect, HSTS, secure cookies, and a
  strict host allowlist.
- Gmail access is **read-only**.

---

## 🌐 Deploy free (live URL)

**Render.com (free, no credit card) — recommended, gives a permanent URL:**
1. Push this repo to GitHub.
2. On [render.com](https://render.com) → **New → Blueprint** → select your repo.
3. Render reads [`render.yaml`](render.yaml), builds, and hands you an `https://…onrender.com` URL.
4. Open it → **Enter App** → done. (Free web services sleep after ~15 min idle and wake on the next visit.)

Optional: to use free **Groq** AI on the live site, add `LLM_PROVIDER=groq` and `LLM_API_KEY` in the Render dashboard.

**Instant temporary URL (no deploy) — while your local server runs:**
```bash
# one-off public https tunnel to localhost:8000 (no signup)
cloudflared tunnel --url http://localhost:8000
```

## ✅ Testing

```bash
python manage.py test          # 17 tests: models, services, views, API
```

## ⚡ Performance

- GZip compression on dynamic responses; WhiteNoise compressed static with
  1-year immutable caching (hashed filenames in prod).
- Persistent DB connections (`CONN_MAX_AGE`) with health checks.
- Deferred heavy columns (`.only(...)`) on list queries.
- Blocking Google/LLM calls run off the request path in Celery tasks.

## License

MIT — build on it freely.
