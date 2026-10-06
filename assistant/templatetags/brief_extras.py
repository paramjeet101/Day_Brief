"""A tiny, dependency-free markdown renderer for brief bodies.

Supports the small subset the LLM actually emits: ## headings, - bullet lists,
and **bold**. Input is HTML-escaped first, so the output is safe to mark_safe.
"""

from __future__ import annotations

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_BOLD = re.compile(r"\*\*(.+?)\*\*")


@register.filter(name="brief_markdown")
def brief_markdown(text: str) -> str:
    if not text:
        return ""

    html: list[str] = []
    in_list = False

    for raw in text.splitlines():
        line = escape(raw.strip())
        line = _BOLD.sub(r"<strong>\1</strong>", line)

        if line.startswith("## "):
            if in_list:
                html.append("</ul>")
                in_list = False
            html.append(f"<h3>{line[3:]}</h3>")
        elif line.startswith("# "):
            if in_list:
                html.append("</ul>")
                in_list = False
            html.append(f"<h2>{line[2:]}</h2>")
        elif line.startswith("- "):
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{line[2:]}</li>")
        elif line:
            if in_list:
                html.append("</ul>")
                in_list = False
            html.append(f"<p>{line}</p>")

    if in_list:
        html.append("</ul>")
    return mark_safe("\n".join(html))
