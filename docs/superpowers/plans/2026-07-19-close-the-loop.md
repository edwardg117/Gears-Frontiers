# Close the Loop — Preview Diff & Local Commit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the generate step observable (live per-jar progress) and actionable in-app — review the real `git diff` of the two files the tool writes, then commit them locally — without ever touching `main` or pushing.

**Architecture:** `POST /api/generate` becomes an NDJSON stream (progress events, then a terminal result). A new path-scoped `git_ops.py` stages/commits/reverts **only** the two generated files. The webapp holds the touched paths server-side so the browser never names a file to stage. A frontend Result modal shows summary + diff and drives commit/discard.

**Tech Stack:** Python 3.12, Flask (streaming `Response`), `subprocess` + `git`, pytest; vanilla-JS frontend (no build, no JS test runner) verified by running the app.

**Spec:** [docs/superpowers/specs/2026-07-19-close-the-loop-design.md](../specs/2026-07-19-close-the-loop-design.md)

---

## File Structure

**Create:**
- `ModpackManager/modpack_manager/git_ops.py` — path-scoped git wrapper (diff / commit / discard). One responsibility: run `git` limited to an explicit pathspec, never `-A`.
- `ModpackManager/tests/test_git_ops.py` — unit tests against a temp git repo.

**Modify:**
- `ModpackManager/modpack_manager/service.py` — split `real_generate` into a `generate_events` generator (emits progress + a result carrying `touched_files`/`diff`/`manual_count`); keep `real_generate` as a thin drain; add `real_commit` / `real_discard`.
- `ModpackManager/modpack_manager/webapp.py` — `create_app` gains `commit_fn`, `discard_fn`; `generate_fn` becomes the event generator; `/api/generate` streams NDJSON and records `cache["last_touched"]`; add `/api/commit`, `/api/discard`.
- `ModpackManager/modpack_manager/__main__.py` — wire `generate_fn=generate_events`, `commit_fn=real_commit`, `discard_fn=real_discard`.
- `ModpackManager/tests/test_webapp.py` — update the DI fake for the new signature + streaming; add commit/discard tests.
- `ModpackManager/tests/test_service.py` — **create** (new file) for `generate_events` / `real_commit` tests.
- `ModpackManager/modpack_manager/web/index.html` — add the Result modal.
- `ModpackManager/modpack_manager/web/style.css` — diff view, progress, danger button, message input.
- `ModpackManager/modpack_manager/web/app.js` — rewrite `generate()` to consume the stream; add render/commit/discard functions.
- `ModpackManager/README.md` — document the in-app diff + commit step.

**Conventions to follow (from the existing code):**
- Repo root = `pack_paths().root` = `H:/repos/Gears-Frontiers` ([paths.py:24](../../../ModpackManager/modpack_manager/paths.py:24)). Touched paths are **repo-root-relative** with forward slashes.
- Preview pack basename: `GearsAndFrontiers_Preview.xml` ([paths.py:30](../../../ModpackManager/modpack_manager/paths.py:30)).
- The webapp uses constructor dependency injection with `create_app(...)` ([webapp.py:9](../../../ModpackManager/modpack_manager/webapp.py:9)); tests inject fakes ([test_webapp.py:12](../../../ModpackManager/tests/test_webapp.py:12)).
- Run tests from the `ModpackManager/` dir with the venv: `.venv/Scripts/python -m pytest`.

---

## Task 1: `git_ops.py` — path-scoped git wrapper (TDD)

This is the load-bearing safety module: it must stage/commit **only** the paths handed to it and never disturb the maintainer's unrelated dirty files. Build it test-first.

**Files:**
- Create: `ModpackManager/modpack_manager/git_ops.py`
- Test: `ModpackManager/tests/test_git_ops.py`

- [ ] **Step 1: Write the failing tests**

Create `ModpackManager/tests/test_git_ops.py`:

```python
import subprocess
import pytest

from modpack_manager import git_ops


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """A temp git repo with a committed preview file and an unrelated tracked file.
    Signing is disabled so tests never block on a key."""
    root = tmp_path
    _git(root, "init")
    _git(root, "config", "user.email", "t@t.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "GearsAndFrontiers_Preview.xml").write_text('<Server revision="1"/>\n', encoding="utf-8")
    (root / "unrelated.txt").write_text("original\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "baseline")
    return root


def _make_generated(repo):
    """Simulate what generate wrote: a new update file + a modified preview,
    plus an unrelated dirty file that must never be committed."""
    (repo / "updates").mkdir(exist_ok=True)
    (repo / "updates" / "u.xml").write_text("<newfile/>\n", encoding="utf-8")
    (repo / "GearsAndFrontiers_Preview.xml").write_text('<Server revision="2"/>\n', encoding="utf-8")
    (repo / "unrelated.txt").write_text("now dirty\n", encoding="utf-8")
    return ["updates/u.xml", "GearsAndFrontiers_Preview.xml"]


def test_commit_includes_only_named_paths(repo):
    paths = _make_generated(repo)
    res = git_ops.commit(repo, paths, "chore: test")
    assert res["ok"] is True and res["sha"]

    committed = subprocess.run(
        ["git", "-C", str(repo), "show", "--name-only", "--pretty=format:", "HEAD"],
        capture_output=True, text=True, check=True).stdout.split()
    assert set(committed) == {"updates/u.xml", "GearsAndFrontiers_Preview.xml"}

    # the unrelated file was never staged/committed — still dirty
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "unrelated.txt"],
                            capture_output=True, text=True, check=True).stdout
    assert "unrelated.txt" in status


def test_discard_reverts_new_and_modified(repo):
    paths = _make_generated(repo)
    res = git_ops.discard(repo, paths)
    assert res["ok"] is True
    assert not (repo / "updates" / "u.xml").exists()          # new file deleted
    assert (repo / "GearsAndFrontiers_Preview.xml").read_text(encoding="utf-8") == '<Server revision="1"/>\n'
    # unrelated dirty file left untouched
    assert (repo / "unrelated.txt").read_text(encoding="utf-8") == "now dirty\n"


def test_diff_is_readonly_and_shows_both(repo):
    paths = _make_generated(repo)
    out = git_ops.diff(repo, paths)
    assert "newfile" in out            # from the untracked --no-index diff
    assert 'revision="2"' in out       # from the tracked diff
    # read-only: the new file is still untracked after diff
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "updates/u.xml"],
                            capture_output=True, text=True, check=True).stdout
    assert status.startswith("??")


def test_commit_timeout_returns_flag(repo, monkeypatch):
    real_run = git_ops._run

    def fake_run(root, args, timeout=30, check=True):
        if args and args[0] == "commit":
            raise subprocess.TimeoutExpired(cmd="git commit", timeout=timeout)
        return real_run(root, args, timeout=timeout, check=check)

    monkeypatch.setattr(git_ops, "_run", fake_run)
    paths = _make_generated(repo)
    res = git_ops.commit(repo, paths, "chore: test")
    assert res["ok"] is False and res["timeout"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_git_ops.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modpack_manager.git_ops'`.

- [ ] **Step 3: Implement `git_ops.py`**

Create `ModpackManager/modpack_manager/git_ops.py`:

```python
"""Path-scoped git operations for the diff / commit / discard flow.

Every function takes an explicit list of repo-relative paths and NEVER runs a
broad ``git add -A`` / ``git add .`` — staging is provably limited to the paths
handed in, so the maintainer's unrelated working-tree changes are never touched.
"""

import subprocess
from pathlib import Path

_COMMIT_TIMEOUT = 120  # seconds — generous, to allow a YubiKey touch


def _run(root, args, timeout=30, check=True):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=check)


def _is_untracked(root, path) -> bool:
    out = _run(root, ["status", "--porcelain", "--", path]).stdout
    return out.startswith("??")


def diff(root, paths) -> str:
    """Unified diff of ``paths``. Read-only: mutates no git state, so closing the
    result modal without acting leaves the tree exactly as generate left it.
    An untracked new file is diffed against /dev/null (git special-cases it
    cross-platform and exits 1 when there are differences — expected, not an error)."""
    parts = []
    for p in paths:
        if _is_untracked(root, p):
            r = _run(root, ["diff", "--no-index", "--", "/dev/null", p], check=False)
        else:
            r = _run(root, ["diff", "--", p], check=False)
        if r.stdout:
            parts.append(r.stdout)
    return "\n".join(parts)


def commit(root, paths, message) -> dict:
    """Stage and commit exactly ``paths``. The commit pathspec excludes any other
    pre-staged changes. Signing (YubiKey) happens inside ``git commit``; a timeout
    leaves the files staged so nothing is lost."""
    try:
        _run(root, ["add", "--", *paths])
        _run(root, ["commit", "-m", message, "--", *paths], timeout=_COMMIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "timeout": True,
                "error": "Key touch timed out — the files are staged; retry or commit from a terminal."}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": (e.stderr or e.stdout or str(e)).strip()}
    sha = _run(root, ["rev-parse", "--short", "HEAD"]).stdout.strip()
    return {"ok": True, "sha": sha}


def discard(root, paths) -> dict:
    """Revert exactly ``paths``: a modified tracked file is restored to HEAD; a
    newly-created (untracked) file is deleted."""
    try:
        for p in paths:
            if _is_untracked(root, p):
                (Path(root) / p).unlink(missing_ok=True)
            else:
                _run(root, ["restore", "--", p])
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": (e.stderr or e.stdout or str(e)).strip()}
    return {"ok": True}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_git_ops.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/git_ops.py ModpackManager/tests/test_git_ops.py
git commit -m "feat: add path-scoped git_ops (diff/commit/discard)"
```

---

## Task 2: `service.py` — streaming generate + commit/discard delegates (TDD)

Split the existing `real_generate` ([service.py:95](../../../ModpackManager/modpack_manager/service.py:95)) into a generator that emits per-jar progress and a terminal result, keep a synchronous `real_generate` drain, and add thin `real_commit` / `real_discard`.

**Files:**
- Modify: `ModpackManager/modpack_manager/service.py`
- Test: `ModpackManager/tests/test_service.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `ModpackManager/tests/test_service.py`:

```python
import types
from datetime import date

from modpack_manager import service
from modpack_manager.sources.base import Candidate


def _fake_paths(tmp_path):
    return types.SimpleNamespace(
        root=tmp_path,
        updates_dir=tmp_path / "updates",
        preview_pack=tmp_path / "GearsAndFrontiers_Preview.xml",
        config_ini=tmp_path / "c.ini",
        cache_dir=tmp_path / "cache",
    )


def _patch_collaborators(monkeypatch, tmp_path, compute):
    monkeypatch.setattr(service, "pack_paths", lambda: _fake_paths(tmp_path))
    monkeypatch.setattr(service, "load_config", lambda p: types.SimpleNamespace(mc_version="1.21.1"))
    monkeypatch.setattr(service, "parse_packs", lambda layers: {})
    monkeypatch.setattr(service, "_pack_layer_paths", lambda paths: [])
    monkeypatch.setattr(service, "compute", compute)
    monkeypatch.setattr(service.gen, "write_batch_xml", lambda entries, out, mc: [])
    monkeypatch.setattr(service.gen, "wire_into_preview", lambda preview, url: "7")
    monkeypatch.setattr(service.git_ops, "diff", lambda root, paths: "DIFF")


def _cand():
    return Candidate(mod_id="a", name="ModA", platform="modrinth",
                     source_url="http://x/a.jar", current_version="1", latest_version="2",
                     severity="minor", side="BOTH", required=True, mod_type="Regular", status="ok")


def test_generate_events_emits_progress_then_result(monkeypatch, tmp_path):
    _patch_collaborators(monkeypatch, tmp_path, lambda url, cache=None: ("abc123", 10))
    events = list(service.generate_events(
        {"updates": ["a"], "adds": [], "removals": []}, [_cand()]))

    progress = [e for e in events if e["type"] == "progress"]
    result = [e for e in events if e["type"] == "result"][0]
    assert progress[0]["i"] == 1 and progress[0]["n"] == 1 and progress[0]["name"] == "ModA"
    today = date.today().isoformat()
    assert result["written_file"] == f"updates/updates-{today}.xml"
    assert result["touched_files"] == [f"updates/updates-{today}.xml", "GearsAndFrontiers_Preview.xml"]
    assert result["diff"] == "DIFF"


def test_generate_events_failure_yields_no_touched(monkeypatch, tmp_path):
    def boom(url, cache=None):
        raise RuntimeError("network")
    _patch_collaborators(monkeypatch, tmp_path, boom)
    events = list(service.generate_events(
        {"updates": ["a"], "adds": [], "removals": []}, [_cand()]))
    result = [e for e in events if e["type"] == "result"][0]
    assert result["failures"] and result["written_file"] is None
    assert result["touched_files"] == [] and result["diff"] == ""


def test_real_commit_delegates_to_git_ops(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(service, "pack_paths", lambda: types.SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(service.git_ops, "commit",
                        lambda root, paths, msg: seen.update(root=root, paths=paths, msg=msg) or {"ok": True, "sha": "z"})
    out = service.real_commit(["updates/u.xml", "GearsAndFrontiers_Preview.xml"], "msg")
    assert out == {"ok": True, "sha": "z"}
    assert seen["root"] == tmp_path and seen["paths"][0] == "updates/u.xml" and seen["msg"] == "msg"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_service.py -v`
Expected: FAIL — `AttributeError: module 'modpack_manager.service' has no attribute 'generate_events'` (and `git_ops`).

- [ ] **Step 3: Add the `git_ops` import to `service.py`**

In `ModpackManager/modpack_manager/service.py`, add to the imports block (after `from . import updates as upd` at [service.py:7](../../../ModpackManager/modpack_manager/service.py:7)):

```python
from . import git_ops
```

- [ ] **Step 4: Replace `real_generate` with `generate_events` + a drain, and add commit/discard**

In `ModpackManager/modpack_manager/service.py`, replace the entire `real_generate` function ([service.py:95-149](../../../ModpackManager/modpack_manager/service.py:95)) with:

```python
def generate_events(payload, candidates=None):
    """Generator: yields {'type':'progress',...} per downloaded jar, then a single
    {'type':'result',...}. payload: {updates:[mod_id], adds:[AddSpec], removals:[mod_id]}."""
    paths = pack_paths()
    config = load_config(paths.config_ini)
    modules = parse_packs(_pack_layer_paths(paths))
    if candidates is None:
        yield {"type": "progress", "phase": "scanning"}
        candidates = real_scan()
    cand_by_id = {c.mod_id: c for c in candidates}
    cache = HashCache(paths.cache_dir / "hashes.json")

    # Collect the jars to download first, so progress can report a known total.
    # Each spec: (op, name, mod_id, side, required, mod_type, depends, mod_path, url, version)
    specs = []
    for mid in payload.get("updates", []):
        c = cand_by_id.get(mid)
        if not c or c.status != "ok":
            continue
        m = modules.get(mid)
        specs.append(("update", c.name, mid, c.side, c.required, c.mod_type,
                      m.depends if m else "", m.mod_path if m else None,
                      c.source_url, c.latest_version))
    for spec in payload.get("adds", []):
        specs.append(("add", spec["name"], spec["module_id"], spec.get("side", "BOTH"),
                      bool(spec.get("required", True)), "Regular", "", None,
                      spec["url"], spec.get("version", "")))

    entries, failures = [], []
    total = len(specs)
    for i, (op, name, mod_id, side, required, mod_type, depends, mod_path, url, version) in enumerate(specs, 1):
        yield {"type": "progress", "i": i, "n": total, "name": name}
        try:
            md5, size = compute(url, cache=cache)
        except Exception as e:  # noqa: BLE001
            failures.append({"id": mod_id, "error": str(e)})
            continue
        entries.append({"kind": "regular", "op": op, "name": name, "id": mod_id,
                        "side": side, "required": required, "mod_type": mod_type,
                        "depends": depends, "mod_path": mod_path, "url": url,
                        "md5": md5, "size": size, "version": version})

    for mid in payload.get("removals", []):
        m = modules.get(mid)
        if m:
            entries.append({"kind": "removal", "name": m.name, "id": mid, "side": m.side,
                            "size": m.size, "required": m.required})

    manual_count = sum(1 for c in candidates if getattr(c, "status", None) == "manual")

    if failures:
        yield {"type": "result", "written_file": None, "new_revision": None, "mods": [],
               "failures": failures, "touched_files": [], "diff": "", "manual_count": manual_count}
        return
    if not entries:
        yield {"type": "result", "written_file": None, "new_revision": None, "mods": [],
               "failures": [], "note": "Nothing queued — nothing written.",
               "touched_files": [], "diff": "", "manual_count": manual_count}
        return

    today = date.today().isoformat()
    out_path = paths.updates_dir / f"updates-{today}.xml"
    summary = gen.write_batch_xml(entries, out_path, config.mc_version)
    new_rev = gen.wire_into_preview(paths.preview_pack, f"{_GITHUB_RAW}updates-{today}.xml")
    written_file = f"updates/updates-{today}.xml"
    touched = [written_file, paths.preview_pack.name]
    yield {"type": "result", "written_file": written_file, "new_revision": new_rev,
           "mods": summary, "failures": [], "touched_files": touched,
           "diff": git_ops.diff(paths.root, touched), "manual_count": manual_count}


def real_generate(payload, candidates=None):
    """Synchronous drain of generate_events -> the final result dict (minus the
    streaming-only 'type' key). Kept for non-streaming callers/tests."""
    result = {"written_file": None, "new_revision": None, "mods": [], "failures": []}
    for evt in generate_events(payload, candidates):
        if evt.get("type") == "result":
            result = {k: v for k, v in evt.items() if k != "type"}
    return result


def real_commit(touched, message):
    """Stage + commit exactly the paths generate wrote (see git_ops.commit)."""
    return git_ops.commit(pack_paths().root, touched, message)


def real_discard(touched):
    """Revert exactly the paths generate wrote (see git_ops.discard)."""
    return git_ops.discard(pack_paths().root, touched)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full suite to confirm nothing regressed**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS (existing tests still green; `test_webapp.py` still passes because its fake `generate_fn` isn't exercised as a generator yet — the route is unchanged until Task 3).

- [ ] **Step 7: Commit**

```bash
git add ModpackManager/modpack_manager/service.py ModpackManager/tests/test_service.py
git commit -m "feat: stream generate progress + add commit/discard service fns"
```

---

## Task 3: `webapp.py` — NDJSON streaming + commit/discard routes (TDD)

Change `create_app` to accept `commit_fn` / `discard_fn`, stream `/api/generate`, record `cache["last_touched"]` from the result, and add `/api/commit` + `/api/discard` that act only on the stored paths.

**Files:**
- Modify: `ModpackManager/modpack_manager/webapp.py`
- Modify: `ModpackManager/modpack_manager/__main__.py`
- Test: `ModpackManager/tests/test_webapp.py`

- [ ] **Step 1: Update the test file for the new signature + streaming**

Replace `ModpackManager/tests/test_webapp.py` in full:

```python
import json

from modpack_manager.sources.base import Candidate, SearchHit
from modpack_manager import webapp


def _cand(mod_id="appleskin"):
    return Candidate(mod_id=mod_id, name="AppleSkin", platform="modrinth",
                     source_url="https://x/new.jar", current_version="3.0.5",
                     latest_version="3.1.0", severity="minor", side="CLIENT",
                     required=True, mod_type="Regular", status="ok", latest_size=10)


def _client(calls):
    def _gen(payload, candidates=None):
        calls["gen"] = payload
        yield {"type": "progress", "i": 1, "n": 1, "name": "AppleSkin"}
        yield {"type": "result", "written_file": "updates/u.xml", "new_revision": "5",
               "mods": [], "failures": [],
               "touched_files": ["updates/u.xml", "GearsAndFrontiers_Preview.xml"],
               "diff": "diff text", "manual_count": 0}

    app = webapp.create_app(
        scan_fn=lambda: [_cand()],
        generate_fn=_gen,
        pack_fn=lambda: [{"mod_id": "farsight", "name": "Farsight", "version": "1.2",
                          "platform": "modrinth", "side": "BOTH"}],
        search_fn=lambda q, platform: [SearchHit("modrinth", "AAB", "sodium", "Sodium", "", "", "p")],
        resolve_fn=lambda ref: SearchHit("modrinth", "AAB", "sodium", "Sodium", "", "", "p"),
        versions_fn=lambda platform, pid: {"side": "CLIENT",
                                           "versions": [{"ref": "V1", "name": "0.5.8",
                                                         "type": "release", "url": "u"}]},
        commit_fn=lambda touched, message: calls.update(commit=(touched, message)) or {"ok": True, "sha": "abc1234"},
        discard_fn=lambda touched: calls.update(discard=touched) or {"ok": True})
    app.config["TESTING"] = True
    return app.test_client()


def _stream_lines(resp):
    return [json.loads(ln) for ln in resp.get_data(as_text=True).splitlines() if ln.strip()]


def test_pack_route():
    assert _client({}).get("/api/pack").get_json()["mods"][0]["mod_id"] == "farsight"


def test_search_route():
    data = _client({}).get("/api/search?q=sodium&platform=both").get_json()
    assert data["hits"][0]["id"] == "AAB"


def test_resolve_route():
    assert _client({}).get("/api/resolve?ref=sodium").get_json()["hit"]["slug"] == "sodium"


def test_versions_route():
    data = _client({}).get("/api/project-versions?platform=modrinth&id=AAB").get_json()
    assert data["side"] == "CLIENT" and data["versions"][0]["ref"] == "V1"


def test_index_served():
    assert _client({}).get("/").status_code == 200


def test_generate_streams_progress_then_result():
    calls = {}
    c = _client(calls)
    body = {"updates": ["appleskin"], "adds": [], "removals": ["farsight"]}
    resp = c.post("/api/generate", json=body)
    assert resp.status_code == 200
    events = _stream_lines(resp)
    assert events[0]["type"] == "progress"
    assert events[-1]["type"] == "result" and events[-1]["new_revision"] == "5"
    assert calls["gen"] == body


def test_commit_uses_stored_touched_paths():
    calls = {}
    c = _client(calls)
    # a generate must run first so the server records last_touched
    c.post("/api/generate", json={"updates": ["appleskin"], "adds": [], "removals": []}).get_data()  # consume the stream so last_touched is recorded
    resp = c.post("/api/commit", json={"message": "chore(preview): test"})
    assert resp.get_json() == {"ok": True, "sha": "abc1234"}
    touched, message = calls["commit"]
    assert touched == ["updates/u.xml", "GearsAndFrontiers_Preview.xml"]  # server-held, not client-sent
    assert message == "chore(preview): test"


def test_commit_without_generate_is_rejected():
    resp = _client({}).post("/api/commit", json={"message": "x"})
    assert resp.status_code == 400


def test_commit_blank_message_is_rejected():
    c = _client({})
    c.post("/api/generate", json={"updates": ["appleskin"], "adds": [], "removals": []}).get_data()  # consume the stream so last_touched is recorded
    assert c.post("/api/commit", json={"message": "   "}).status_code == 400


def test_discard_uses_stored_paths_and_clears_them():
    calls = {}
    c = _client(calls)
    c.post("/api/generate", json={"updates": ["appleskin"], "adds": [], "removals": []}).get_data()  # consume the stream so last_touched is recorded
    assert c.post("/api/discard").get_json() == {"ok": True}
    assert calls["discard"] == ["updates/u.xml", "GearsAndFrontiers_Preview.xml"]
    # cleared: a second discard now 400s (nothing recorded)
    assert c.post("/api/discard").status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v`
Expected: FAIL — `TypeError: create_app() got an unexpected keyword argument 'commit_fn'`.

- [ ] **Step 3: Rewrite `webapp.py`**

Replace `ModpackManager/modpack_manager/webapp.py` in full:

```python
"""Flask app: serve the picker UI and the scan/search/generate/commit JSON API."""

import json
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

_WEB_DIR = Path(__file__).parent / "web"


def create_app(scan_fn, generate_fn, pack_fn, search_fn, resolve_fn, versions_fn,
               commit_fn, discard_fn) -> Flask:
    app = Flask(__name__, static_folder=None)
    cache = {"candidates": None, "last_touched": []}

    @app.get("/")
    def index():
        return send_from_directory(_WEB_DIR, "index.html")

    @app.get("/web/<path:filename>")
    def web_asset(filename):
        return send_from_directory(_WEB_DIR, filename)

    @app.get("/api/updates")
    def updates():
        if cache["candidates"] is None or request.args.get("refresh") == "1":
            cache["candidates"] = scan_fn()
        return jsonify({"candidates": [c.to_dict() for c in cache["candidates"]]})

    @app.get("/api/pack")
    def pack():
        return jsonify({"mods": pack_fn()})

    @app.get("/api/search")
    def search():
        hits = search_fn(request.args.get("q", ""), request.args.get("platform", "both"))
        return jsonify({"hits": [h.to_dict() for h in hits]})

    @app.get("/api/resolve")
    def resolve():
        hit = resolve_fn(request.args.get("ref", ""))
        return jsonify({"hit": hit.to_dict() if hit else None})

    @app.get("/api/project-versions")
    def project_versions():
        return jsonify(versions_fn(request.args.get("platform", "modrinth"),
                                   request.args.get("id", "")))

    @app.post("/api/generate")
    def generate():
        payload = request.get_json(silent=True) or {}

        def stream():
            for evt in generate_fn(payload, cache["candidates"]):
                if evt.get("type") == "result":
                    cache["last_touched"] = evt.get("touched_files") or []
                yield json.dumps(evt) + "\n"

        return Response(stream_with_context(stream()), mimetype="application/x-ndjson")

    @app.post("/api/commit")
    def commit():
        touched = cache.get("last_touched") or []
        message = ((request.get_json(silent=True) or {}).get("message") or "").strip()
        if not touched:
            return jsonify({"ok": False, "error": "Nothing generated to commit."}), 400
        if not message:
            return jsonify({"ok": False, "error": "A commit message is required."}), 400
        return jsonify(commit_fn(touched, message))

    @app.post("/api/discard")
    def discard():
        touched = cache.get("last_touched") or []
        if not touched:
            return jsonify({"ok": False, "error": "Nothing to discard."}), 400
        result = discard_fn(touched)
        cache["last_touched"] = []
        return jsonify(result)

    return app
```

- [ ] **Step 4: Wire the new fns in `__main__.py`**

In `ModpackManager/modpack_manager/__main__.py`, update the import ([__main__.py:6](../../../ModpackManager/modpack_manager/__main__.py:6)) and the `create_app` call ([__main__.py:14](../../../ModpackManager/modpack_manager/__main__.py:14)):

```python
from .service import (real_scan, generate_events, real_pack, real_search,
                      real_resolve, real_project_versions, real_commit, real_discard)
from .webapp import create_app

HOST, PORT = "127.0.0.1", 5178


def main():
    app = create_app(scan_fn=real_scan, generate_fn=generate_events, pack_fn=real_pack,
                     search_fn=real_search, resolve_fn=real_resolve,
                     versions_fn=real_project_versions,
                     commit_fn=real_commit, discard_fn=real_discard)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v`
Expected: PASS (10 tests).

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS (all green).

- [ ] **Step 7: Commit**

```bash
git add ModpackManager/modpack_manager/webapp.py ModpackManager/modpack_manager/__main__.py ModpackManager/tests/test_webapp.py
git commit -m "feat: stream /api/generate; add /api/commit and /api/discard"
```

---

## Task 4: Frontend — Result modal markup + styles

No JS runner exists; this task adds the static structure the JS in Tasks 5–6 drives, verified by loading the page.

**Files:**
- Modify: `ModpackManager/modpack_manager/web/index.html`
- Modify: `ModpackManager/modpack_manager/web/style.css`

- [ ] **Step 1: Add the Result modal to `index.html`**

In `ModpackManager/modpack_manager/web/index.html`, immediately **after** the closing `</div>` of the `#review` overlay ([index.html:66](../../../ModpackManager/modpack_manager/web/index.html:66)) and before `<div id="status" ...>`, insert:

```html
  <div id="result" class="review-overlay" hidden>
    <div class="review-panel">
      <div class="review-head">
        <b id="result-title">Generating…</b>
        <button id="result-close" type="button" aria-label="Close" hidden>✕</button>
      </div>
      <p id="result-error" class="result-error" hidden></p>
      <div id="result-progress" class="result-progress">
        <div class="spinner"></div>
        <p id="result-progress-text">Starting…</p>
      </div>
      <div id="result-body" hidden></div>
      <div id="result-foot" class="review-foot" hidden>
        <input id="commit-message" class="commit-message" placeholder="Commit message">
        <button id="discard-btn" type="button" class="btn-danger">Discard</button>
        <button id="commit-btn" type="button" class="primary">Commit preview →</button>
      </div>
    </div>
  </div>
```

- [ ] **Step 2: Add styles to `style.css`**

Append to `ModpackManager/modpack_manager/web/style.css`:

```css
/* --- result modal: progress, diff, commit --- */
.result-progress { display:flex; flex-direction:column; align-items:center; gap:.7rem; padding:2rem 1rem; }
.result-progress[hidden] { display:none; }
.result-error { color:var(--major); padding:.4rem .9rem; margin:0; font-size:.82rem; }
.result-error[hidden] { display:none; }
#result-body { overflow-y:auto; padding:.4rem .9rem; }
.manual-note { margin:.5rem 0; padding:.5rem .6rem; border:1px solid rgba(255,159,10,.3);
  background:rgba(255,159,10,.1); color:var(--minor); border-radius:7px; font-size:.8rem; }
.diff { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.72rem; line-height:1.35;
  background:var(--bg); border:1px solid var(--border); border-radius:7px; overflow:auto;
  max-height:40vh; margin-top:.3rem; }
.diff .dl { white-space:pre; padding:0 .5rem; }
.diff .add { background:rgba(52,199,89,.14); color:#b8f0c4; }
.diff .del { background:rgba(255,69,58,.14); color:#ffc4bf; }
.diff .hunk { color:var(--accent); }
.diff .meta { color:var(--muted); }
.commit-message { flex:1; min-width:0; background:var(--bg); color:var(--text);
  border:1px solid var(--border); border-radius:6px; padding:.4rem .6rem; font-size:.8rem; }
.btn-danger { background:transparent; color:var(--major); border:1px solid var(--major);
  border-radius:6px; padding:.4rem .9rem; font-size:.82rem; font-weight:600; cursor:pointer; }
.btn-danger:disabled, .review-foot .primary:disabled { opacity:.5; cursor:default; }
#result-foot { gap:.6rem; }
```

- [ ] **Step 3: Verify the markup loads**

Start the app and confirm the page still renders with no console errors (the modal is `hidden`, so nothing visible changes yet):

Run: `.venv/Scripts/python -m modpack_manager`
Then in the opened browser, confirm the Updates tab renders as before. Stop with Ctrl+C.

- [ ] **Step 4: Commit**

```bash
git add ModpackManager/modpack_manager/web/index.html ModpackManager/modpack_manager/web/style.css
git commit -m "feat: add Result modal markup + diff/commit styles"
```

---

## Task 5: Frontend — consume the stream, render progress/summary/diff

Rewrite `generate()` to read the NDJSON stream and render the Result modal. Commit/discard wiring comes in Task 6.

**Files:**
- Modify: `ModpackManager/modpack_manager/web/app.js`

- [ ] **Step 1: Replace `generate()` and add the render helpers**

In `ModpackManager/modpack_manager/web/app.js`, replace the entire `generate()` function ([app.js:257-275](../../../ModpackManager/modpack_manager/web/app.js:257)) with the following block (keeps the existing payload construction, swaps the status-line handling for the streamed Result modal):

```javascript
async function generate() {
  const autoAdds = computeAutoDeps().map(({ dep }) => ({
    platform: "modrinth", module_id: dep.slug, name: dep.name, version: dep.version,
    url: dep.download_url, side: dep.side, required: true }));
  const payload = { updates: [...state.selected],
    adds: [...state.adds.map(({ page_url, ...a }) => a), ...autoAdds],
    removals: [...state.removals] };
  if (!payload.updates.length && !payload.adds.length && !payload.removals.length) { setStatus("Nothing queued.", true); return; }
  $("#review").hidden = true;
  openResultModal();
  try {
    const res = await fetch("/api/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok || !res.body) throw new Error("HTTP " + res.status);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "", result = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
        if (!line) continue;
        const evt = JSON.parse(line);
        if (evt.type === "progress") renderProgress(evt);
        else if (evt.type === "result") result = evt;
      }
    }
    if (!result) throw new Error("No result from server");
    renderResult(result);
  } catch (e) { resultError("Generate failed: " + e.message); }
}

// ---- result modal: state + rendering ----
function openResultModal() {
  $("#result").hidden = false;
  $("#result-title").textContent = "Generating…";
  $("#result-error").hidden = true;
  $("#result-progress").hidden = false;
  $("#result-progress-text").textContent = "Starting…";
  $("#result-body").hidden = true; $("#result-body").innerHTML = "";
  $("#result-foot").hidden = true;
  $("#result-close").hidden = true;
  $("#commit-btn").disabled = false; $("#discard-btn").disabled = false;
}
function closeResultModal() { $("#result").hidden = true; }
function renderProgress(evt) {
  const t = $("#result-progress-text");
  t.textContent = evt.phase === "scanning" ? "Re-scanning for updates…"
    : `Hashing ${evt.i} / ${evt.n} · ${evt.name}…`;
}
function resultError(msg, retry = false) {
  $("#result-progress").hidden = true;
  const err = $("#result-error"); err.textContent = msg; err.hidden = false;
  $("#result-close").hidden = false;
  $("#result-foot").hidden = !retry;
  $("#commit-btn").disabled = false; $("#discard-btn").disabled = false;
}
function renderDiff(text) {
  if (!text || !text.trim()) return '<p class="muted">No diff available.</p>';
  const cls = (l) =>
    l.startsWith("+++") || l.startsWith("---") ? "meta" :
    l.startsWith("@@") ? "hunk" :
    l.startsWith("+") ? "add" :
    l.startsWith("-") ? "del" :
    (l.startsWith("diff ") || l.startsWith("index ") || l.startsWith("new file") || l.startsWith("deleted file")) ? "meta" : "";
  const lines = text.split("\n").map((l) => `<div class="dl ${cls(l)}">${esc(l) || "&nbsp;"}</div>`).join("");
  return `<div class="diff">${lines}</div>`;
}
function resultSummaryHtml() {
  const upd = [...state.selected].map((id) => state.candidates.find((c) => c.mod_id === id)).filter(Boolean);
  const rem = [...state.removals].map((id) => state.pack.find((m) => m.mod_id === id) || { mod_id: id, name: id });
  const autoAdds = computeAutoDeps().map(({ dep, requiredBy }) => ({ name: dep.name || dep.slug, version: dep.version, auto: true, requiredBy }));
  const adds = [...state.adds, ...autoAdds];
  const sec = (title, items, render) => items.length
    ? `<div class="review-sec">${title} (${items.length})</div>` + items.map(render).join("") : "";
  return (
    sec("Updates", upd, (c) => `<div class="review-item">${esc(c.name)} <span class="muted">${esc(c.current_version)} → ${esc(c.latest_version)}</span></div>`) +
    sec("Adds", adds, (a) => `<div class="review-item">+ ${esc(a.name)} <span class="muted">${esc(a.version)}</span>${a.auto ? ` <span class="dep-chip">dep of ${esc(a.requiredBy.join(", "))}</span>` : ""}</div>`) +
    sec("Removals", rem, (m) => `<div class="review-item">− ${esc(m.name)}</div>`)
  ) || '<p class="muted">Nothing queued.</p>';
}
function renderResult(result) {
  state.lastResult = result;
  $("#result-progress").hidden = true;
  const body = $("#result-body"), foot = $("#result-foot");
  const failures = result.failures || [];
  if (failures.length) {
    $("#result-title").textContent = "Generate failed";
    body.innerHTML = `<p class="muted">No file was written — these downloads failed:</p>` +
      failures.map((f) => `<div class="review-item">✕ ${esc(f.id)} <span class="muted">${esc(f.error)}</span></div>`).join("");
    body.hidden = false; foot.hidden = true; $("#result-close").hidden = false; return;
  }
  if (!result.written_file) {
    $("#result-title").textContent = "Nothing written";
    body.innerHTML = `<p class="muted">${esc(result.note || "Nothing queued.")}</p>`;
    body.hidden = false; foot.hidden = true; $("#result-close").hidden = false; return;
  }
  $("#result-title").textContent = "Review & commit preview";
  const manual = result.manual_count
    ? `<div class="manual-note">⚠ ${result.manual_count} mod(s) in this scan need manual updating (CurseForge-blocked) and were not included.</div>` : "";
  body.innerHTML = manual + resultSummaryHtml() +
    `<div class="review-sec">Diff — ${esc(result.written_file)} + preview pack</div>` +
    renderDiff(result.diff);
  body.hidden = false;
  const date = (result.written_file.match(/updates-(\d{4}-\d{2}-\d{2})/) || [])[1] || "";
  const b = batchCounts();
  const segs = [];
  if (b.u) segs.push(`${b.u} update${b.u > 1 ? "s" : ""}`);
  if (b.a) segs.push(`${b.a} add${b.a > 1 ? "s" : ""}`);
  if (b.r) segs.push(`${b.r} removal${b.r > 1 ? "s" : ""}`);
  $("#commit-message").value = `chore(preview): update ${date} — ${segs.join(", ")}`;
  foot.hidden = false; $("#result-close").hidden = false;
}
```

Also add `lastResult: null` to the `state` object literal at the top of the file ([app.js:1-6](../../../ModpackManager/modpack_manager/web/app.js:1)) — change the last field line to:

```javascript
  releaseFilter: "", lastResult: null,
```

- [ ] **Step 2: Verify progress + diff render end-to-end**

Use the ModpackManager verify skill to launch and drive the app:

Invoke: `Skill(ModpackManager:verify)` and follow it to: open the app, let the scan finish, keep a small selection (e.g. a couple of updates), click **Generate preview**, and confirm: (a) the modal shows `Hashing i / n · Name…` progress, then (b) a summary + a colored diff whose contents match `git diff` in a terminal, and (c) the commit-message box is prefilled. Do **not** commit yet (Task 6 wires the button). Then **discard the working-tree changes manually** (`git restore GearsAndFrontiers_Preview.xml` and delete the new `updates/updates-*.xml`) so the tree is clean for the next step.

Expected: progress animates, diff matches, no console errors.

- [ ] **Step 3: Commit**

```bash
git add ModpackManager/modpack_manager/web/app.js
git commit -m "feat: stream generate progress and render diff/summary in Result modal"
```

---

## Task 6: Frontend — commit & discard actions + README

Wire the Commit/Discard/Close buttons to the new endpoints with the YubiKey-aware states, and document the flow.

**Files:**
- Modify: `ModpackManager/modpack_manager/web/app.js`
- Modify: `ModpackManager/README.md`

- [ ] **Step 1: Add the action functions and button wiring**

In `ModpackManager/modpack_manager/web/app.js`, find the existing generate wiring ([app.js:276-277](../../../ModpackManager/modpack_manager/web/app.js:276)):

```javascript
$("#generate").addEventListener("click", generate);
$("#review-generate").addEventListener("click", generate);
```

Immediately **after** those two lines, add:

```javascript
async function commitPreview() {
  const message = $("#commit-message").value.trim();
  if (!message) { $("#commit-message").focus(); return; }
  $("#result-error").hidden = true;
  $("#commit-btn").disabled = true; $("#discard-btn").disabled = true;
  $("#result-title").textContent = "Touch your YubiKey to sign the commit…";
  try {
    const res = await fetch("/api/commit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
    const data = await res.json();
    if (data.ok) {
      $("#result-title").textContent = "Committed ✓";
      $("#result-foot").hidden = true;
      $("#result-body").innerHTML = `<p>Committed <b>${esc(data.sha)}</b>. Run <code>git push</code> when you're ready to make the preview live for MCUpdater testing.</p>`;
      $("#result-close").hidden = false;
    } else {
      $("#discard-btn").disabled = false;
      resultError(data.error || "Commit failed.", true);
    }
  } catch (e) { $("#discard-btn").disabled = false; resultError("Commit failed: " + e.message, true); }
}
async function discardChanges() {
  if (!confirm("Discard the generated changes? This reverts the preview pack and deletes the new update file.")) return;
  $("#discard-btn").disabled = true; $("#commit-btn").disabled = true;
  try {
    const res = await fetch("/api/discard", { method: "POST" });
    const data = await res.json();
    if (data.ok === false) { resultError(data.error || "Discard failed."); }
    else { closeResultModal(); setStatus("Discarded the generated changes — working tree restored."); }
  } catch (e) { resultError("Discard failed: " + e.message); }
}
$("#commit-btn").addEventListener("click", commitPreview);
$("#discard-btn").addEventListener("click", discardChanges);
$("#result-close").addEventListener("click", closeResultModal);
```

- [ ] **Step 2: Update the README "How it works" section**

In `ModpackManager/README.md`, replace the second paragraph of the intro ([README.md:14-16](../../../ModpackManager/README.md:14)) — the sentence starting "Your browser opens…" through "Press **Ctrl+C** to stop." — with:

```markdown
Your browser opens at http://127.0.0.1:5178/. Pick mods, read changelogs, and
click **Generate preview**. Watch the per-jar progress, review the built-in diff
of the update file and the Preview pack, then **Commit preview** (a local,
signed commit of just those two files — touch your YubiKey when prompted) or
**Discard** to roll the changes back. Push when you're ready, test the Preview
pack in MCUpdater, and promote to the main pack manually. Press **Ctrl+C** to stop.
```

And in the "How it works" list, replace the final bullet ([README.md:36](../../../ModpackManager/README.md:36)) "The tool performs **no git actions**…" with:

```markdown
- The tool can **commit the Preview pack + the dated update file** for you
  (staging *only* those two paths, never anything else in your working tree). It
  never edits the main pack and never pushes — those stay in your hands.
```

- [ ] **Step 3: Verify the full loop with the verify skill**

Invoke: `Skill(ModpackManager:verify)` and follow it to exercise the whole flow against a real (small) batch:
1. Generate → progress → Result modal with summary + diff.
2. Click **Commit preview**; when the title shows "Touch your YubiKey…", touch the key; confirm it lands on "Committed &lt;sha&gt; ✓".
3. In a terminal, `git show --stat HEAD` — confirm the commit contains **only** `GearsAndFrontiers_Preview.xml` + `updates/updates-<date>.xml`, and that any pre-existing dirty files (e.g. `mod_update_automation.py`) are **still uncommitted**.
4. Reset for cleanliness: `git reset --soft HEAD~1` if you want to undo the test commit (optional).
5. Re-run, and this time click **Discard**; confirm `git status` returns to its prior state (preview restored, new update file gone, unrelated dirty files intact).

Expected: commit is correctly scoped; discard fully reverts; unrelated changes never touched.

- [ ] **Step 4: Commit**

```bash
git add ModpackManager/modpack_manager/web/app.js ModpackManager/README.md
git commit -m "feat: wire in-app commit/discard of the preview + document the flow"
```

---

## Task 7: Full regression + final verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole test suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS — all of `test_git_ops`, `test_service`, `test_webapp` plus the pre-existing suite.

- [ ] **Step 2: Confirm the safety invariant one more time**

With a deliberately dirty unrelated file present (e.g. `echo x >> ../mod_update_automation.py`), run a generate → commit through the UI, then `git show --name-only HEAD` and confirm the unrelated file is **not** in the commit. Revert your test edit afterward (`git checkout -- ../mod_update_automation.py`).

Expected: the commit contains exactly the two generated files.

- [ ] **Step 3: Final commit (if any verification tweaks were needed)**

```bash
git add -A ModpackManager/
git commit -m "chore: close-the-loop verification tweaks"
```

(Skip if nothing changed.)

---

## Notes for the implementer

- **Never widen the git pathspec.** Every `git add` / `git commit` / `git restore` in `git_ops.py` takes explicit `--`-separated paths. Do not "simplify" to `git add -A` or `git commit -a` — the whole safety story depends on this, and it's the invariant Task 7 Step 2 checks.
- **Signing hangs the request until touched.** The 120 s commit timeout is deliberate. When testing, have the YubiKey ready; if a commit test ever runs unattended it will (correctly) return the timeout error, not hang forever.
- **`git diff --no-index` exits 1** when files differ — `git_ops.diff` passes `check=False` for exactly this reason. Don't add `check=True` there.
- **The frontend has no test runner** — the verify skill (`ModpackManager:verify`) is the substitute; run it, don't skip it.
```