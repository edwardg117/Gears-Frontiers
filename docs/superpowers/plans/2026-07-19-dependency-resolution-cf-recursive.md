# CurseForge & Recursive Dependency Resolution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing selection-driven auto-add pipeline so it (1) detects **CurseForge** required dependencies (today CF candidates always carry `added_dependencies=[]`) and (2) resolves the full **transitive** closure of new required deps for both platforms, so "Queued to add" reflects everything an update pulls in — not just its first hop.

**Architecture:** One pipeline, two new feeders — no new queue, no new frontend model. CF detection mirrors Modrinth detection (read the latest file's `dependencies`, keep `relationType==3`, drop already-installed modIds). A new `curseforge.resolve_dependencies` parallels `modrinth.resolve_dependencies`. The Modrinth-only single-pass `updates._resolve_dependencies` becomes a **bounded (depth 4) two-platform fixpoint over a shared memo**: resolve the frontier, fold each dep's own `requires` into the next frontier, repeat; then flatten each candidate's transitive closure onto its `added_dependencies` (so the existing selection-driven drop/restore behaviour is inherited unchanged). Three frontend spots that hardcode Modrinth become `dep.platform`-driven, plus a cheap name guard for the cross-platform "already in pack" hazard.

**Tech Stack:** Python 3.10+, Flask, `requests`; `pytest` + `responses` (mocked HTTP) for backend tests; vanilla JS frontend (no JS test runner — verified by driving the app via the `ModpackManager:verify` skill).

**Design spec:** [docs/superpowers/specs/2026-07-19-dependency-resolution-cf-recursive-design.md](../specs/2026-07-19-dependency-resolution-cf-recursive-design.md)

**Run commands (all from `ModpackManager/`):**
- Full suite: `.venv/Scripts/python -m pytest -q`
- One test: `.venv/Scripts/python -m pytest tests/test_modrinth.py::test_name -v`

> **Note on line numbers:** the design spec's code references are from 2026-07-19 and several have since shifted (app.js grew; `computeAutoDeps` is now ~line 285, `generate` ~391). This plan anchors every edit by **function name + exact current code to replace**, not by line number. Show-and-replace the code blocks as written.

---

## File Structure

**Backend (`ModpackManager/modpack_manager/`)**
- `sources/base.py` — add one field (`platform`) to `AddedDependency`. No other change.
- `sources/modrinth.py` — `resolve_dependencies` gains a `requires` edge list in its output (reads a field already fetched; no new request).
- `sources/curseforge.py` — new `resolve_dependencies` + `_bulk_files` helper; `build_candidate` detects new required CF deps; `find_updated_mod_ids` also returns the installed-CF-modId set.
- `updates.py` — `_check`, `_curseforge_to_check`, `scan` thread the installed-CF set through; `_resolve_dependencies` is rewritten as the bounded two-platform transitive fixpoint (the only control-flow change).

**Frontend (`ModpackManager/modpack_manager/web/`)**
- `app.js` — `computeAutoDeps` (platform-aware dedup key + manual-skip + cross-platform name guard), `renderQueue` (real CF/MR pill on auto-deps), `generate` (auto-add spec carries `dep.platform`). `renderReader` needs **no change** — it already renders `added_dependencies` generically.

**Tests (`ModpackManager/tests/`)** — extend the existing mirror files: `test_sources_base.py`, `test_modrinth.py`, `test_curseforge.py`, `test_updates.py`.

**No change:** `service.py`/`webapp.py`/`generate.py`. Confirmed: `generate_events` (service.py:136-139) reads `spec["module_id"]`/`spec["url"]` and **ignores** `platform`, so CF and transitive add-specs already download + hash + write exactly like Modrinth ones. `AddedDependency.platform` rides along via `asdict` in `Candidate.to_dict()` with no serializer change.

---

## Task 1: Add `platform` field to `AddedDependency`

**Files:**
- Modify: `ModpackManager/modpack_manager/sources/base.py` (the `AddedDependency` dataclass)
- Test: `ModpackManager/tests/test_sources_base.py`

- [ ] **Step 1: Write the failing test**

Append to `ModpackManager/tests/test_sources_base.py`:

```python
def test_added_dependency_platform_defaults_and_roundtrips():
    from modpack_manager.sources.base import Candidate, AddedDependency
    # defaults to "modrinth" so every existing construction + test is unchanged
    assert AddedDependency(id="cloth-config", satisfied=False).platform == "modrinth"
    # CF deps set it explicitly, and it survives Candidate.to_dict() (asdict) nesting
    dep = AddedDependency(id="306612", satisfied=False, platform="curseforge")
    c = Candidate(mod_id="cbc", name="CBC", platform="curseforge", source_url="u",
                  current_version="1", latest_version="2", severity="minor", side="BOTH",
                  required=True, mod_type="Regular", added_dependencies=[dep], status="ok")
    assert c.to_dict()["added_dependencies"][0]["platform"] == "curseforge"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_sources_base.py::test_added_dependency_platform_defaults_and_roundtrips -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'platform'`.

- [ ] **Step 3: Add the field**

In `ModpackManager/modpack_manager/sources/base.py`, add the `platform` field as the last field of `AddedDependency`:

```python
@dataclass
class AddedDependency:
    id: str
    satisfied: bool
    name: str | None = None
    url: str = ""               # project page, for the "open" link
    slug: str = ""              # platform slug -> used as the add's module_id
    side: str = "BOTH"          # CLIENT | SERVER | BOTH (detected)
    version: str = ""           # resolved latest compatible version name
    download_url: str = ""      # primary-file jar URL to hash/add
    size: int | None = None     # primary-file size in bytes
    addable: bool = False       # True once resolved to a queueable spec
    platform: str = "modrinth"  # "modrinth" | "curseforge" — makes CF deps explicit
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_sources_base.py -v`
Expected: PASS (new test + the two existing base tests).

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/sources/base.py ModpackManager/tests/test_sources_base.py
git commit -m "feat: add platform field to AddedDependency"
```

---

## Task 2: `modrinth.resolve_dependencies` surfaces `requires` edges

The Modrinth resolver already fetches each dep's latest version but ignores that version's own `dependencies`. Recursion needs them — read the required project ids off the version we already have in hand (no new request).

**Files:**
- Modify: `ModpackManager/modpack_manager/sources/modrinth.py` (`resolve_dependencies`, inner `_latest` + the combine step)
- Test: `ModpackManager/tests/test_modrinth.py`

- [ ] **Step 1: Write the failing test**

Append to `ModpackManager/tests/test_modrinth.py`:

```python
@responses.activate
def test_resolve_dependencies_surfaces_required_requires():
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "DEP0001", "slug": "cloth-config", "title": "Cloth Config API",
         "client_side": "required", "server_side": "required"}], status=200)
    responses.add(responses.GET, f"{API}/project/DEP0001/version", json=[
        {"id": "CCV2", "version_number": "15.0.140", "date_published": "2026-07-10T00:00:00Z",
         "dependencies": [
             {"project_id": "ARCH99", "dependency_type": "required"},   # kept
             {"project_id": "OPT88", "dependency_type": "optional"},     # dropped
             {"project_id": None, "dependency_type": "required"}],       # no id -> dropped
         "files": [{"primary": True, "url": "https://cdn.modrinth.com/cc.jar", "size": 4242}]},
    ], status=200)
    out = modrinth.resolve_dependencies(["DEP0001"], "1.21.1", "neoforge")
    assert out["DEP0001"]["requires"] == ["ARCH99"]
    assert out["DEP0001"]["addable"] is True     # unchanged behaviour otherwise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py::test_resolve_dependencies_surfaces_required_requires -v`
Expected: FAIL with `KeyError: 'requires'`.

- [ ] **Step 3: Read the version's dependencies in `_latest`**

In `modrinth.resolve_dependencies`, replace the inner `_latest` function:

```python
    # 2) latest compatible version per dep (concurrent, failure-isolated)
    def _latest(pid):
        try:
            versions = _fetch_versions(session, pid, mc_version, loader)
            if not versions:
                return pid, None
            versions.sort(key=lambda v: v.get("date_published") or "", reverse=True)
            top = versions[0]
            pf = _primary_file(top)
            requires = [d["project_id"] for d in top.get("dependencies", [])
                        if d.get("dependency_type") == "required" and d.get("project_id")]
            return pid, {"version": top.get("version_number", "?"),
                         "download_url": pf.get("url", ""), "size": pf.get("size"),
                         "requires": requires}
        except Exception:
            return pid, None
```

- [ ] **Step 4: Include `requires` in the combined output**

In the same function, replace the combine block (the `# 3) combine ...` loop) so each spec carries `requires` (default `[]` when the version fetch failed):

```python
    # 3) combine; addable requires both a slug (module_id) and a download url
    out = {}
    for pid in dep_ids:
        m = meta.get(pid, {})
        v = latest_by_id.get(pid) or {}
        download_url = v.get("download_url", "")
        out[pid] = {"name": m.get("name"), "slug": m.get("slug", ""),
                    "side": m.get("side", "BOTH"), "version": v.get("version", ""),
                    "download_url": download_url, "size": v.get("size"),
                    "addable": bool(m.get("slug")) and bool(download_url),
                    "requires": v.get("requires", [])}
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py -v`
Expected: PASS (new test + all existing `resolve_dependencies` tests — they assert individual keys, so the added `requires` key doesn't break them).

- [ ] **Step 6: Commit**

```bash
git add ModpackManager/modpack_manager/sources/modrinth.py ModpackManager/tests/test_modrinth.py
git commit -m "feat: surface required-dependency edges from modrinth.resolve_dependencies"
```

---

## Task 3: New `curseforge.resolve_dependencies` (+ `_bulk_files` helper)

Mirror of the Modrinth resolver using CF's bulk endpoints: two bulk calls (`POST /mods`, `POST /mods/files`), no per-dep fan-out. Returns queueable add-specs, each with a `requires` edge list (the file's own `relationType==3` modIds) for transitive resolution.

**Files:**
- Modify: `ModpackManager/modpack_manager/sources/curseforge.py` (new `_bulk_files` + new `resolve_dependencies`; add `AddedDependency` is **not** needed here — that's Task 4)
- Test: `ModpackManager/tests/test_curseforge.py`

- [ ] **Step 1: Write the failing tests**

Append to `ModpackManager/tests/test_curseforge.py`:

```python
@responses.activate
def test_resolve_dependencies_happy_path_with_requires():
    # modId 306612 -> latest compatible file 8001 (from latestFilesIndexes);
    # that file itself requires modId 319057 (required) and 999999 (optional).
    responses.add(responses.POST, f"{API}/mods", json={"data": [
        {"id": 306612, "name": "Cloth Config API", "slug": "cloth-config",
         "allowModDistribution": True, "links": {"websiteUrl": "https://cf/cloth"},
         "latestFilesIndexes": [{"gameVersion": "1.21.1", "modLoader": 6, "fileId": 8001}]},
    ]}, status=200)
    responses.add(responses.POST, f"{API}/mods/files", json={"data": [
        {"id": 8001, "displayName": "15.0.140", "fileName": "cloth-15.0.140.jar",
         "fileLength": 512000, "downloadUrl": "https://edge.forgecdn.net/8001/cloth.jar",
         "dependencies": [{"modId": 319057, "relationType": 3},
                          {"modId": 999999, "relationType": 2}]},
    ]}, status=200)
    out = curseforge.resolve_dependencies([306612], "1.21.1", "neoforge", api_key="CF")
    spec = out["306612"]
    assert spec["name"] == "Cloth Config API"
    assert spec["slug"] == "cloth-config"
    assert spec["url"] == "https://cf/cloth"
    assert spec["side"] == "BOTH"
    assert spec["version"] == "15.0.140"
    assert spec["download_url"] == "https://edge.forgecdn.net/8001/cloth.jar"
    assert spec["size"] == 512000
    assert spec["addable"] is True
    assert spec["requires"] == ["319057"]           # required kept, optional dropped, str ids


@responses.activate
def test_resolve_dependencies_blocked_dep_not_addable():
    responses.add(responses.POST, f"{API}/mods", json={"data": [
        {"id": 306612, "name": "Blocked Lib", "slug": "blocked-lib",
         "allowModDistribution": False, "links": {"websiteUrl": "https://cf/blocked"},
         "latestFilesIndexes": [{"gameVersion": "1.21.1", "modLoader": 6, "fileId": 8001}]},
    ]}, status=200)
    responses.add(responses.POST, f"{API}/mods/files", json={"data": [
        {"id": 8001, "displayName": "1.0", "fileName": "blocked-1.0.jar",
         "fileLength": 100, "downloadUrl": None, "dependencies": []},
    ]}, status=200)
    out = curseforge.resolve_dependencies([306612], "1.21.1", "neoforge", api_key="CF")
    spec = out["306612"]
    assert spec["name"] == "Blocked Lib"            # meta still resolved -> name shows in banner
    assert spec["download_url"] == ""
    assert spec["addable"] is False
    assert spec["requires"] == []


def test_resolve_dependencies_no_key_returns_empty():
    assert curseforge.resolve_dependencies([306612], "1.21.1", "neoforge", api_key="") == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py -k resolve_dependencies -v`
Expected: FAIL with `AttributeError: module 'modpack_manager.sources.curseforge' has no attribute 'resolve_dependencies'`.

- [ ] **Step 3: Add the `_bulk_files` helper**

In `ModpackManager/modpack_manager/sources/curseforge.py`, add directly after `_bulk_mods` (so the bulk helpers sit together):

```python
def _bulk_files(session, file_ids):
    """fileId -> full file object, via POST /mods/files (richer than _bulk_file_to_mod)."""
    out = {}
    for chunk in _chunk(file_ids):
        r = session.post(f"{API}/mods/files", json={"fileIds": chunk}, timeout=30)
        r.raise_for_status()
        for f in r.json().get("data", []):
            if f.get("id") is not None:
                out[f["id"]] = f
    return out
```

- [ ] **Step 4: Add `resolve_dependencies`**

In the same file, add after `_bulk_files` (or after `find_updated_mod_ids` — anywhere in the bulk section):

```python
def resolve_dependencies(dep_mod_ids, mc_version, loader, api_key=""):
    """Resolve new CF dependency modIds into queueable add-specs.

    Returns {dep_mod_id(str): {name, slug, url, side, version, download_url, size,
    addable, requires}}, where `requires` is the list of same-platform (CF) modIds
    this dep's latest compatible file itself requires (relationType==3), for the
    transitive fixpoint. Two bulk calls, no per-dep fan-out. Best-effort: a dep we
    can't fully resolve comes back addable=False with whatever meta did resolve, so
    the UI still warns without auto-queuing it (mirrors modrinth.resolve_dependencies).
    """
    ids = list(dict.fromkeys(int(d) for d in dep_mod_ids if d is not None))  # de-dupe, keep order
    if not ids or not api_key:
        return {}
    session = _session(api_key)

    # 1) bulk mod meta: modId -> {name, slug, url, allow_dist, latest compatible file id}
    try:
        mods = _bulk_mods(session, ids)
    except requests.RequestException:
        mods = {}
    meta = {}
    for mid in ids:
        m = mods.get(mid)
        if not m:
            continue
        meta[mid] = {
            "name": m.get("name") or m.get("slug") or str(mid),
            "slug": m.get("slug") or "",
            "url": (m.get("links") or {}).get("websiteUrl", "") or "",
            "allow_dist": m.get("allowModDistribution", True),
            "file_id": _latest_compatible_file_id(m, mc_version, loader),
        }

    # 2) bulk file details for every resolved latest-file id
    file_ids = [meta[mid]["file_id"] for mid in meta if meta[mid]["file_id"]]
    try:
        files = _bulk_files(session, file_ids) if file_ids else {}
    except requests.RequestException:
        files = {}

    # 3) combine; side is BOTH (CF exposes no reliable per-dep side)
    out = {}
    for mid in ids:
        m = meta.get(mid, {})
        f = files.get(m.get("file_id")) or {}
        download_url = f.get("downloadUrl") or ""
        version = _clean_version(f.get("displayName"), f.get("fileName"), mc_version) if f else ""
        requires = [str(d["modId"]) for d in f.get("dependencies", [])
                    if d.get("relationType") == 3 and d.get("modId")]
        addable = bool(m.get("allow_dist", True)) and bool(download_url) and bool(m.get("slug"))
        out[str(mid)] = {
            "name": m.get("name"), "slug": m.get("slug", ""), "url": m.get("url", ""),
            "side": "BOTH", "version": version, "download_url": download_url,
            "size": f.get("fileLength"), "addable": addable, "requires": requires,
        }
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py -v`
Expected: PASS (three new tests + all existing CF tests untouched).

- [ ] **Step 6: Commit**

```bash
git add ModpackManager/modpack_manager/sources/curseforge.py ModpackManager/tests/test_curseforge.py
git commit -m "feat: add curseforge.resolve_dependencies with requires edges"
```

---

## Task 4: `curseforge.build_candidate` detects new required CF deps

Replace the literal `added_dependencies=[]` with detection that mirrors Modrinth's: keep `relationType==3` deps whose modId is **not** already installed. The 4th positional parameter (today the unused `current_project_ids`) is repurposed to the CF-installed-modId set, which is what CF detection actually needs.

**Files:**
- Modify: `ModpackManager/modpack_manager/sources/curseforge.py` (`build_candidate` signature param + the `added_dependencies` construction; add `AddedDependency` to the `.base` import)
- Test: `ModpackManager/tests/test_curseforge.py`

- [ ] **Step 1: Write the failing test**

Append to `ModpackManager/tests/test_curseforge.py`:

```python
@responses.activate
def test_build_candidate_detects_new_required_cf_dep():
    responses.add(responses.POST, f"{API}/mods/files",
                  json={"data": [{"id": 7568054, "modId": 999}]}, status=200)
    responses.add(responses.GET, f"{API}/mods/999",
                  json={"data": {"id": 999, "name": "Xaeros World Map",
                                 "allowModDistribution": True}}, status=200)
    responses.add(responses.GET, f"{API}/mods/999/files", json={"data": [
        {"id": 7600000, "displayName": "1.39.8", "fileName": "Xaeros_1.39.8.jar",
         "fileDate": "2026-07-10T00:00:00Z", "fileLength": 2000,
         "downloadUrl": "https://edge.forgecdn.net/files/7600/000/Xaeros_1.39.8.jar",
         "dependencies": [
             {"modId": 306612, "relationType": 3},   # required, not installed -> collected
             {"modId": 555, "relationType": 3},       # required, but installed -> skipped
             {"modId": 777, "relationType": 2}],      # optional -> ignored
         "gameVersions": ["1.21.1", "NeoForge"]},
        {"id": 7568054, "displayName": "1.39.4", "fileName": "Xaeros_1.39.4.jar",
         "fileDate": "2026-06-01T00:00:00Z", "fileLength": 1900,
         "downloadUrl": "https://edge.forgecdn.net/files/7568/054/Xaeros_1.39.4.jar",
         "gameVersions": ["1.21.1", "NeoForge"]},
    ]}, status=200)
    responses.add(responses.GET, f"{API}/mods/999/files/7600000/changelog",
                  json={"data": "<p>cl</p>"}, status=200)
    # 4th positional arg is now the installed-CF-modId set
    c = curseforge.build_candidate(_module(), "1.21.1", "neoforge", {555}, api_key="CF")
    deps = c.added_dependencies
    assert [d.id for d in deps] == ["306612"]
    assert deps[0].platform == "curseforge"
    assert deps[0].satisfied is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py::test_build_candidate_detects_new_required_cf_dep -v`
Expected: FAIL — `assert [] == ["306612"]` (build_candidate still hardcodes `added_dependencies=[]`).

- [ ] **Step 3: Import `AddedDependency`**

In `ModpackManager/modpack_manager/sources/curseforge.py`, extend the base import:

```python
from .base import Candidate, ChangelogEntry, AddedDependency, SearchHit
```

- [ ] **Step 4: Rename the 4th param and detect deps**

Change the `build_candidate` signature (rename `current_project_ids` -> `installed_cf_mod_ids`):

```python
def build_candidate(module, mc_version, loader, installed_cf_mod_ids, api_key="", ctx=None):
```

Then, inside `build_candidate`, replace the `blocked = ...` line and the `Candidate(...)` return's `added_dependencies=[]`. Locate this current code:

```python
        blocked = (not allow_dist) or not latest.get("downloadUrl")
        return Candidate(
            mod_id=module.mod_id, name=module.name, platform="curseforge",
            source_url=latest.get("downloadUrl") or module.url,
            current_version=current_ver,
            latest_version=latest_ver,
            severity=classify_severity(current_ver, latest_ver),
            side=module.side, required=module.required, mod_type=module.mod_type,
            changelogs=changelogs, added_dependencies=[],
```

Replace it with (adds the detection loop; sets `added_dependencies=added`):

```python
        added = []
        for dep in latest.get("dependencies", []):
            if dep.get("relationType") == 3 and dep.get("modId"):
                dep_mod_id = dep["modId"]
                if dep_mod_id not in installed_cf_mod_ids:
                    added.append(AddedDependency(id=str(dep_mod_id), satisfied=False,
                                                 platform="curseforge"))

        blocked = (not allow_dist) or not latest.get("downloadUrl")
        return Candidate(
            mod_id=module.mod_id, name=module.name, platform="curseforge",
            source_url=latest.get("downloadUrl") or module.url,
            current_version=current_ver,
            latest_version=latest_ver,
            severity=classify_severity(current_ver, latest_ver),
            side=module.side, required=module.required, mod_type=module.mod_type,
            changelogs=changelogs, added_dependencies=added,
```

(Leave the rest of the `Candidate(...)` call — `status=`, `note=`, `latest_size=`, `project_url=` — exactly as it is.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py tests/test_updates.py -v`
Expected: PASS. Existing CF `build_candidate` tests pass `set()` as the 4th arg and use latest files with no `dependencies` key, so they still produce `added_dependencies=[]`. `test_updates.py` monkeypatches CF `build_candidate` with `lambda m, *a, **k:` so the rename is transparent.

- [ ] **Step 6: Commit**

```bash
git add ModpackManager/modpack_manager/sources/curseforge.py ModpackManager/tests/test_curseforge.py
git commit -m "feat: detect new required dependencies in curseforge.build_candidate"
```

---

## Task 5: Thread `installed_cf_mod_ids` from the bulk prefilter

The CF bulk prefilter already resolves every installed CF file to its modId (`set(file_to_mod.values())`) and then discards it. Surface that set and thread it to CF detection so the "already installed" filter actually has data. This changes `find_updated_mod_ids`' return arity, so its consumer and the affected tests move together to keep the suite green.

**Files:**
- Modify: `ModpackManager/modpack_manager/sources/curseforge.py` (`find_updated_mod_ids` return)
- Modify: `ModpackManager/modpack_manager/updates.py` (`_curseforge_to_check`, `_check`, `scan`)
- Test: `ModpackManager/tests/test_curseforge.py`, `ModpackManager/tests/test_updates.py`

- [ ] **Step 1: Update the tests to expect the new arity (they will fail first)**

In `ModpackManager/tests/test_curseforge.py`, update the three `find_updated_mod_ids` unpackings to a 4-tuple and assert the installed set:

`test_find_updated_mod_ids_bulk_flags_only_changed` — change the unpack line and add an assertion:

```python
    updated, unresolved, contexts, installed = curseforge.find_updated_mod_ids(
        [ma, mb], "1.21.1", "neoforge", api_key="CF")
    assert updated == {"a"}                      # 11 has a newer fileId; 22 unchanged
    assert unresolved == []
    assert contexts["a"] == {"cf_mod_id": 11, "allow_dist": True, "website": "http://a"}
    assert installed == {11, 22}                 # every installed CF modId the bulk pass resolved
```

`test_find_updated_unresolved_when_no_matching_index` — change the unpack line and add:

```python
    updated, unresolved, contexts, installed = curseforge.find_updated_mod_ids(
        [ma], "1.21.1", "neoforge", api_key="CF")
    assert updated == set()
    assert [m.mod_id for m in unresolved] == ["a"]  # no index for our version -> fallback
    assert installed == {11}
```

`test_find_updated_no_api_key_marks_all_unresolved` — change the unpack line and add:

```python
    updated, unresolved, contexts, installed = curseforge.find_updated_mod_ids(
        [ma], "1.21.1", "neoforge", api_key="")
    assert updated == set()
    assert [m.mod_id for m in unresolved] == ["a"]
    assert contexts == {}
    assert installed == set()
```

In `ModpackManager/tests/test_updates.py`, update the CF monkeypatch in `test_scan_dispatches_by_platform_and_sorts` to return a 4-tuple:

```python
    monkeypatch.setattr(updates.curseforge, "find_updated_mod_ids",
                        lambda mods_, *a, **k: ({m.mod_id for m in mods_}, [], {}, set()))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py tests/test_updates.py -q`
Expected: FAIL — `ValueError: not enough values to unpack (expected 4, got 3)` for the CF tests.

- [ ] **Step 3: Return the installed set from `find_updated_mod_ids`**

In `ModpackManager/modpack_manager/sources/curseforge.py`, update `find_updated_mod_ids` — the no-key early return, the mid-function computation, and the final return:

```python
def find_updated_mod_ids(modules, mc_version, loader, api_key=""):
    """Bulk update check for many CurseForge mods in a handful of requests.

    Returns (updated_mod_ids, unresolved, contexts, installed_cf_mod_ids):
      - updated_mod_ids: set of mod ids with a newer compatible file
      - unresolved: modules the bulk pass couldn't decide (per-mod fallback)
      - contexts: mod_id -> {cf_mod_id, allow_dist, website} for resolved mods,
        so build_candidate can skip re-fetching the recover + info calls.
      - installed_cf_mod_ids: every installed CF modId the bulk pass resolved
        (set(file_to_mod.values())), for dependency "already installed" filtering.
    """
    if not api_key:  # let the per-mod path report the key error for each mod
        return set(), list(modules), {}, set()
    session = _session(api_key)
    file_ids = [m.cf_file_id for m in modules if m.cf_file_id]
    file_to_mod = _bulk_file_to_mod(session, file_ids)
    mod_objs = _bulk_mods(session, list(set(file_to_mod.values())))
    installed_cf_mod_ids = set(file_to_mod.values())

    updated, unresolved, contexts = set(), [], {}
    for m in modules:
        cf_mod_id = file_to_mod.get(m.cf_file_id)
        mod_obj = mod_objs.get(cf_mod_id) if cf_mod_id is not None else None
        if mod_obj is None:
            unresolved.append(m)
            continue
        latest_fid = _latest_compatible_file_id(mod_obj, mc_version, loader)
        if latest_fid is None:
            unresolved.append(m)   # bulk index had nothing for our version/loader
            continue
        contexts[m.mod_id] = {
            "cf_mod_id": cf_mod_id,
            "allow_dist": mod_obj.get("allowModDistribution", True),
            "website": (mod_obj.get("links") or {}).get("websiteUrl", "") or "",
        }
        if latest_fid != m.cf_file_id:
            updated.add(m.mod_id)
    return updated, unresolved, contexts, installed_cf_mod_ids
```

- [ ] **Step 4: Thread it through `_curseforge_to_check`**

In `ModpackManager/modpack_manager/updates.py`, replace `_curseforge_to_check` entirely:

```python
def _curseforge_to_check(cf_mods, config):
    """Bulk-prefilter CF mods. Returns
    (mods_to_build, contexts, installed_cf_mod_ids, notice_or_None)."""
    if not cf_mods:
        return [], {}, set(), None
    try:
        updated_ids, unresolved, contexts, installed_cf_mod_ids = curseforge.find_updated_mod_ids(
            cf_mods, config.mc_version, config.loader, config.curseforge_api_key)
        return ([m for m in cf_mods if m.mod_id in updated_ids] + unresolved,
                contexts, installed_cf_mod_ids, None)
    except Exception:  # bulk failed entirely -> per-mod fallback for all
        return list(cf_mods), {}, set(), Notice(
            "info", "curseforge_bulk_fallback",
            "CurseForge bulk update-check was unavailable — fell back to per-mod checks (results are complete).")
```

- [ ] **Step 5: Give `_check` the CF installed set**

In `ModpackManager/modpack_manager/updates.py`, replace `_check`'s signature and its two `build_candidate` calls so each builder gets its platform-appropriate installed set (Modrinth keeps `current_project_ids`; CF gets `installed_cf_mod_ids`):

```python
def _check(module, config, current_project_ids, installed_cf_mod_ids, cf_ctx=None) -> Candidate | None:
    try:
        if module.platform == "modrinth":
            return modrinth.build_candidate(
                module, config.mc_version, config.loader, current_project_ids,
                api_key=config.modrinth_api_key)
        return curseforge.build_candidate(
            module, config.mc_version, config.loader, installed_cf_mod_ids,
            api_key=config.curseforge_api_key, ctx=cf_ctx)
    except Exception as e:  # isolate per-mod failures
        return Candidate(
            mod_id=module.mod_id, name=module.name, platform=module.platform,
            source_url=module.url, current_version=module.version or "unknown",
            latest_version="?", severity="unknown", side=module.side,
            required=module.required, mod_type=module.mod_type,
            status="error", note=str(e))
```

- [ ] **Step 6: Capture + pass the set in `scan`**

In `ModpackManager/modpack_manager/updates.py`, in `scan`, update the prefilter unpack and the `_check` submit (leave the `_resolve_dependencies(results, config)` call unchanged for now — Task 6 owns it):

```python
    # the two bulk prefilters are independent network round-trips -> run concurrently
    with ThreadPoolExecutor(max_workers=2) as pre:
        cf_future = pre.submit(_curseforge_to_check, cf_mods, config)
        mr_future = pre.submit(_modrinth_to_check, modrinth_mods, config)
        cf_to_check, cf_contexts, cf_installed_ids, cf_notice = cf_future.result()
        modrinth_to_check, mr_notice = mr_future.result()
    to_check = modrinth_to_check + cf_to_check

    results: list[Candidate] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check, m, config, current_project_ids, cf_installed_ids,
                             cf_contexts.get(m.mod_id)): m
                   for m in to_check}
        for fut in as_completed(futures):
            candidate = fut.result()
            if candidate is not None:
                results.append(candidate)
    results.sort(key=lambda c: (_STATUS_ORDER.get(c.status, 9),
                                _SEVERITY_ORDER.get(c.severity, 9), c.name.lower()))
    dep_notice = _resolve_dependencies(results, config)
    warnings = [n for n in (mr_notice, cf_notice, dep_notice) if n]
    return ScanResult(results, warnings)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS (full suite). The CF installed set is now threaded to detection but `_resolve_dependencies` is still the old Modrinth-only single pass.

- [ ] **Step 8: Commit**

```bash
git add ModpackManager/modpack_manager/sources/curseforge.py ModpackManager/modpack_manager/updates.py ModpackManager/tests/test_curseforge.py ModpackManager/tests/test_updates.py
git commit -m "feat: thread installed CurseForge modIds from bulk prefilter to detection"
```

---

## Task 6: `updates._resolve_dependencies` — bounded two-platform transitive fixpoint

Rewrite the single Modrinth-only pass into a bounded (depth `MAX_DEPTH`) fixpoint that resolves both platforms, chases each dep's own `requires` into the next frontier over a shared memo (so a shared subtree is fetched once), then flattens each candidate's transitive closure onto its `added_dependencies`. This is the only file whose control flow materially changes.

**Files:**
- Modify: `ModpackManager/modpack_manager/updates.py` (add `MAX_DEPTH` + 4 helpers; replace `_resolve_dependencies`; import `AddedDependency`; pass installed sets from `scan`)
- Test: `ModpackManager/tests/test_updates.py`

- [ ] **Step 1: Write the failing tests (transitivity, memo, cycle, depth cap)**

Append to `ModpackManager/tests/test_updates.py`:

```python
def test_resolve_dependencies_transitive_closure_and_memo(monkeypatch):
    # candidate -> A (required), A -> B (required), B not installed.
    # Two candidates share A, so the memo must fetch A once and B once.
    from modpack_manager.sources.base import AddedDependency
    c1 = _cand("cbc", "minor"); c1.added_dependencies = [AddedDependency(id="A", satisfied=False)]
    c2 = _cand("guns", "minor"); c2.added_dependencies = [AddedDependency(id="A", satisfied=False)]

    calls = []
    def fake_resolve(ids, mc, loader, key):
        calls.append(sorted(ids))
        table = {
            "A": {"name": "Arch", "slug": "arch", "side": "BOTH", "version": "1",
                  "download_url": "u", "size": 1, "addable": True, "requires": ["B"]},
            "B": {"name": "Bee", "slug": "bee", "side": "BOTH", "version": "2",
                  "download_url": "u2", "size": 2, "addable": True, "requires": []},
        }
        return {pid: table[pid] for pid in ids if pid in table}

    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", fake_resolve)
    from modpack_manager.config import Config
    notice = updates._resolve_dependencies([c1, c2], Config())
    assert notice is None
    for c in (c1, c2):
        assert {d.id for d in c.added_dependencies} == {"A", "B"}       # flattened closure
        assert {d.slug for d in c.added_dependencies} == {"arch", "bee"}
        assert all(d.platform == "modrinth" for d in c.added_dependencies)
    assert calls == [["A"], ["B"]]     # A resolved once (shared), then B once — no re-fetch


def test_resolve_dependencies_handles_cycle(monkeypatch):
    from modpack_manager.sources.base import AddedDependency
    c = _cand("root", "minor"); c.added_dependencies = [AddedDependency(id="A", satisfied=False)]
    def fake_resolve(ids, mc, loader, key):
        table = {"A": {"slug": "a", "name": "A", "side": "BOTH", "version": "1",
                       "download_url": "u", "size": 1, "addable": True, "requires": ["B"]},
                 "B": {"slug": "b", "name": "B", "side": "BOTH", "version": "1",
                       "download_url": "u", "size": 1, "addable": True, "requires": ["A"]}}
        return {pid: table[pid] for pid in ids if pid in table}
    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", fake_resolve)
    from modpack_manager.config import Config
    notice = updates._resolve_dependencies([c], Config())
    assert notice is None                              # A<->B cycle terminates via `seen`
    assert {d.id for d in c.added_dependencies} == {"A", "B"}   # each attached exactly once


def test_resolve_dependencies_depth_cap_surfaces_overcap_dep(monkeypatch):
    from modpack_manager.sources.base import AddedDependency
    c = _cand("root", "minor"); c.added_dependencies = [AddedDependency(id="D0", satisfied=False)]
    chain = {f"D{i}": [f"D{i+1}"] for i in range(5)}   # D0->D1->D2->D3->D4->D5 (6 links)
    def fake_resolve(ids, mc, loader, key):
        return {pid: {"slug": pid.lower(), "name": pid, "side": "BOTH", "version": "1",
                      "download_url": "u", "size": 1, "addable": True,
                      "requires": chain.get(pid, [])} for pid in ids}
    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", fake_resolve)
    from modpack_manager.config import Config
    updates._resolve_dependencies([c], Config())      # MAX_DEPTH == 4
    deps = {d.id: d for d in c.added_dependencies}
    assert deps["D0"].addable is True and deps["D3"].addable is True   # within the cap
    assert "D4" in deps and deps["D4"].addable is False               # over-cap: surfaced, not addable
    assert "D5" not in deps                                            # never discovered
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_updates.py -k "transitive or cycle or depth_cap" -v`
Expected: FAIL — the current single-pass resolver ignores `requires`, so B/D-chain deps are never attached (`assert {"A"} == {"A", "B"}`).

- [ ] **Step 3: Import `AddedDependency` and add `MAX_DEPTH`**

In `ModpackManager/modpack_manager/updates.py`, extend the base import:

```python
from .sources.base import Candidate, Notice, AddedDependency
```

And add the constant next to the existing order maps (after `_STATUS_ORDER`):

```python
MAX_DEPTH = 4  # direct + 3 hops; Minecraft dependency chains are shallow, and this
               # plus the `seen` set is belt-and-suspenders against cycles.
```

- [ ] **Step 4: Add the fixpoint helpers**

In `ModpackManager/modpack_manager/updates.py`, add these four helpers directly above `_resolve_dependencies`:

```python
def _resolve_platform(platform, dep_ids, config):
    """Resolve one platform's pending dep ids in bulk. Returns (specs, failed)."""
    try:
        if platform == "modrinth":
            return (modrinth.resolve_dependencies(
                dep_ids, config.mc_version, config.loader, config.modrinth_api_key), False)
        if platform == "curseforge":
            return (curseforge.resolve_dependencies(
                dep_ids, config.mc_version, config.loader, config.curseforge_api_key), False)
        return {}, False
    except Exception:  # this platform's pass aborts; its deps stay addable=False
        return {}, True


def _apply_spec(dep, spec):
    """Copy a resolved add-spec onto an existing (direct) AddedDependency in place,
    preserving a name/url already set at detection time."""
    if dep.name is None:
        dep.name = spec.get("name")
    dep.slug = spec.get("slug", "")
    dep.side = spec.get("side", "BOTH")
    dep.version = spec.get("version", "")
    dep.download_url = spec.get("download_url", "")
    dep.size = spec.get("size")
    dep.addable = spec.get("addable", False)
    if spec.get("url"):
        dep.url = spec["url"]


def _new_dependency(platform, dep_id, spec):
    """Build a fresh AddedDependency for a transitive dep from its resolved spec,
    or a bare non-addable one if it never resolved (over-cap / failed lookup)."""
    spec = spec or {}
    url = spec.get("url", "")
    if not url and platform == "modrinth":
        url = f"https://modrinth.com/mod/{dep_id}"
    return AddedDependency(
        id=str(dep_id), satisfied=False, platform=platform,
        name=spec.get("name"), url=url, slug=spec.get("slug", ""),
        side=spec.get("side", "BOTH"), version=spec.get("version", ""),
        download_url=spec.get("download_url", ""), size=spec.get("size"),
        addable=spec.get("addable", False))


def _closure_ids(candidate, resolved, installed):
    """Every (platform, id) reachable from a candidate's direct deps via resolved
    `requires` edges, skipping installed ids and cycles. Naturally bounded: only
    resolved specs carry edges, so the walk stops at the fixpoint's frontier."""
    out, stack = set(), []
    for d in candidate.added_dependencies:
        if d.id:
            stack.append((d.platform, str(d.id)))
    while stack:
        key = stack.pop()
        platform, dep_id = key
        if key in out or dep_id in installed.get(platform, set()):
            continue
        out.add(key)
        spec = resolved.get(key)
        if spec:
            for req in spec.get("requires", []):
                stack.append((platform, str(req)))
    return out
```

- [ ] **Step 5: Replace `_resolve_dependencies` with the fixpoint**

In `ModpackManager/modpack_manager/updates.py`, replace the entire existing `_resolve_dependencies` function with:

```python
def _resolve_dependencies(results, config, current_project_ids=frozenset(),
                          installed_cf_mod_ids=frozenset()):
    """Enrich every new required dependency — direct and transitive, both platforms —
    with a queueable add-spec, and flatten each candidate's full transitive closure
    onto its `added_dependencies`. Runs a bounded fixpoint (MAX_DEPTH hops) over a
    shared memo so a subtree shared by two updates is fetched once. Best-effort: a
    platform whose resolver raises leaves its deps addable=False and yields a
    `deps_unresolved` warning; the reactive frontend behaviour is inherited."""
    installed = {"modrinth": {str(x) for x in current_project_ids},
                 "curseforge": {str(x) for x in installed_cf_mod_ids}}

    # 1) seed the frontier from every candidate's direct deps, minus installed
    frontier = set()
    for c in results:
        for d in c.added_dependencies:
            if d.id and str(d.id) not in installed.get(d.platform, set()):
                frontier.add((d.platform, str(d.id)))
    if not frontier:
        return None

    # 2) fixpoint: resolve the frontier, fold newly-required ids into the next
    resolved, seen, failed, depth = {}, set(), False, 0
    while frontier and depth < MAX_DEPTH:
        pending = {}
        for (platform, dep_id) in frontier:
            if (platform, dep_id) not in seen:
                pending.setdefault(platform, []).append(dep_id)
        seen |= frontier
        if not pending:
            break
        # resolve the (<=2) platforms concurrently, mirroring scan's prefilter
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = {ex.submit(_resolve_platform, p, ids, config): p
                    for p, ids in pending.items()}
            batches = {futs[f]: f.result() for f in as_completed(futs)}
        nxt = set()
        for platform, (specs, plat_failed) in batches.items():
            failed = failed or plat_failed
            for dep_id, spec in specs.items():
                resolved[(platform, str(dep_id))] = spec
                for req in spec.get("requires", []):
                    key = (platform, str(req))
                    if key not in seen and str(req) not in installed.get(platform, set()):
                        nxt.add(key)
        frontier = nxt
        depth += 1

    # 3) attach each candidate's flattened closure: enrich direct deps in place,
    #    append transitive ones (deduped by (platform, id), sorted for determinism)
    for c in results:
        direct = {(d.platform, str(d.id)) for d in c.added_dependencies if d.id}
        for d in c.added_dependencies:
            spec = resolved.get((d.platform, str(d.id)))
            if spec:
                _apply_spec(d, spec)
        for key in sorted(_closure_ids(c, resolved, installed) - direct):
            platform, dep_id = key
            c.added_dependencies.append(_new_dependency(platform, dep_id, resolved.get(key)))

    if failed:
        return Notice("warn", "deps_unresolved",
                      "Dependency resolution failed — some new required dependencies were not "
                      "auto-queued. Check the changelog banners and add them manually.")
    return None
```

- [ ] **Step 6: Pass the installed sets from `scan`**

In `ModpackManager/modpack_manager/updates.py`, update the `_resolve_dependencies` call in `scan` (the only remaining leftover from Task 5) to pass both installed sets:

```python
    dep_notice = _resolve_dependencies(results, config, current_project_ids, cf_installed_ids)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_updates.py -v`
Expected: PASS — the 3 new tests plus the 4 existing `_resolve_dependencies` tests. The existing tests call `_resolve_dependencies([c], Config())` (2 args → installed sets default empty) and monkeypatch `updates.modrinth.resolve_dependencies`; direct-dep enrichment is byte-for-byte the same behaviour they assert. `test_resolve_dependencies_returns_notice_on_failure` still gets its `deps_unresolved` notice via the per-platform `failed` flag.

- [ ] **Step 8: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS (entire backend suite).

- [ ] **Step 9: Commit**

```bash
git add ModpackManager/modpack_manager/updates.py ModpackManager/tests/test_updates.py
git commit -m "feat: bounded two-platform transitive dependency fixpoint"
```

---

## Task 7: Frontend — platform-aware auto-dep queue

Three surgical `app.js` edits so CF and transitive deps render and generate correctly. No JS unit runner — verify by driving the app with deterministic synthetic state (no live API needed) per the `ModpackManager:verify` skill.

**Files:**
- Modify: `ModpackManager/modpack_manager/web/app.js` (`computeAutoDeps`, `renderQueue`, `generate`)

- [ ] **Step 1: Make `computeAutoDeps` platform-aware**

In `ModpackManager/modpack_manager/web/app.js`, replace the current `computeAutoDeps` function body (dedup by `d.slug`) with a `${platform}:${slug}` key and a platform-aware manual-skip. Replace this:

```javascript
function computeAutoDeps() {
  const bySlug = new Map();
  for (const c of state.candidates) {
    if (!state.selected.has(c.mod_id)) continue;
    for (const d of (c.added_dependencies || [])) {
      if (!d.addable || !d.slug) continue;
      if (state.adds.some((a) => a.module_id === d.slug)) continue;
      const e = bySlug.get(d.slug) || { dep: d, requiredBy: [] };
      if (!e.requiredBy.includes(c.name)) e.requiredBy.push(c.name);
      bySlug.set(d.slug, e);
    }
  }
  return [...bySlug.values()];
}
```

with:

```javascript
function computeAutoDeps() {
  const byKey = new Map();
  for (const c of state.candidates) {
    if (!state.selected.has(c.mod_id)) continue;
    for (const d of (c.added_dependencies || [])) {
      if (!d.addable || !d.slug) continue;
      const platform = d.platform || "modrinth";
      // a dep already queued manually (same platform + slug) wins — skip it
      if (state.adds.some((a) => a.platform === platform && a.module_id === d.slug)) continue;
      const key = `${platform}:${d.slug}`;
      const e = byKey.get(key) || { dep: d, requiredBy: [] };
      if (!e.requiredBy.includes(c.name)) e.requiredBy.push(c.name);
      byKey.set(key, e);
    }
  }
  return [...byKey.values()];
}
```

- [ ] **Step 2: Give auto-dep rows a real CF/MR pill**

In `renderQueue`, replace the auto-dep row block. Replace this:

```javascript
  for (const { dep, requiredBy } of auto) {
    const row = document.createElement("div"); row.className = "add-row auto-dep";
    const chips = requiredBy.map((n) => `<span class="dep-chip">dep of ${esc(n)}</span>`).join("");
    row.innerHTML = `<span class="tag">MR</span>
      <div class="main"><div class="name">${esc(dep.name || dep.slug)}</div>
        <div class="dep-chips">${chips}</div></div>
      <span class="ver">${esc(dep.version)}</span>${openLink(dep.url)}`;
    box.append(row);
  }
```

with:

```javascript
  for (const { dep, requiredBy } of auto) {
    const row = document.createElement("div"); row.className = "add-row auto-dep";
    const chips = requiredBy.map((n) => `<span class="dep-chip">dep of ${esc(n)}</span>`).join("");
    const pill = dep.platform === "curseforge" ? "CF" : "MR";
    row.innerHTML = `<span class="tag">${pill}</span>
      <div class="main"><div class="name">${esc(dep.name || dep.slug)}</div>
        <div class="dep-chips">${chips}</div></div>
      <span class="ver">${esc(dep.version)}</span>${openLink(dep.url)}`;
    box.append(row);
  }
```

- [ ] **Step 3: Emit the dep's real platform in `generate`**

In `generate`, replace the `autoAdds` mapping. Replace this:

```javascript
  const autoAdds = computeAutoDeps().map(({ dep }) => ({
    platform: "modrinth", module_id: dep.slug, name: dep.name, version: dep.version,
    url: dep.download_url, side: dep.side, required: true }));
```

with:

```javascript
  const autoAdds = computeAutoDeps().map(({ dep }) => ({
    platform: dep.platform || "modrinth", module_id: dep.slug, name: dep.name, version: dep.version,
    url: dep.download_url, side: dep.side, required: true }));
```

- [ ] **Step 4: Verify in the running app (synthetic state — no live API)**

Follow the `ModpackManager:verify` skill. Launch the app in the background:

```bash
.venv/Scripts/python -m modpack_manager
```

Open it in the browser pane (`preview_start` `http://127.0.0.1:5178/`), then use `javascript_tool` to inject deterministic state and assert the pill + payload:

```javascript
// 1) a selected update carrying one CF auto-dep
state.candidates = [{ mod_id: "m1", name: "Some CF Mod", status: "ok",
  added_dependencies: [{ id: "306612", platform: "curseforge", slug: "cloth-config",
    name: "Cloth Config API", version: "15.0.140", side: "BOTH", addable: true,
    download_url: "https://edge.forgecdn.net/8001/cloth.jar", url: "https://cf/cloth" }] }];
state.selected = new Set(["m1"]); state.adds = []; state.pack = [];
renderQueue();
// EXPECT: the auto-dep row's pill reads "CF"
document.querySelector("#add-queue .auto-dep .tag").textContent;   // => "CF"

// 2) generate payload carries platform:"curseforge" (stub fetch — never really POST)
let captured = null;
const realFetch = window.fetch;
window.fetch = (url, opts) => {
  if (String(url).includes("/api/generate")) { captured = JSON.parse(opts.body);
    return Promise.resolve(new Response('{"written_file":null}', { status: 200 })); }
  return realFetch(url, opts);
};
await generate();
window.fetch = realFetch;   // restore
captured.adds.find((a) => a.module_id === "cloth-config").platform;   // => "curseforge"
```

Confirm both expectations (`"CF"` and `"curseforge"`). Then kill the background server (it holds port 5178).

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/web/app.js
git commit -m "feat: platform-aware auto-dependency queue (CF pill + platform passthrough)"
```

---

## Task 8: Frontend — cross-platform "already in pack" name guard

The design's headline hazard (§2.1/§9): dependency arrays never cross platforms, but pack membership does (e.g. Architectury installed from **CF**, required as a **Modrinth** project id the CF entry can't satisfy by id). There is no shared identifier to reconcile by, so add the cheap v1 mitigation — skip an auto-dep whose display name already matches a pack entry (case-insensitive). `state.pack` is eagerly loaded at startup (`loadPack()`), and its entries expose `name` (not slug), so the guard matches on name.

**Files:**
- Modify: `ModpackManager/modpack_manager/web/app.js` (`computeAutoDeps`)

- [ ] **Step 1: Add the name guard to `computeAutoDeps`**

In `computeAutoDeps` (as rewritten in Task 7), add the guard immediately after the `const platform = ...` line and before the manual-skip. The loop body becomes:

```javascript
    for (const d of (c.added_dependencies || [])) {
      if (!d.addable || !d.slug) continue;
      const platform = d.platform || "modrinth";
      // cross-platform "already in pack" guard: the dep arrays never cross platforms,
      // but pack membership does (e.g. Architectury installed from CF, required as a
      // Modrinth project). We can't reconcile by id across registries, so skip a dep
      // whose display name already matches a pack entry (case-insensitive). state.pack
      // is loaded eagerly; if it hasn't arrived yet the guard is a self-correcting no-op.
      const depName = (d.name || d.slug || "").toLowerCase();
      if (depName && state.pack.some((m) => m.name.toLowerCase() === depName)) continue;
      // a dep already queued manually (same platform + slug) wins — skip it
      if (state.adds.some((a) => a.platform === platform && a.module_id === d.slug)) continue;
      const key = `${platform}:${d.slug}`;
      const e = byKey.get(key) || { dep: d, requiredBy: [] };
      if (!e.requiredBy.includes(c.name)) e.requiredBy.push(c.name);
      byKey.set(key, e);
    }
```

- [ ] **Step 2: Verify in the running app (synthetic state)**

Launch the app (`ModpackManager:verify` skill), open the browser pane, and via `javascript_tool`:

```javascript
// pack already ships "Cloth Config API" (from CF); a Modrinth update requires the
// Modrinth copy under the same display name -> must be skipped (not queued).
state.pack = [{ mod_id: "cloth", name: "Cloth Config API", version: "15.0.140",
                platform: "curseforge", side: "BOTH" }];
state.candidates = [{ mod_id: "m1", name: "Some MR Mod", status: "ok",
  added_dependencies: [{ id: "DEP", platform: "modrinth", slug: "cloth-config",
    name: "Cloth Config API", version: "15.0.140", side: "BOTH", addable: true,
    download_url: "https://cdn/cc.jar", url: "https://modrinth.com/mod/DEP" }] }];
state.selected = new Set(["m1"]); state.adds = [];
computeAutoDeps().length;   // => 0  (guarded out — already in pack under this name)

// control: with an empty pack the same dep IS queued
state.pack = [];
computeAutoDeps().length;   // => 1
```

Confirm `0` then `1`. Kill the background server.

- [ ] **Step 3: Commit**

```bash
git add ModpackManager/modpack_manager/web/app.js
git commit -m "feat: cross-platform already-in-pack name guard for auto-deps"
```

---

## Task 9: End-to-end verification against the running app

Backend correctness is proven by the unit suite; the frontend edits are proven by the synthetic-state checks in Tasks 7–8. This final task is the design's §10 acceptance check at the real surface. It needs the live app and a working CurseForge API key (Modrinth works anonymously); if no CF key is available in the environment, record that and rely on the per-task verification above.

**Files:** none (verification only).

- [ ] **Step 1: Launch and scan**

Use the `ModpackManager:verify` skill. Launch in the background:

```bash
.venv/Scripts/python -m modpack_manager
```

Fetch the scan JSON (first call runs a ~30s live scan, then caches):

```bash
curl -s "http://127.0.0.1:5178/api/updates" > scan.json
```

- [ ] **Step 2: Confirm the backend now populates CF + transitive deps**

Inspect `scan.json` (e.g. with `python -c` or `jq`): find at least one `platform:"curseforge"` candidate whose `added_dependencies` is non-empty, and confirm entries carry `platform`, `addable`, `slug`, `download_url`, `version`. Confirm a Modrinth candidate whose closure includes a dep-of-a-dep (an `added_dependencies` entry not present in that mod's first-hop `dependencies`). Confirm any distribution-blocked CF dep shows `addable:false` with a resolved `name`.

Expected: CF candidates carry dependency entries (previously always `[]`); Modrinth closures can be >1 hop deep.

- [ ] **Step 3: Confirm the frontend surfaces them**

Open the app in the browser pane. In the Updates tab, pick the CF update from Step 2 and confirm its changelog reader shows the `⚠ New required dependency: …` banner. In the Add tab's "Queued to add", confirm the auto-dep row shows the correct **CF**/**MR** pill and a `dep of <RootUpdate>` chip. Deselect the root update → its whole subtree drops from the queue; re-select → it returns with **no** network call (watch the network panel). A distribution-blocked CF dep shows the "add it manually" banner and is **not** queued.

- [ ] **Step 4: Confirm generate would write the deps (without actually generating)**

Per the skill's destructive-`/api/generate` caveat, do **not** click Generate. Stub `window.fetch` to capture the `/api/generate` body (as in Task 7 Step 4) and confirm the queued CF/transitive deps appear in `payload.adds` with their real `platform` and a valid `url`. Restore `fetch`.

- [ ] **Step 5: Clean up**

Kill the background server (frees port 5178). Delete the scratch `scan.json`.

- [ ] **Step 6 (optional): Full suite one more time**

```bash
.venv/Scripts/python -m pytest -q
```

Expected: PASS.

---

## Appendix: Spec coverage map

| Spec section | Task(s) |
|---|---|
| §5.1 `AddedDependency.platform` | 1 |
| §7.3 Modrinth resolver surfaces `requires` | 2 |
| §7.1 `curseforge.resolve_dependencies` (+ blocked/no-key) | 3 |
| §7.2 CF `build_candidate` detection | 4 |
| §7.5 thread `installed_cf_mod_ids` | 5 |
| §7.4 bounded two-platform transitive fixpoint, `MAX_DEPTH=4` | 6 |
| §5.3 flatten closure onto requiring candidate | 6 |
| §8 frontend pill / platform passthrough / dedup key | 7 |
| §2.1 & §9 cross-platform name guard | 8 |
| §9 blocked CF dep → detected, addable=False, "add manually" | 3, 4, 9 |
| §9 cycle guard (`seen`) + depth cap | 6 |
| §9 shared subtree fetched once (memo) | 6 |
| §9 CF resolver fails mid-scan → per-platform isolation + notice | 6 |
| §3 no change to generate/write | (verified — service.py ignores `platform`) |
| §10 backend unit tests | 1–6 |
| §10 end-to-end app verification | 7, 8, 9 |

**Deferred to v2 (not in this plan, per spec §11):** true cross-platform identity resolution, optional-dependency prompts, CF per-dep side detection, dependency-chain/tree chips, per-row version override.
