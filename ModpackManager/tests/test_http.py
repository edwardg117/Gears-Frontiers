import responses
from urllib3.util.retry import Retry

from modpack_manager.sources import http


def test_build_session_mounts_a_retrying_adapter():
    s = http.build_session()
    r = s.get_adapter("https://api.example.com").max_retries
    assert isinstance(r, Retry)
    assert set(r.status_forcelist) >= {429, 500, 502, 503, 504}
    # the urllib3-kwarg-name guard: POST must be opted in (bulk lookups are POSTs)
    assert "POST" in r.allowed_methods and "GET" in r.allowed_methods
    assert r.total == 3


def test_build_session_applies_headers():
    s = http.build_session({"User-Agent": "X", "x-api-key": "k"})
    assert s.headers["User-Agent"] == "X" and s.headers["x-api-key"] == "k"


@responses.activate
def test_retries_transient_503_then_succeeds():
    responses.add(responses.GET, "https://x.test/api", status=503)
    responses.add(responses.GET, "https://x.test/api", json={"ok": True}, status=200)
    r = http.build_session().get("https://x.test/api", timeout=5)
    assert r.status_code == 200
    assert len(responses.calls) == 2          # the 503 was retried


@responses.activate
def test_does_not_retry_404():
    responses.add(responses.GET, "https://x.test/missing", status=404)
    r = http.build_session().get("https://x.test/missing", timeout=5)
    assert r.status_code == 404
    assert len(responses.calls) == 1          # non-transient, not retried


@responses.activate
def test_retries_429_with_retry_after_then_succeeds():
    responses.add(responses.GET, "https://x.test/rl", status=429, headers={"Retry-After": "0"})
    responses.add(responses.GET, "https://x.test/rl", json={"ok": True}, status=200)
    r = http.build_session().get("https://x.test/rl", timeout=5)
    assert r.status_code == 200
    assert len(responses.calls) == 2          # 429 retried, Retry-After: 0 honored (no real sleep)
