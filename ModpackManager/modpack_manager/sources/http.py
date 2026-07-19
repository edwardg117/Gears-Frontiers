"""A shared requests.Session factory with transient-failure retries.

One retry policy for every outbound call in the source layer (Modrinth,
CurseForge) and the jar download in hashing.py, so a single 429/5xx or a
connection blip no longer turns a mod into an error row or drops a platform.
"""

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Retry connection/read errors and transient statuses with exponential backoff,
# honoring Retry-After. POST is opted in on purpose: both platforms' bulk update
# checks are POSTs but read-only lookups, so retrying them is safe.
_RETRY = Retry(
    total=3, connect=3, read=3, status=3,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET", "POST"}),
    backoff_factor=0.5,          # first retry: 0s, then ~1s, ~2s (urllib3 skips backoff on retry #1)
    backoff_max=30,              # caps the exponential backoff only (NOT a server-sent Retry-After)
    respect_retry_after_header=True,
    raise_on_status=True,        # exhausted -> raise, caught by the existing per-mod isolation
)


def build_session(headers: dict | None = None) -> Session:
    s = Session()
    adapter = HTTPAdapter(max_retries=_RETRY)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    if headers:
        s.headers.update(headers)
    return s
