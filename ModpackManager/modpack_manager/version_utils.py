"""Classify the size of a version bump.

Minecraft mod version strings are inconsistent: some carry a leading MC-version
prefix (``mc1.21-2.0.0``, ``1.21.1-2.0.0``) and some a trailing ``+build`` tag
(``2.5.1+mc1.20.1``). We best-effort extract the real mod version; genuinely
unparseable strings fall back to "unknown" (severity is only a display label).
"""

import re
from packaging import version as _v

# leading MC-version-like prefix followed by a separator and the real version
_LEAD_MC = re.compile(r"(?:mc)?\d+(?:\.\d+)+[-_](.+)", re.IGNORECASE)
_NUM = re.compile(r"(\d+(?:\.\d+){0,3})")


def _extract(vstr: str):
    s = (vstr or "").split("+")[0].strip()  # drop +build metadata
    lead = _LEAD_MC.match(s)
    if lead and _NUM.search(lead.group(1)):  # strip MC prefix only if a version follows
        s = lead.group(1)
    match = _NUM.search(s)
    if not match:
        return None
    try:
        return _v.parse(match.group(1))
    except _v.InvalidVersion:
        return None


def classify_severity(current: str, latest: str) -> str:
    cur, lat = _extract(current), _extract(latest)
    if cur is None or lat is None:
        return "unknown"
    if lat.major > cur.major:
        return "major"
    if lat.minor > cur.minor:
        return "minor"
    if lat.micro > cur.micro:
        return "patch"
    return "patch" if lat > cur else "unknown"
