"""Pluggable brief-generation engine.

Turns raw calendar + inbox data into a structured brief (headline, prioritized
items, markdown body). Works with **zero keys** out of the box via the smart
local engine, and can be upgraded to a real LLM — including free ones:

    LLM_PROVIDER = local      # default, no key, no cost, works offline
                 | groq       # FREE, no credit card — https://console.groq.com
                 | gemini     # FREE tier — https://aistudio.google.com/apikey
                 | openai     # or any OpenAI-compatible endpoint
                 | anthropic  # Claude

For every hosted provider we speak the OpenAI "chat/completions" dialect (Groq,
Gemini and OpenAI all expose it), so one small client covers them all. Any
failure falls back to the local engine, so a brief is always produced.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import httpx
from django.conf import settings
from tenacity import retry, stop_after_attempt, wait_exponential

from assistant.dto import BriefItem, CalendarEvent, InboxMessage
from assistant.services import local_brief

logger = logging.getLogger(__name__)

# Presets: base URL + a sensible default model for each free/hosted provider.
_PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "ollama": {  # fully local, free — run `ollama serve`
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.1",
    },
}

_SYSTEM_PROMPT = """You are an elite executive Chief of Staff. You receive a \
person's upcoming calendar events and recent unread emails, and produce a crisp \
morning brief.

Be direct, prioritize ruthlessly, and never invent facts. Call out schedule \
conflicts, back-to-back meetings, prep that's needed, and emails that clearly \
warrant a reply. Keep it skimmable — a busy person reads this in 30 seconds.

Respond with ONLY a JSON object (no prose, no code fences) matching:
{
  "headline": "one punchy sentence summarizing the day",
  "items": [
    {"kind": "event|reply|insight", "title": "...", "detail": "...", "priority": "low|normal|high"}
  ],
  "body_markdown": "short markdown with ## Schedule and ## Needs a Reply sections"
}
"""


# --------------------------------------------------------------------------- #
# Context rendering
# --------------------------------------------------------------------------- #
def _render_context(events: list[CalendarEvent], messages: list[InboxMessage], tz: str) -> str:
    lines = [f"User timezone: {tz}", f"Local time now: {datetime.now().isoformat()}", "", "## Calendar (upcoming)"]
    if events:
        for e in events:
            when = "all day" if e.is_all_day else e.start.strftime("%a %H:%M")
            who = f" — with {', '.join(e.attendees[:5])}" if e.attendees else ""
            loc = f" @ {e.location}" if e.location else ""
            lines.append(f"- {when}: {e.summary}{loc}{who}")
    else:
        lines.append("- (nothing scheduled)")

    lines.append("\n## Unread inbox (recent)")
    if messages:
        for m in messages:
            lines.append(f'- From {m.sender} — "{m.subject}": {m.snippet[:200]}')
    else:
        lines.append("- (inbox clear)")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        inner = text.split("```", 2)[1]
        text = inner[4:] if inner.lower().startswith("json") else inner
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Model did not return JSON")
    return json.loads(text[start : end + 1])


# --------------------------------------------------------------------------- #
# Provider resolution
# --------------------------------------------------------------------------- #
def _resolve_provider() -> dict | None:
    """Return an active provider config, or None to use the local engine."""
    provider = (settings.LLM_PROVIDER or "local").strip().lower()
    if provider == "local":
        return None

    if provider == "anthropic":
        key = settings.ANTHROPIC_API_KEY
        if not key:
            return None
        return {"kind": "anthropic", "key": key, "model": settings.LLM_MODEL or "claude-sonnet-5"}

    preset = _PROVIDERS.get(provider, {})
    base_url = settings.LLM_BASE_URL or preset.get("base_url")
    model = settings.LLM_MODEL or preset.get("model")
    # Gemini/OpenAI/Groq all need a key; Ollama runs locally without one.
    key = settings.LLM_API_KEY or (settings.ANTHROPIC_API_KEY if provider == "anthropic" else "")
    if not base_url or (provider != "ollama" and not key):
        logger.warning("LLM_PROVIDER=%s but missing key/base_url — using local engine.", provider)
        return None
    return {"kind": "openai", "provider": provider, "base_url": base_url.rstrip("/"), "key": key, "model": model}


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def _complete_openai(cfg: dict, context: str) -> str:
    """Call any OpenAI-compatible chat/completions endpoint (Groq/Gemini/OpenAI…)."""
    headers = {"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"}
    payload = {
        "model": cfg["model"],
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
    }
    resp = httpx.post(
        f"{cfg['base_url']}/chat/completions",
        headers=headers,
        json=payload,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def _complete_anthropic(cfg: dict, context: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=cfg["key"], timeout=settings.LLM_TIMEOUT_SECONDS)
    resp = client.messages.create(
        model=cfg["model"],
        max_tokens=settings.LLM_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def generate_brief(
    events: list[CalendarEvent], messages: list[InboxMessage], timezone_name: str
) -> tuple[str, list[BriefItem], str]:
    """Return (headline, items, body_markdown). Never raises — falls back locally."""
    cfg = _resolve_provider()
    if cfg is None:
        logger.info("Using the smart local brief engine (no LLM provider configured).")
        return local_brief.generate(events, messages, timezone_name)

    context = _render_context(events, messages, timezone_name)
    try:
        raw = _complete_anthropic(cfg, context) if cfg["kind"] == "anthropic" else _complete_openai(cfg, context)
        data = _extract_json(raw)
        logger.info("Brief generated via %s.", cfg.get("provider", cfg["kind"]))
    except Exception as exc:  # any provider/parse error → resilient local fallback
        logger.error("LLM (%s) failed (%s) — falling back to local engine.", cfg.get("provider", cfg["kind"]), exc)
        return local_brief.generate(events, messages, timezone_name)

    items = [
        BriefItem(
            kind=str(it.get("kind", "insight")),
            title=str(it.get("title", "")).strip(),
            detail=(str(it["detail"]).strip() if it.get("detail") else None),
            priority=str(it.get("priority", "normal")),
        )
        for it in data.get("items", [])
        if it.get("title")
    ]
    headline = str(data.get("headline", "Your day at a glance")).strip()
    body = str(data.get("body_markdown", "")).strip()
    if not items or not body:  # thin response → prefer the richer local brief
        return local_brief.generate(events, messages, timezone_name)
    return headline, items, body
