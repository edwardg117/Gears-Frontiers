"""Render Modrinth markdown and sanitize CurseForge HTML changelogs."""

import bleach
import markdown as _md

_ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr",
    "img", "span", "div", "table", "thead", "tbody", "tr", "th", "td",
}
_ALLOWED_ATTRS = {"a": ["href", "title", "rel"], "img": ["src", "alt", "title"]}


def sanitize_html(html: str) -> str:
    if not html:
        return ""
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)


def render_markdown(text: str) -> str:
    if not text:
        return ""
    html = _md.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
    return sanitize_html(html)
