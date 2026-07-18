# Dependency Auto-Add Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a mod update introduces a new required dependency, automatically queue the latest compatible version of that dependency in the Add tab's "Queued to add" section, each with a chip naming the mod(s) it's a new dependency for.

**Architecture:** The scan (backend) resolves each newly-detected dependency into a full add-spec (slug, latest version, download URL, side, size) and stores it on the `Candidate`. The frontend derives the auto-queue from the *currently selected* updates, deduped by slug with one chip per requiring mod — so deselecting an update drops its dep and re-selecting restores it from the in-memory cache with no re-fetch. Modrinth-scoped (the only source that detects new deps today).

**Tech Stack:** Python 3.10+, Flask, `requests`, `pytest` + `responses` (HTTP mocking); vanilla HTML/CSS/JS frontend (no build, no JS test runner).

**Spec:** [docs/superpowers/specs/2026-07-18-dependency-auto-add-design.md](../specs/2026-07-18-dependency-auto-add-design.md)

**Working directory for all commands:** `H:/repos/Gears-Frontiers/ModpackManager`
**Test runner:** `.venv/Scripts/python -m pytest`

---

## File Structure

- `modpack_manager/sources/base.py` — **Modify.** Extend the `AddedDependency` dataclass with the add-spec fields.
- `modpack_manager/sources/modrinth.py` — **Modify.** Replace `resolve_project_names` with a richer `resolve_dependencies` that returns queueable specs.
- `modpack_manager/updates.py` — **Modify.** Rename/rewrite `_resolve_dependency_names` → `_resolve_dependencies` (enrichment pass) and update the `scan()` call site.
- `modpack_manager/web/app.js` — **Modify.** Derive auto-deps (`computeAutoDeps`), render them in the queue with chips, include them in the batch count / generate payload / review panel, wire live recompute into selection changes, and update the changelog banner text.
- `modpack_manager/web/style.css` — **Modify.** Add `.dep-chip` / `.dep-chips` / `.add-row.auto-dep` styles.
- `tests/test_sources_base.py` — **Modify.** Assert the new `AddedDependency` fields default and round-trip.
- `tests/test_modrinth.py` — **Modify.** Replace the `resolve_project_names` test with `resolve_dependencies` tests.
- `tests/test_updates.py` — **Modify.** Test the enrichment pass maps specs onto the right candidate and is a no-op without deps.

---

## Task 1: Extend `AddedDependency` with add-spec fields

**Files:**
- Modify: `modpack_manager/sources/base.py:13-18`
- Test: `tests/test_sources_base.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_sources_base.py`:

```python
def test_added_dependency_new_fields_default_and_roundtrip():
    from modpack_manager.sources.base import Candidate, AddedDependency
    dep = AddedDependency(id="cloth-config", satisfied=False)
    # new fields default to a not-yet-resolved, not-addable spec
    assert dep.slug == ""
    assert dep.side == "BOTH"
    assert dep.version == ""
    assert dep.download_url == ""
    assert dep.size is None
    assert dep.addable is False
    # populated fields survive Candidate.to_dict() (asdict) nesting
    dep2 = AddedDependency(id="create", satisfied=False, name="Create", slug="create",
                           side="CLIENT", version="6.0.6",
                           download_url="https://cdn/create.jar", size=1234, addable=True)
    c = Candidate(mod_id="cbc", name="CBC", platform="modrinth", source_url="u",
                  current_version="1", latest_version="2", severity="minor", side="BOTH",
                  required=True, mod_type="Regular", added_dependencies=[dep2], status="ok")
    d = c.to_dict()["added_dependencies"][0]
    assert d["slug"] == "create"
    assert d["side"] == "CLIENT"
    assert d["version"] == "6.0.6"
    assert d["download_url"] == "https://cdn/create.jar"
    assert d["size"] == 1234
    assert d["addable"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_sources_base.py::test_added_dependency_new_fields_default_and_roundtrip -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'slug'`.

- [ ] **Step 3: Add the fields to the dataclass**

In `modpack_manager/sources/base.py`, replace the `AddedDependency` dataclass:

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
```

- [ ] **Step 4: Run the base tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_sources_base.py -v`
Expected: PASS (both the new test and the existing `test_candidate_to_dict_roundtrips_nested`, which uses positional `AddedDependency("morered", False)` — still valid since the new fields have defaults).

- [ ] **Step 5: Commit**

```bash
git add modpack_manager/sources/base.py tests/test_sources_base.py
git commit -m "feat: extend AddedDependency with add-spec fields"
```

---

## Task 2: `modrinth.resolve_dependencies` (replace `resolve_project_names`)

**Files:**
- Modify: `modpack_manager/sources/modrinth.py:150-163` (remove `resolve_project_names`, add `resolve_dependencies`)
- Modify: `modpack_manager/sources/modrinth.py:1-9` (add `ThreadPoolExecutor` import)
- Test: `tests/test_modrinth.py:106-115` (remove old test) + new tests

**Context:** Reuse the existing module helpers — `_session`, `_chunk`, `_fetch_versions`, `_primary_file`, `_detect_side` — all already defined in `modrinth.py`. `_fetch_versions` already filters by `game_versions`/`loaders`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_modrinth.py`, **delete** `test_resolve_project_names_maps_id_and_slug_to_title` (lines 106-115) and add:

```python
@responses.activate
def test_resolve_dependencies_builds_addable_spec():
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "DEP0001", "slug": "cloth-config", "title": "Cloth Config API",
         "client_side": "required", "server_side": "required"},
    ], status=200)
    responses.add(responses.GET, f"{API}/project/DEP0001/version", json=[
        {"id": "CCV2", "version_number": "15.0.140",
         "date_published": "2026-07-10T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn.modrinth.com/cc.jar", "size": 4242}]},
        {"id": "CCV1", "version_number": "15.0.100",
         "date_published": "2026-06-01T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn.modrinth.com/cc-old.jar", "size": 4000}]},
    ], status=200)
    out = modrinth.resolve_dependencies(["DEP0001"], "1.21.1", "neoforge")
    spec = out["DEP0001"]
    assert spec["name"] == "Cloth Config API"
    assert spec["slug"] == "cloth-config"
    assert spec["side"] == "BOTH"
    assert spec["version"] == "15.0.140"          # newest by date
    assert spec["download_url"] == "https://cdn.modrinth.com/cc.jar"
    assert spec["size"] == 4242
    assert spec["addable"] is True


@responses.activate
def test_resolve_dependencies_detects_client_side():
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "DEP3", "slug": "clientmod", "title": "Client Mod",
         "client_side": "required", "server_side": "unsupported"}], status=200)
    responses.add(responses.GET, f"{API}/project/DEP3/version", json=[
        {"id": "V", "version_number": "1.0", "date_published": "2026-07-10T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/c.jar", "size": 1}]}], status=200)
    out = modrinth.resolve_dependencies(["DEP3"], "1.21.1", "neoforge")
    assert out["DEP3"]["side"] == "CLIENT"
    assert out["DEP3"]["addable"] is True


@responses.activate
def test_resolve_dependencies_no_compatible_version_not_addable():
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "DEP2", "slug": "somelib", "title": "Some Lib",
         "client_side": "required", "server_side": "required"}], status=200)
    responses.add(responses.GET, f"{API}/project/DEP2/version", json=[], status=200)
    out = modrinth.resolve_dependencies(["DEP2"], "1.21.1", "neoforge")
    spec = out["DEP2"]
    assert spec["name"] == "Some Lib"      # meta still resolved
    assert spec["slug"] == "somelib"
    assert spec["download_url"] == ""
    assert spec["addable"] is False


@responses.activate
def test_resolve_dependencies_meta_failure_not_addable():
    responses.add(responses.GET, f"{API}/projects", status=500)
    responses.add(responses.GET, f"{API}/project/DEP4/version", json=[
        {"id": "V", "version_number": "1.0", "date_published": "2026-07-10T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/d.jar", "size": 1}]}], status=200)
    out = modrinth.resolve_dependencies(["DEP4"], "1.21.1", "neoforge")
    spec = out["DEP4"]
    assert spec["name"] is None            # no meta -> no name
    assert spec["slug"] == ""
    assert spec["addable"] is False        # can't queue without a slug
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py -k resolve_dependencies -v`
Expected: FAIL with `AttributeError: module 'modpack_manager.sources.modrinth' has no attribute 'resolve_dependencies'`.

- [ ] **Step 3: Add the `ThreadPoolExecutor` import**

In `modpack_manager/sources/modrinth.py`, add to the imports at the top (after `import re`):

```python
from concurrent.futures import ThreadPoolExecutor
```

- [ ] **Step 4: Replace `resolve_project_names` with `resolve_dependencies`**

In `modpack_manager/sources/modrinth.py`, delete the whole `resolve_project_names` function (lines 150-163) and put this in its place:

```python
def resolve_dependencies(dep_ids, mc_version, loader, api_key=""):
    """Resolve new-dependency project ids into queueable add-specs.

    Returns {dep_id: {name, slug, side, version, download_url, size, addable}}.
    Best-effort: any dep we can't fully resolve comes back addable=False (with
    whatever fields did resolve), so the UI still shows the warning but doesn't
    auto-queue it.
    """
    dep_ids = list(dict.fromkeys(d for d in dep_ids if d))  # de-dupe, keep order
    if not dep_ids:
        return {}
    session = _session(api_key)

    # 1) bulk project meta: id -> {name, slug, side}
    meta = {}
    try:
        for chunk in _chunk(dep_ids):
            r = session.get(f"{API}/projects", params={"ids": json.dumps(chunk)}, timeout=30)
            r.raise_for_status()
            for proj in r.json():
                pid = proj.get("id")
                if pid:
                    meta[pid] = {"name": proj.get("title") or proj.get("slug") or pid,
                                 "slug": proj.get("slug") or "",
                                 "side": _detect_side(proj)}
    except Exception:  # bulk meta failed -> deps stay non-addable (no slug/side)
        meta = {}

    # 2) latest compatible version per dep (concurrent, failure-isolated)
    def _latest(pid):
        try:
            versions = _fetch_versions(session, pid, mc_version, loader)
        except Exception:
            return pid, None
        if not versions:
            return pid, None
        versions.sort(key=lambda v: v.get("date_published", ""), reverse=True)
        pf = _primary_file(versions[0])
        return pid, {"version": versions[0].get("version_number", "?"),
                     "download_url": pf.get("url", ""), "size": pf.get("size")}

    with ThreadPoolExecutor(max_workers=5) as ex:
        latest_by_id = dict(ex.map(_latest, dep_ids))

    # 3) combine; addable requires both a slug (module_id) and a download url
    out = {}
    for pid in dep_ids:
        m = meta.get(pid, {})
        v = latest_by_id.get(pid) or {}
        download_url = v.get("download_url", "")
        out[pid] = {"name": m.get("name"), "slug": m.get("slug", ""),
                    "side": m.get("side", "BOTH"), "version": v.get("version", ""),
                    "download_url": download_url, "size": v.get("size"),
                    "addable": bool(m.get("slug")) and bool(download_url)}
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py -v`
Expected: PASS (the four new `resolve_dependencies` tests plus all the pre-existing modrinth tests).

- [ ] **Step 6: Commit**

```bash
git add modpack_manager/sources/modrinth.py tests/test_modrinth.py
git commit -m "feat: modrinth.resolve_dependencies returns queueable dep specs"
```

---

## Task 3: `updates._resolve_dependencies` enrichment pass

**Files:**
- Modify: `modpack_manager/updates.py:90` (call site) and `:94-109` (the function)
- Test: `tests/test_updates.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_updates.py`:

```python
def _cand_with_dep(mod_id, dep_id):
    from modpack_manager.sources.base import AddedDependency
    c = _cand(mod_id, "minor")
    c.added_dependencies = [AddedDependency(id=dep_id, satisfied=False)]
    return c


def test_resolve_dependencies_enriches_candidate(monkeypatch):
    c = _cand_with_dep("createbigcannons", "DEP1")

    def fake_resolve(ids, mc, loader, key):
        assert list(ids) == ["DEP1"]
        return {"DEP1": {"name": "Create", "slug": "create", "side": "BOTH",
                         "version": "6.0.6", "download_url": "https://cdn/create.jar",
                         "size": 1234, "addable": True}}

    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", fake_resolve)
    from modpack_manager.config import Config
    updates._resolve_dependencies([c], Config())
    d = c.added_dependencies[0]
    assert d.name == "Create"
    assert d.slug == "create"
    assert d.side == "BOTH"
    assert d.version == "6.0.6"
    assert d.download_url == "https://cdn/create.jar"
    assert d.size == 1234
    assert d.addable is True


def test_resolve_dependencies_noop_without_deps(monkeypatch):
    called = []
    monkeypatch.setattr(updates.modrinth, "resolve_dependencies",
                        lambda *a, **k: called.append(1) or {})
    from modpack_manager.config import Config
    updates._resolve_dependencies([_cand("plain")], Config())  # candidate with no deps
    assert called == []                                        # no network pass triggered
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_updates.py -k resolve_dependencies -v`
Expected: FAIL with `AttributeError: module 'modpack_manager.updates' has no attribute '_resolve_dependencies'`.

- [ ] **Step 3: Replace the function and the call site**

In `modpack_manager/updates.py`, change the call site at line 90 inside `scan()`:

```python
    _resolve_dependencies(results, config)
```

Then replace the whole `_resolve_dependency_names` function (lines 94-109) with:

```python
def _resolve_dependencies(results, config):
    """Enrich each new (unsatisfied) dependency with a queueable add-spec: name,
    slug, side, latest compatible version + download url + size, and an `addable`
    flag. One bulk pass over all Modrinth candidates. Best-effort — a dep we
    can't resolve stays addable=False and the UI keeps showing the warning
    without auto-queuing it."""
    dep_ids = {d.id for c in results if c.platform == "modrinth"
               for d in c.added_dependencies if d.id}
    if not dep_ids:
        return
    try:
        specs = modrinth.resolve_dependencies(
            list(dep_ids), config.mc_version, config.loader, config.modrinth_api_key)
    except Exception:
        return
    for c in results:
        for d in c.added_dependencies:
            spec = specs.get(d.id)
            if not spec:
                continue
            if d.name is None:
                d.name = spec.get("name")
            d.slug = spec.get("slug", "")
            d.side = spec.get("side", "BOTH")
            d.version = spec.get("version", "")
            d.download_url = spec.get("download_url", "")
            d.size = spec.get("size")
            d.addable = spec.get("addable", False)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_updates.py -v`
Expected: PASS (new enrichment tests + existing scan tests).

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS — all tests green. This confirms removing `resolve_project_names` broke nothing (its only caller and its test are gone).

- [ ] **Step 6: Commit**

```bash
git add modpack_manager/updates.py tests/test_updates.py
git commit -m "feat: enrich new dependencies into add-specs during scan"
```

---

## Task 4: Frontend — derive, render (with chips), count, generate, review

**Files:**
- Modify: `modpack_manager/web/style.css` (append chip styles)
- Modify: `modpack_manager/web/app.js` — add `computeAutoDeps`; update `renderQueue`, `batchCounts`, `generate`, `openReview`

**Context:** `esc` and `openLink` helpers exist at the top of `app.js`. `state` has `candidates`, `selected` (Set of mod_ids), `adds` (manual add specs, each with `module_id`), and `pack` (loaded eagerly at startup). The queue container is `#add-queue`; its count is `#add-queue-count`.

- [ ] **Step 1: Add chip styles**

Append to `modpack_manager/web/style.css`:

```css
.dep-chip { font-size:.58rem; font-weight:600; padding:1px 7px; border-radius:100px;
  background:rgba(255,159,10,.16); color:var(--minor); white-space:nowrap; }
.dep-chips { display:flex; flex-wrap:wrap; gap:4px; margin-top:3px; }
.add-row.auto-dep { border-left:2px solid var(--minor); }
```

- [ ] **Step 2: Add the `computeAutoDeps` helper**

In `modpack_manager/web/app.js`, add this function just above `renderQueue` (near line 137):

```javascript
// Derived: new deps of currently-selected updates, deduped by slug, one entry
// per dep with the names of every selected mod that introduced it. Skips deps
// that aren't addable, are already queued manually, or are already in the pack.
function computeAutoDeps() {
  const bySlug = new Map();
  for (const c of state.candidates) {
    if (!state.selected.has(c.mod_id)) continue;
    for (const d of (c.added_dependencies || [])) {
      if (!d.addable || !d.slug) continue;
      if (state.adds.some((a) => a.module_id === d.slug)) continue;
      if (state.pack.some((m) => m.mod_id === d.slug)) continue;
      const e = bySlug.get(d.slug) || { dep: d, requiredBy: [] };
      if (!e.requiredBy.includes(c.name)) e.requiredBy.push(c.name);
      bySlug.set(d.slug, e);
    }
  }
  return [...bySlug.values()];
}
```

- [ ] **Step 3: Render auto-deps in the queue (with chips, no ✕)**

In `modpack_manager/web/app.js`, replace the whole `renderQueue` function (lines 137-151):

```javascript
function renderQueue() {
  const box = $("#add-queue"); box.innerHTML = "";
  const auto = computeAutoDeps();
  for (const { dep, requiredBy } of auto) {
    const row = document.createElement("div"); row.className = "add-row auto-dep";
    const chips = requiredBy.map((n) => `<span class="dep-chip">dep of ${esc(n)}</span>`).join("");
    row.innerHTML = `<span class="tag">MR</span>
      <div class="main"><div class="name">${esc(dep.name || dep.slug)}</div>
        <div class="dep-chips">${chips}</div></div>
      <span class="ver">${esc(dep.version)}</span>${openLink(dep.url)}`;
    box.append(row);
  }
  for (const a of state.adds) {
    const row = document.createElement("div"); row.className = "add-row";
    row.innerHTML = `<span class="tag">${a.platform === "curseforge" ? "CF" : "MR"}</span>
      <div class="main"><div class="name">${esc(a.name)}</div></div>
      <span class="ver">${esc(a.version)}</span>${openLink(a.page_url)}
      <button class="rm-btn">✕</button>`;
    row.querySelector(".rm-btn").addEventListener("click", () => {
      state.adds = state.adds.filter((x) => x !== a); renderQueue(); updateBatch();
    });
    box.append(row);
  }
  $("#add-queue-count").textContent = auto.length + state.adds.length;
}
```

- [ ] **Step 4: Count auto-deps in the batch summary**

In `modpack_manager/web/app.js`, replace `batchCounts` (line 184):

```javascript
function batchCounts() {
  return { u: state.selected.size, a: state.adds.length + computeAutoDeps().length,
           r: state.removals.size };
}
```

- [ ] **Step 5: Include auto-deps in the generate payload**

In `modpack_manager/web/app.js`, in `generate()` (line 212), replace the `payload` line:

```javascript
  const autoAdds = computeAutoDeps().map(({ dep }) => ({
    platform: "modrinth", module_id: dep.slug, name: dep.name, version: dep.version,
    url: dep.download_url, side: dep.side, required: true }));
  const payload = { updates: [...state.selected],
    adds: [...state.adds.map(({ page_url, ...a }) => a), ...autoAdds],
    removals: [...state.removals] };
```

- [ ] **Step 6: Show auto-deps in the Review panel (Adds section, no remove control)**

In `modpack_manager/web/app.js`, in `openReview()` (line 189), replace the `body.innerHTML = …` assignment block (lines 195-199) with:

```javascript
  const autoAdds = computeAutoDeps().map(({ dep, requiredBy }) =>
    ({ name: dep.name || dep.slug, version: dep.version, auto: true, requiredBy }));
  const addsForReview = [...state.adds, ...autoAdds];
  body.innerHTML =
    sec("Updates", upd, (c) => `<div class="review-item">${esc(c.name)} <span class="muted">${esc(c.current_version)} → ${esc(c.latest_version)}</span><button data-t="u" data-id="${esc(c.mod_id)}">remove</button></div>`) +
    sec("Adds", addsForReview, (a) => a.auto
      ? `<div class="review-item">+ ${esc(a.name)} <span class="muted">${esc(a.version)}</span> <span class="dep-chip">dep of ${esc(a.requiredBy.join(", "))}</span></div>`
      : `<div class="review-item">+ ${esc(a.name)} <span class="muted">${esc(a.version)}</span><button data-t="a" data-id="${esc(a.module_id)}">remove</button></div>`) +
    sec("Removals", rem, (m) => `<div class="review-item">− ${esc(m.name)}<button data-t="r" data-id="${esc(m.mod_id)}">keep</button></div>`) ||
    '<p class="muted">Nothing queued yet.</p>';
```

(The existing button handler below this block filters `state.adds` by `module_id`; auto entries render no button, so they are untouched by it.)

- [ ] **Step 7: Commit**

```bash
git add modpack_manager/web/app.js modpack_manager/web/style.css
git commit -m "feat: render auto-added deps in the queue with requiring-mod chips"
```

---

## Task 5: Frontend — live recompute on selection change + banner text

**Files:**
- Modify: `modpack_manager/web/app.js` — `toggleUpdate`, the Select-all handler, `load`, and `renderReader`

**Context:** After Task 4 the auto-queue renders from the selection present at initial `load`, but toggling an update on the Updates tab does not yet refresh it. This task makes it reactive and updates the changelog banner.

- [ ] **Step 1: Refresh the queue when a single update is toggled**

In `modpack_manager/web/app.js`, replace `toggleUpdate` (line 69):

```javascript
function toggleUpdate(id) {
  state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id);
  renderUpdates(); renderQueue(); updateBatch();
}
```

- [ ] **Step 2: Refresh the queue on Select all**

In `modpack_manager/web/app.js`, replace the `#select-all` click handler (lines 72-77):

```javascript
$("#select-all").addEventListener("click", () => {
  const vis = visible().filter((c) => c.status === "ok");
  const all = vis.every((c) => state.selected.has(c.mod_id));
  vis.forEach((c) => all ? state.selected.delete(c.mod_id) : state.selected.add(c.mod_id));
  renderUpdates(); renderQueue(); updateBatch();
});
```

- [ ] **Step 3: Seed the queue after a scan loads**

In `modpack_manager/web/app.js`, in `load()` (line 30), add `renderQueue()` after `renderUpdates()`:

```javascript
    hideLoading(); renderUpdates(); renderQueue(); updateBatch();
```

- [ ] **Step 4: Update the changelog banner text**

In `modpack_manager/web/app.js`, replace the `added_dependencies` loop in `renderReader` (line 66):

```javascript
  for (const d of c.added_dependencies) {
    const label = esc(d.name || d.id);
    const tail = d.addable
      ? ` <span class="muted">(${esc(d.version)})</span> — added to the Add queue`
      : " — not in your pack; add it manually";
    h += `<div class="dep">⚠ New required dependency: <b>${label}</b>${tail}</div>`;
  }
```

- [ ] **Step 5: Commit**

```bash
git add modpack_manager/web/app.js
git commit -m "feat: keep auto-dep queue reactive to update selection; update banner"
```

---

## Task 6: End-to-end verification (manual — no JS test harness)

**Files:** none (verification only)

- [ ] **Step 1: Launch the app**

Run (from `H:/repos/Gears-Frontiers/ModpackManager`): `powershell -ExecutionPolicy Bypass -File .\run.ps1`
Expected: the browser opens at `http://127.0.0.1:5178/`, the Updates tab scans and lists candidates.

- [ ] **Step 2: Confirm a new dependency auto-queues with the right chip**

Find an update whose changelog shows the orange "⚠ New required dependency … — added to the Add queue" banner (a Modrinth mod that gained a required dep). Switch to the **Add** tab. Verify:
- the dependency appears in **Queued to add** with an orange left border and a `dep of <ModName>` chip naming the mod that introduced it,
- the version shown matches the resolved latest, and the ↗ opens its Modrinth page,
- the footer batch summary's "adds" count includes it.

If no live update currently introduces a new dep, verify the plumbing instead: the banner renders for any historical new-dep mod, and a mod with `addable` deps appears in the queue. Note in the completion report if a live new-dep case could not be exercised.

- [ ] **Step 3: Confirm reactivity + cache-on-reselect**

On the Updates tab, **deselect** the update that introduced the dependency → the dependency disappears from the Add queue and the batch count drops. **Re-select** it → the dependency reappears immediately (no scan/spinner, no network delay), confirming the cached spec is reused.

- [ ] **Step 4: Confirm dedupe against a manual add**

With the dep auto-queued, go to Add, search the same dependency, pick a version, and click **Add**. Verify the auto-dep row is replaced by the single manual row (chip gone, ✕ present) — i.e., no duplicate entry for the same slug.

- [ ] **Step 5: Confirm Review + Generate include the dependency**

Click **Review batch** → the dependency shows under **Adds** (with its chip, no remove control). Click **Generate preview**. When it completes, confirm the written `updates/updates-YYYY-MM-DD.xml` contains a `<Module>` for the dependency with a real MD5 + Size. Then discard that generated file/preview change (`git checkout -- GearsAndFrontiers_Preview.xml` and delete the dated file) unless you intend to keep it.

- [ ] **Step 6: Stop the app**

Press Ctrl+C in the terminal running `run.ps1`.

---

## Self-Review Notes

- **Spec coverage:** §2/§5.2/§7 → Tasks 1-3 (data model, enrichment, `resolve_dependencies`). §4.1/§5.1/§8 (derive, render, chips, count, generate, review) → Task 4. §2 reactivity + cache + §4.2 banner → Task 5. §9 edge cases: unresolvable→`addable=False` (Task 2/5), multi-requirer chips (Task 4 step 2/3), manual-add & pack dedupe (Task 4 step 2), deselect/re-select cache (Task 5 + Task 6 step 3). §10 testing → Tasks 1-3 unit tests + Task 6 manual. §3 non-goals (transitive, CF, version override) → not implemented, by design.
- **Type consistency:** `AddedDependency` fields (`slug`/`side`/`version`/`download_url`/`size`/`addable`) are defined in Task 1 and consumed identically in Tasks 2 (dict keys), 3 (attribute copy), and 4/5 (JS `dep.slug`/`dep.download_url`/etc.). `computeAutoDeps()` returns `[{dep, requiredBy}]` and every consumer (renderQueue, generate, openReview, batchCounts) uses that exact shape.
- **No placeholders:** every code step contains full code; every test step includes the assertions; every run step names the command and expected result.
