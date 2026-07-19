# Reliability & Error Surfacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the source layer resilient to transient API failures (retry/backoff/429), make the failures that remain *visible* to the maintainer (a warnings channel + banner), and make the generated MCUpdater `<Server>` template loader-correct.

**Architecture:** One shared retrying `requests.Session` factory (`sources/http.py`) routed through both platform sources and the jar download. A `Notice` type + `ScanResult` carry per-scan/per-search warnings additively through `scan()`/`real_search()` → the webapp JSON → a dismissible frontend banner. A small loader→launch-attribute map in `generate.py`.

**Tech Stack:** Python 3.12, `requests` + `urllib3` `Retry`, Flask, `pytest` + `responses`; vanilla-JS frontend (no build/test runner) verified by driving the app.

**Spec:** [docs/superpowers/specs/2026-07-19-reliability-and-error-surfacing-design.md](../specs/2026-07-19-reliability-and-error-surfacing-design.md)

**Decisions taken on the spec's open questions** (see spec §Open questions; all cheap to change):
- Retry policy = the spec's proposed defaults; the Task 1 test asserts the config.
- Loader map ships **only** verified `neoforge`/`forge` + a NeoForge default; unverified Fabric/Quilt strings are left as a TODO comment (never assert an unverified value). Current pack output is byte-identical.
- Launch attributes are **kept** on generated `<Server>` (not omitted); info-level notices **are** surfaced (muted/dismissible).

---

## File Structure

**Create:**
- `ModpackManager/modpack_manager/sources/http.py` — the shared retrying session factory + `Retry` policy. One responsibility.
- `ModpackManager/tests/test_http.py` — its tests.

**Modify:**
- `ModpackManager/modpack_manager/sources/base.py` — add a `Notice` dataclass.
- `ModpackManager/modpack_manager/sources/modrinth.py` — `_session()` builds via `http.build_session()`.
- `ModpackManager/modpack_manager/sources/curseforge.py` — `_session()` builds via `http.build_session()`.
- `ModpackManager/modpack_manager/hashing.py` — `compute()`'s default session builds via `http.build_session()`.
- `ModpackManager/modpack_manager/updates.py` — add `ScanResult`; `scan()` returns it; the two bulk prefilters and `_resolve_dependencies` return an optional `Notice`.
- `ModpackManager/modpack_manager/service.py` — `real_search()` returns `(hits, warnings)`; `generate_events` self-scan uses `.candidates`. (`real_scan()` body unchanged; its return type is now `ScanResult`.)
- `ModpackManager/modpack_manager/webapp.py` — cache key `candidates`→`scan`; `/api/updates` + `/api/search` return `warnings`; generate reads `cache["scan"].candidates`.
- `ModpackManager/modpack_manager/generate.py` — `_server_element`/`write_batch_xml` gain a `loader` param + `_LAUNCH` map.
- `ModpackManager/modpack_manager/web/{index.html,style.css,app.js}` — warnings banner + `renderWarnings`.
- Tests: `tests/test_updates.py`, `tests/test_webapp.py`, `tests/test_generate.py`.

**Conventions (from the codebase):**
- Run tests from `ModpackManager/`: `.venv/Scripts/python -m pytest`. Source tests mock HTTP with `responses` ([test_modrinth.py](../../../ModpackManager/tests/test_modrinth.py)).
- Webapp uses constructor DI ([webapp.py:11](../../../ModpackManager/modpack_manager/webapp.py:11)); tests inject fakes.
- Dataclasses carry `to_dict()` via `asdict` ([base.py:46](../../../ModpackManager/modpack_manager/sources/base.py:46)).

---

## Task 1: `sources/http.py` — retrying session factory (TDD)

**Files:** Create `modpack_manager/sources/http.py`, Test `tests/test_http.py`.

- [ ] **Step 1: Confirm the urllib3 major version** (decides the `Retry` kwarg names).

Run: `.venv/Scripts/python -c "import urllib3; print(urllib3.__version__)"`
Expected: `2.x` (this plan uses the v2 kwargs `allowed_methods` + `backoff_max`). If it prints `1.26.x`, use `allowed_methods` (also valid in 1.26) and drop `backoff_max` from the constructor (set `Retry.DEFAULT_BACKOFF_MAX` is not needed — omit it); the tests below still pass.

- [ ] **Step 2: Write the failing tests** — create `tests/test_http.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_http.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modpack_manager.sources.http'`.

- [ ] **Step 4: Implement `sources/http.py`**

```python
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
    backoff_max=30,              # cap any single backoff / honored Retry-After
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_http.py -v`
Expected: PASS (4 tests). If `test_retries_transient_503_then_succeeds` shows 1 call / status 503, the installed `responses` isn't driving the adapter's `Retry`; the config test still guards the policy — keep the config/404 tests and change the 503 test to assert the policy via `get_adapter(...).max_retries` instead of behavior, noting it in the commit.

- [ ] **Step 6: Commit**

```bash
git add ModpackManager/modpack_manager/sources/http.py ModpackManager/tests/test_http.py
git commit -m "feat: add shared retrying requests session factory (429/5xx + backoff)"
```

---

## Task 2: Route the sources + download through `build_session()` (TDD)

**Files:** Modify `sources/modrinth.py`, `sources/curseforge.py`, `hashing.py`. Test: extend `tests/test_modrinth.py` (wiring assertions).

- [ ] **Step 1: Write the failing wiring tests** — append to `tests/test_modrinth.py`:

```python
from urllib3.util.retry import Retry


def test_modrinth_session_uses_retrying_adapter():
    r = modrinth._session().get_adapter("https://api.modrinth.com").max_retries
    assert isinstance(r, Retry) and 429 in r.status_forcelist


def test_curseforge_session_uses_retrying_adapter():
    from modpack_manager.sources import curseforge
    r = curseforge._session("k").get_adapter("https://api.curseforge.com").max_retries
    assert isinstance(r, Retry) and 429 in r.status_forcelist


def test_hashing_default_session_uses_retrying_adapter():
    from modpack_manager import hashing
    s = hashing._download_session()
    r = s.get_adapter("https://cdn.example.com").max_retries
    assert isinstance(r, Retry) and 429 in r.status_forcelist
```

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py -k "retrying_adapter" -v`
Expected: FAIL — the sessions still use a bare `requests.Session` (no retrying adapter), and `hashing._download_session` doesn't exist yet.

- [ ] **Step 2: Wire Modrinth** — in `modpack_manager/sources/modrinth.py`, add the import and rewrite `_session` ([modrinth.py:17](../../../ModpackManager/modpack_manager/sources/modrinth.py:17)):

```python
from . import http
```
```python
def _session(api_key: str = "") -> requests.Session:
    headers = {"User-Agent": _UA}
    if api_key:
        headers["Authorization"] = api_key
    return http.build_session(headers)
```

- [ ] **Step 3: Wire CurseForge** — in `modpack_manager/sources/curseforge.py`, add the import and rewrite `_session` ([curseforge.py:39](../../../ModpackManager/modpack_manager/sources/curseforge.py:39)):

```python
from . import http
```
```python
def _session(api_key: str) -> requests.Session:
    return http.build_session({"x-api-key": api_key, "Accept": "application/json"})
```

- [ ] **Step 4: Wire hashing** — in `modpack_manager/hashing.py`, add a small helper and use it in `compute` ([hashing.py:30-35](../../../ModpackManager/modpack_manager/hashing.py:30)). Add near the top (after imports):

```python
from .sources import http


def _download_session():
    return http.build_session()
```

Then in `compute`, replace `session = session or requests.Session()` with:

```python
    session = session or _download_session()
```

(Keep the `import requests` line — it's still used for the `requests.Session` type elsewhere / no harm. If a linter flags it as unused after this change, remove it.)

- [ ] **Step 5: Run the wiring tests + full suite**

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py -v` then `.venv/Scripts/python -m pytest -q`
Expected: the three new wiring tests PASS; the whole suite stays green (the existing `responses`-based source/hashing tests are unaffected — a single registered `200` still returns `200`).

- [ ] **Step 6: Commit**

```bash
git add ModpackManager/modpack_manager/sources/modrinth.py ModpackManager/modpack_manager/sources/curseforge.py ModpackManager/modpack_manager/hashing.py ModpackManager/tests/test_modrinth.py
git commit -m "feat: route sources + jar download through the retrying session"
```

---

## Task 3: `Notice` + `ScanResult` + warnings plumbing (TDD)

**Files:** Modify `sources/base.py`, `updates.py`, `service.py`, `tests/test_updates.py`.

- [ ] **Step 1: Update the existing scan tests for the new return type + add warnings tests** — in `tests/test_updates.py`:

Change the three existing `scan` assertions to read `.candidates`:
- In `test_scan_dispatches_by_platform_and_sorts`: replace `ids = [c.mod_id for c in result]` with `ids = [c.mod_id for c in result.candidates]`, and add `assert result.warnings == []` at the end.
- In `test_scan_isolates_per_mod_errors`: replace `result[0]` with `result.candidates[0]` (both assertions).
- In `test_excluded_mods_are_skipped`: replace `assert result == []` with `assert result.candidates == []`.

Append these new tests:

```python
def test_resolve_dependencies_returns_notice_on_failure(monkeypatch):
    c = _cand_with_dep("m", "DEP1")
    def boom(*a, **k):
        raise RuntimeError("deps api down")
    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", boom)
    from modpack_manager.config import Config
    notice = updates._resolve_dependencies([c], Config())
    assert notice is not None and notice.code == "deps_unresolved" and notice.level == "warn"


def test_scan_warns_on_bulk_fallback_but_still_builds(monkeypatch):
    mods = {"a": _mod("a", "https://cdn.modrinth.com/data/A/versions/V/a.jar")}
    def boom(*a, **k):
        raise RuntimeError("bulk down")
    monkeypatch.setattr(updates.modrinth, "find_updated_mod_ids", boom)   # bulk prefilter fails
    monkeypatch.setattr(updates.modrinth, "build_candidate", lambda m, *a, **k: _cand(m.mod_id))
    from modpack_manager.config import Config
    result = updates.scan(mods, Config())
    assert [c.mod_id for c in result.candidates] == ["a"]                 # per-mod fallback still built it
    assert any(w.code == "modrinth_bulk_fallback" and w.level == "info" for w in result.warnings)
```

Run: `.venv/Scripts/python -m pytest tests/test_updates.py -v`
Expected: FAIL — `AttributeError: 'list' object has no attribute 'candidates'` (and `Notice` unused yet).

- [ ] **Step 2: Add the `Notice` dataclass** — in `modpack_manager/sources/base.py`, after `ChangelogEntry` (or anywhere top-level), add:

```python
@dataclass
class Notice:
    level: str          # "warn" | "info"
    code: str           # stable id for dedup/dismissal/tests
    message: str        # human text for the banner

    def to_dict(self) -> dict:
        return asdict(self)
```

- [ ] **Step 3: Add `ScanResult` + thread notices through `updates.py`**

At the top of `modpack_manager/updates.py`, add the import + container:

```python
from dataclasses import dataclass
from .sources.base import Candidate, Notice


@dataclass
class ScanResult:
    candidates: list
    warnings: list
```

Rewrite `_modrinth_to_check` ([updates.py:38](../../../ModpackManager/modpack_manager/updates.py:38)) to return a notice:

```python
def _modrinth_to_check(modrinth_mods, config):
    """Bulk-prefilter Modrinth mods. Returns (mods_to_build, notice_or_None)."""
    if not modrinth_mods:
        return [], None
    try:
        updated_ids, unresolved = modrinth.find_updated_mod_ids(
            modrinth_mods, config.mc_version, config.loader, config.modrinth_api_key)
        return [m for m in modrinth_mods if m.mod_id in updated_ids] + unresolved, None
    except Exception:  # bulk failed entirely -> per-mod fallback for all
        return list(modrinth_mods), Notice(
            "info", "modrinth_bulk_fallback",
            "Modrinth bulk update-check was unavailable — fell back to per-mod checks (results are complete).")
```

Rewrite `_curseforge_to_check` ([updates.py:51](../../../ModpackManager/modpack_manager/updates.py:51)):

```python
def _curseforge_to_check(cf_mods, config):
    """Bulk-prefilter CF mods. Returns (mods_to_build, contexts, notice_or_None)."""
    if not cf_mods:
        return [], {}, None
    try:
        updated_ids, unresolved, contexts = curseforge.find_updated_mod_ids(
            cf_mods, config.mc_version, config.loader, config.curseforge_api_key)
        return [m for m in cf_mods if m.mod_id in updated_ids] + unresolved, contexts, None
    except Exception:  # bulk failed entirely -> per-mod fallback for all
        return list(cf_mods), {}, Notice(
            "info", "curseforge_bulk_fallback",
            "CurseForge bulk update-check was unavailable — fell back to per-mod checks (results are complete).")
```

In `scan()` ([updates.py:65](../../../ModpackManager/modpack_manager/updates.py:65)), change the three result-unpacking lines and the return. Replace:

```python
        cf_to_check, cf_contexts = cf_future.result()
        modrinth_to_check = mr_future.result()
```
with:
```python
        cf_to_check, cf_contexts, cf_notice = cf_future.result()
        modrinth_to_check, mr_notice = mr_future.result()
```

and replace the tail of the function:

```python
    results.sort(key=lambda c: (_STATUS_ORDER.get(c.status, 9),
                                _SEVERITY_ORDER.get(c.severity, 9), c.name.lower()))
    _resolve_dependencies(results, config)
    return results
```
with:
```python
    results.sort(key=lambda c: (_STATUS_ORDER.get(c.status, 9),
                                _SEVERITY_ORDER.get(c.severity, 9), c.name.lower()))
    dep_notice = _resolve_dependencies(results, config)
    warnings = [n for n in (mr_notice, cf_notice, dep_notice) if n]
    return ScanResult(results, warnings)
```

Rewrite `_resolve_dependencies` ([updates.py:94](../../../ModpackManager/modpack_manager/updates.py:94)) to return a notice on failure — change its early `return` / `except`:
- the `if not dep_ids: return` → `if not dep_ids: return None`
- the `except Exception: return` → return the warn notice
- add `return None` at the very end (after the enrichment loop).

```python
    if not dep_ids:
        return None
    try:
        specs = modrinth.resolve_dependencies(
            list(dep_ids), config.mc_version, config.loader, config.modrinth_api_key)
    except Exception:
        return Notice("warn", "deps_unresolved",
                      "Dependency resolution failed — new required dependencies were not auto-queued. "
                      "Check the changelog banners and add them manually.")
    for c in results:
        for d in c.added_dependencies:
            # ... existing enrichment body unchanged ...
    return None
```

- [ ] **Step 4: Update `service.py`** — `real_search` returns `(hits, warnings)` and `generate_events` uses `.candidates`.

Add the import (with the existing source imports, [service.py:12](../../../ModpackManager/modpack_manager/service.py:12)):
```python
from .sources.base import Notice
```

Rewrite `real_search` ([service.py:58](../../../ModpackManager/modpack_manager/service.py:58)):
```python
def real_search(query, platform="both"):
    paths = pack_paths()
    config = load_config(paths.config_ini)
    hits, warnings = [], []
    if platform in ("both", "modrinth"):
        try:
            hits += modrinth.search(query, config.mc_version, config.loader, config.modrinth_api_key)
        except Exception:  # noqa: BLE001
            warnings.append(Notice("warn", "modrinth_search_failed",
                                   "Modrinth search failed — showing CurseForge results only."
                                   if platform == "both" else "Modrinth search failed."))
    if platform in ("both", "curseforge"):
        try:
            hits += curseforge.search(query, config.mc_version, config.loader, config.curseforge_api_key)
        except Exception:  # noqa: BLE001
            warnings.append(Notice("warn", "curseforge_search_failed",
                                   "CurseForge search failed — showing Modrinth results only."
                                   if platform == "both" else "CurseForge search failed."))
    return hits, warnings
```

In `generate_events`, change the self-scan fallback line ([service.py:104](../../../ModpackManager/modpack_manager/service.py:104)) from `candidates = real_scan()` to:
```python
        candidates = real_scan().candidates
```
(`real_scan()`'s body is unchanged — it returns `upd.scan(...)`, which is now a `ScanResult`.)

- [ ] **Step 5: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_updates.py -v` then `.venv/Scripts/python -m pytest -q`
Expected: `test_updates.py` PASSES (including the two new tests). Full suite: **`test_webapp.py` still passes** — its injected `scan_fn` fake still returns a plain list and the webapp route hasn't changed yet (Task 4). If `test_service.py` fails, check the `generate_events` self-scan edit (its tests pass explicit candidates, so they should be unaffected).

- [ ] **Step 6: Commit**

```bash
git add ModpackManager/modpack_manager/sources/base.py ModpackManager/modpack_manager/updates.py ModpackManager/modpack_manager/service.py ModpackManager/tests/test_updates.py
git commit -m "feat: surface swallowed scan/search failures via a Notice/warnings channel"
```

---

## Task 4: Webapp — return `warnings` in the payloads (TDD)

**Files:** Modify `webapp.py`, `tests/test_webapp.py`.

- [ ] **Step 1: Update the webapp tests** — in `tests/test_webapp.py`:

Add imports at the top:
```python
from modpack_manager.updates import ScanResult
from modpack_manager.sources.base import Notice
```

In `_client(...)`, change the two fakes so `scan_fn` returns a `ScanResult` and `search_fn` returns `(hits, warnings)`:
```python
        scan_fn=lambda: ScanResult([_cand()], []),
```
```python
        search_fn=lambda q, platform: ([SearchHit("modrinth", "AAB", "sodium", "Sodium", "", "", "p")], []),
```

Update `test_search_route` to expect the additive `warnings` key:
```python
def test_search_route():
    data = _client({}).get("/api/search?q=sodium&platform=both").get_json()
    assert data["hits"][0]["id"] == "AAB"
    assert data["warnings"] == []
```

Append a new test for `/api/updates`:
```python
def test_updates_route_returns_candidates_and_warnings():
    app = webapp.create_app(
        scan_fn=lambda: ScanResult([_cand()], [Notice("warn", "deps_unresolved", "deps failed")]),
        generate_fn=lambda p, c=None: iter([]), pack_fn=lambda: [],
        search_fn=lambda q, pl: ([], []), resolve_fn=lambda r: None,
        versions_fn=lambda pl, i: {}, commit_fn=lambda t, m: {"ok": True}, discard_fn=lambda t: {"ok": True})
    app.config["TESTING"] = True
    data = app.test_client().get("/api/updates").get_json()
    assert data["candidates"][0]["mod_id"] == "appleskin"
    assert data["warnings"][0]["code"] == "deps_unresolved"
```

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v`
Expected: FAIL — `test_search_route` gets no `warnings` key / `search_fn` now returns a tuple the route doesn't unpack; `/api/updates` iterates a `ScanResult`.

- [ ] **Step 2: Update `webapp.py`** — change the cache key + three routes.

Cache init ([webapp.py:14](../../../ModpackManager/modpack_manager/webapp.py:14)):
```python
    cache = {"scan": None, "last_touched": []}
```

`/api/updates` ([webapp.py:24-28](../../../ModpackManager/modpack_manager/webapp.py:24)):
```python
    @app.get("/api/updates")
    def updates():
        if cache["scan"] is None or request.args.get("refresh") == "1":
            cache["scan"] = scan_fn()
        sr = cache["scan"]
        return jsonify({"candidates": [c.to_dict() for c in sr.candidates],
                        "warnings": [w.to_dict() for w in sr.warnings]})
```

`/api/search` ([webapp.py:34-37](../../../ModpackManager/modpack_manager/webapp.py:34)):
```python
    @app.get("/api/search")
    def search():
        hits, warnings = search_fn(request.args.get("q", ""), request.args.get("platform", "both"))
        return jsonify({"hits": [h.to_dict() for h in hits],
                        "warnings": [w.to_dict() for w in warnings]})
```

`/api/generate` — the `stream()` closure ([webapp.py:53-57](../../../ModpackManager/modpack_manager/webapp.py:53)) reads candidates from the ScanResult:
```python
        def stream():
            sr = cache["scan"]
            for evt in generate_fn(payload, sr.candidates if sr else None):
                if evt.get("type") == "result":
                    cache["last_touched"] = evt.get("touched_files") or []
                yield json.dumps(evt) + "\n"
```

- [ ] **Step 3: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v` then `.venv/Scripts/python -m pytest -q`
Expected: all green (webapp incl. the new updates test; whole suite).

- [ ] **Step 4: Commit**

```bash
git add ModpackManager/modpack_manager/webapp.py ModpackManager/tests/test_webapp.py
git commit -m "feat: return scan/search warnings in /api/updates and /api/search"
```

---

## Task 5: Loader-aware server template (TDD)

**Files:** Modify `generate.py`, `service.py`, `tests/test_generate.py`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_generate.py`:

```python
def _regular(**over):
    e = {"kind": "regular", "op": "add", "name": "Sodium", "id": "sodium",
         "side": "BOTH", "required": True, "mod_type": "Regular", "depends": "",
         "mod_path": None, "url": "https://cdn/s.jar",
         "md5": "d41d8cd98f00b204e9800998ecf8427e", "size": 1, "version": "1"}
    e.update(over)
    return e


def _server(out):
    return ET.parse(out).getroot().find(".//m:Server", NS)


def test_launch_attrs_neoforge_unchanged(tmp_path):
    out = tmp_path / "u.xml"
    generate.write_batch_xml([_regular()], out, "1.21.1", loader="neoforge")
    s = _server(out)
    assert s.get("mainClass") == "cpw.mods.bootstraplauncher.BootstrapLauncher"
    assert s.get("launcherType") == "Vanilla"


def test_launch_attrs_unknown_loader_falls_back_to_neoforge(tmp_path):
    out = tmp_path / "u.xml"
    generate.write_batch_xml([_regular()], out, "1.21.1", loader="fabric")  # unmapped -> default
    assert _server(out).get("mainClass") == "cpw.mods.bootstraplauncher.BootstrapLauncher"
```

Run: `.venv/Scripts/python -m pytest tests/test_generate.py -v`
Expected: FAIL — `write_batch_xml()` takes no `loader` argument.

- [ ] **Step 2: Add the loader map + params in `generate.py`**

After `MCU_NS = "http://www.mcupdater.com"` ([generate.py:8](../../../ModpackManager/modpack_manager/generate.py:8)), add:

```python
# loader -> (mainClass, launcherType). These per-update <Server> attributes are
# effectively inert under <Import> (the entry pack supplies the launch-critical
# <Loader>), so this is correctness hygiene, not a launch fix. Only verified
# loaders are mapped; unknown loaders fall back to the NeoForge pair so this pack
# never regresses. Add "fabric"/"quilt" here once their mainClass is verified
# against MCUpdater's ServerPack schema.
_LAUNCH = {
    "neoforge": ("cpw.mods.bootstraplauncher.BootstrapLauncher", "Vanilla"),
    "forge":    ("cpw.mods.bootstraplauncher.BootstrapLauncher", "Vanilla"),
}
_DEFAULT_LAUNCH = _LAUNCH["neoforge"]
```

Rewrite `_server_element` ([generate.py:18](../../../ModpackManager/modpack_manager/generate.py:18)) to take `loader`:

```python
def _server_element(root, mc_version, loader):
    today = date.today().isoformat()
    main_class, launcher_type = _LAUNCH.get((loader or "").lower(), _DEFAULT_LAUNCH)
    return ET.SubElement(root, f"{{{MCU_NS}}}Server", {
        "id": f"update-{today}", "abstract": "false", "name": f"Update {today}",
        "newsUrl": "about:blank", "version": mc_version, "generateList": "true",
        "autoConnect": "false", "revision": "",
        "mainClass": main_class, "launcherType": launcher_type,
    })
```

Give `write_batch_xml` a `loader` param and pass it through ([generate.py:52-57](../../../ModpackManager/modpack_manager/generate.py:52)):

```python
def write_batch_xml(entries, out_path, mc_version, loader="neoforge"):
    """entries: list of {kind:'regular'|'removal', ...}. Regular entries already
    carry md5+size (the service downloads/hashes before calling this)."""
    ET.register_namespace("", MCU_NS)
    root = ET.Element(f"{{{MCU_NS}}}ServerPack", {"version": "4.1"})
    server = _server_element(root, mc_version, loader)
```

- [ ] **Step 3: Thread `config.loader` from the service call**

In `service.generate_events`, update the one call site ([service.py:158](../../../ModpackManager/modpack_manager/service.py:158)):
```python
    summary = gen.write_batch_xml(entries, out_path, config.mc_version, config.loader)
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_generate.py -v` then `.venv/Scripts/python -m pytest -q`
Expected: all green — the existing `test_write_batch_xml_regular_and_removal` (which calls `write_batch_xml(entries, out, mc_version="1.21.1")`) still passes via the `loader="neoforge"` default.

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/generate.py ModpackManager/modpack_manager/service.py ModpackManager/tests/test_generate.py
git commit -m "feat: loader-aware server template (verified loaders + NeoForge default)"
```

---

## Task 6: Frontend — warnings banner

**Files:** Modify `web/index.html`, `web/style.css`, `web/app.js`.

- [ ] **Step 1: Add the banner containers to `index.html`**

In the Updates panel, add a warnings container just before `<div class="panes">` ([index.html:23](../../../ModpackManager/modpack_manager/web/index.html:23)):
```html
    <div id="scan-warnings" class="warnings" hidden></div>
```

In the Add panel, add one just before `<div id="add-results" class="add-results"></div>` ([index.html:42](../../../ModpackManager/modpack_manager/web/index.html:42)):
```html
    <div id="add-warnings" class="warnings" hidden></div>
```

- [ ] **Step 2: Add styles to `style.css`** (append):

```css
/* --- scan/search warnings --- */
.warnings { display:flex; flex-direction:column; gap:4px; padding:.5rem .9rem 0; }
.warnings[hidden] { display:none; }
.notice { display:flex; align-items:center; gap:.5rem; padding:.45rem .6rem; border-radius:7px; font-size:.8rem; }
.notice span { flex:1; min-width:0; }
.notice.warn { border:1px solid rgba(255,159,10,.3); background:rgba(255,159,10,.1); color:var(--minor); }
.notice.info { border:1px solid var(--border); background:var(--panel); color:var(--muted); }
.notice-x { background:transparent; border:none; color:inherit; cursor:pointer; opacity:.7; font-size:.8rem; padding:0 2px; }
.notice-x:hover { opacity:1; }
```

- [ ] **Step 3: Add `renderWarnings` + wiring in `app.js`**

Add `dismissed: new Set()` to the `state` object literal ([app.js:1-6](../../../ModpackManager/modpack_manager/web/app.js:1)) — change the last line to:
```javascript
  releaseFilter: "", dismissed: new Set(),
```

Add the helper (near the other shared helpers, e.g. after `openLink` [app.js:10](../../../ModpackManager/modpack_manager/web/app.js:10)):
```javascript
function renderWarnings(list, container) {
  if (!container) return;
  container.innerHTML = "";
  const shown = (list || []).filter((n) => !state.dismissed.has(n.code));
  container.hidden = shown.length === 0;
  for (const n of shown) {
    const row = document.createElement("div");
    row.className = "notice " + (n.level === "info" ? "info" : "warn");
    const span = document.createElement("span");
    span.textContent = (n.level === "info" ? "ⓘ " : "⚠ ") + n.message;
    const x = document.createElement("button");
    x.type = "button"; x.className = "notice-x"; x.textContent = "✕"; x.setAttribute("aria-label", "Dismiss");
    x.addEventListener("click", () => { state.dismissed.add(n.code); renderWarnings(list, container); });
    row.append(span, x);
    container.append(row);
  }
}
```

In `load()` ([app.js:22](../../../ModpackManager/modpack_manager/web/app.js:22)), after `state.candidates = data.candidates || [];` add a `refresh` reset, and render the banner after the list renders. The body becomes:
```javascript
    const data = await res.json();
    if (refresh) state.dismissed.clear();
    state.candidates = data.candidates || [];
    state.selected = new Set(state.candidates.filter((c) => c.status === "ok").map((c) => c.mod_id));
    hideLoading(); renderUpdates(); renderQueue(); updateBatch();
    renderWarnings(data.warnings || [], $("#scan-warnings"));
```

In `runSearch()` ([app.js:89](../../../ModpackManager/modpack_manager/web/app.js:89)), clear the add note at the top and render warnings for the search (not the link-resolve) path. After `const data = await res.json();` and computing `hits`, add:
```javascript
    renderWarnings(looksLink ? [] : (data.warnings || []), $("#add-warnings"));
```
(and at the very top of `runSearch`, after reading `q`, you may clear it eagerly: `renderWarnings([], $("#add-warnings"));` — optional, the render above already clears on each search.)

- [ ] **Step 4: Verify JS parses**

Run: `node --check ModpackManager/modpack_manager/web/app.js`
Expected: success (no output).

- [ ] **Step 5: Verify the banner in the running app** — use the `ModpackManager:verify` skill.

Invoke `Skill(ModpackManager:verify)`, launch the app, open the browser pane, and via `javascript_tool` (the update list is ~130 rows so drive by JS, per the skill):
1. Confirm a clean scan surfaces no banner: `document.querySelector("#scan-warnings").hidden === true` after load, and that `GET /api/updates` includes a `warnings` key (`fetch("/api/updates").then(r=>r.json()).then(d => "warnings" in d)`).
2. Confirm rendering + dismissal deterministically: call `renderWarnings([{level:"warn",code:"deps_unresolved",message:"Dependency resolution failed"},{level:"info",code:"modrinth_bulk_fallback",message:"fell back to per-mod"}], document.querySelector("#scan-warnings"))`, then assert the container shows 2 `.notice` rows (one `.warn`, one `.info`) and is not hidden; click the warn row's `.notice-x` and assert it drops to 1 row and `state.dismissed.has("deps_unresolved")`.
Kill the server afterward.

- [ ] **Step 6: Commit**

```bash
git add ModpackManager/modpack_manager/web/index.html ModpackManager/modpack_manager/web/style.css ModpackManager/modpack_manager/web/app.js
git commit -m "feat: dismissible scan/search warnings banner"
```

---

## Task 7: Full regression + live reliability check

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all green (http, sources wiring, updates warnings, webapp warnings, generate loader — plus the pre-existing suite).

- [ ] **Step 2: Live degradation check** — via `ModpackManager:verify`, launch the app with the CurseForge key temporarily blanked in `mod_update_config.ini` (or point `curseforge.API` at an unreachable host in a throwaway way), run a search for a common mod, and confirm the Add tab shows the `curseforge_search_failed` warn note while Modrinth hits still render. Restore the config afterward. (A clean scan/search shows no banner — Step 1 of Task 6 Step 5 already covered the clean path.)

- [ ] **Step 3: Final commit (only if verification required tweaks)**

```bash
git add -A ModpackManager/
git commit -m "chore: reliability verification tweaks"
```
(Skip if nothing changed.)

---

## Notes for the implementer

- **The `Retry` config is the load-bearing test.** `test_build_session_mounts_a_retrying_adapter` guards the urllib3 kwarg-name pitfall (`allowed_methods` vs the deprecated `method_whitelist`) and the POST opt-in. Don't weaken it. If the behavioral 503-retry test can't fire under the installed `responses`, keep the config test and downgrade the behavioral one to a policy assertion (Task 1 Step 5).
- **`ScanResult` is a hard cut** — every `scan()`/`real_scan()` consumer must read `.candidates`. Tasks 3 and 4 update the two consumers (generate self-scan; the webapp routes) and their tests together; the suite is green at each commit because the webapp uses injected fakes.
- **Don't ship unverified loader strings.** Only `neoforge`/`forge` are mapped; everything else (incl. `fabric`) falls back to NeoForge by design. Adding Fabric/Quilt is a follow-up gated on verifying their `mainClass` against MCUpdater's schema.
- **Frontend has no JS runner** — Task 6's `ModpackManager:verify` step is the substitute; run it.
