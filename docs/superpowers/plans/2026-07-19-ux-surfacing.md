# UX Surfacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close three picker-UI surfacing gaps — a dedicated "Needs manual update" section, a name filter + keyboard navigation on the Updates list, and an on-demand changelog preview when adding a mod — reusing existing data, styles, and endpoints wherever the data already exists.

**Architecture:** Two of the three features are frontend-only (`web/*`): the manual section and the filter+keyboard work are pure views over data `/api/updates` already ships. The third (changelog-on-add) adds one lazy backend route `GET /api/project-changelog` delegating to a `changelog_fn` (new `create_app` DI param, wired to `service.real_project_changelog`) plus two thin source functions that reuse the existing `render_markdown` / `_changelog` helpers.

**Tech Stack:** Python 3.12, Flask, `pytest` + `responses` (HTTP mocking); vanilla-JS frontend (no build/test runner) verified with `node --check` and the `ModpackManager:verify` skill.

**Spec:** [docs/superpowers/specs/2026-07-19-ux-surfacing-design.md](../specs/2026-07-19-ux-surfacing-design.md)

**Decisions taken on the spec's open questions** (see spec §11; all cheap to change):
- **§11.1 Manual list placement** — an in-line collapsible **section** on the Updates tab, full-width between `#scan-warnings` and `.panes`, expanded by default. Manual rows are **pulled out** of the main list (not mirrored).
- **§11.2 Keyboard scheme** — the spec's full recommended set: **↑/↓ (+ j/k) move, Enter opens the active mod's page, Space toggles its selection**.
- **§11.3 Changelog-on-add** — a **new lazy `GET /api/project-changelog`**, one call per expand / version change (rejecting the eager-Modrinth-inline alternative that would force N per-file CurseForge calls).

---

## File Structure

**Modify — backend:**
- `ModpackManager/modpack_manager/sources/modrinth.py` — add `project_changelog(version_id, api_key)`.
- `ModpackManager/modpack_manager/sources/curseforge.py` — add `project_changelog(mod_id, file_id, api_key)`.
- `ModpackManager/modpack_manager/service.py` — add `real_project_changelog(platform, project_id, ref)`.
- `ModpackManager/modpack_manager/webapp.py` — `create_app` gains a `changelog_fn` param; add `GET /api/project-changelog`.
- `ModpackManager/modpack_manager/__main__.py` — import + wire `real_project_changelog` into `create_app`.

**Modify — frontend:**
- `ModpackManager/modpack_manager/web/index.html` — `#manual-updates` band; `#updates-filter` input; (add-tab preview needs no new HTML — built in JS).
- `ModpackManager/modpack_manager/web/style.css` — manual-section + add-preview styles (appended).
- `ModpackManager/modpack_manager/web/app.js` — `matchesFilters`/`manualVisible`/`renderManual`; text filter + keyboard handler; `renderResults` disclosure + `togglePreview`/`loadPreview`/`fetchChangelog`.

**Modify — tests:**
- `ModpackManager/tests/test_modrinth.py`, `tests/test_curseforge.py` — source `project_changelog` coverage.
- `ModpackManager/tests/test_service.py` — `real_project_changelog` dispatch coverage.
- `ModpackManager/tests/test_webapp.py` — `/api/project-changelog` route + thread `changelog_fn` through every `create_app` call site.

**Conventions (from the codebase):**
- Run tests from `ModpackManager/`: `.venv/Scripts/python -m pytest`. Source tests mock HTTP with `responses` ([test_modrinth.py](../../../ModpackManager/tests/test_modrinth.py)).
- Webapp uses constructor DI ([webapp.py:11](../../../ModpackManager/modpack_manager/webapp.py:11)); tests inject fakes and pass **all** collaborators by keyword.
- Source `project_changelog` returns the §6 shape `{"version","date","body_html"}`; `body_html` is server-sanitized (`render_markdown` for Modrinth, `sanitize_html` via `_changelog` for CurseForge) — the same contract `renderReader` already injects.
- Frontend has no JS runner; `node --check` guards parse errors and `ModpackManager:verify` covers runtime (Task 6).

---

## Task 1: Backend sources — `project_changelog` for Modrinth & CurseForge (TDD)

**Files:** Modify `sources/modrinth.py`, `sources/curseforge.py`. Test: `tests/test_modrinth.py`, `tests/test_curseforge.py`.

- [ ] **Step 1: Write the failing Modrinth tests** — append to `tests/test_modrinth.py`:

```python
@responses.activate
def test_project_changelog_returns_version_date_body():
    responses.add(responses.GET, f"{API}/version/V2", json={
        "id": "V2", "version_number": "0.6.0", "date_published": "2026-07-10T00:00:00Z",
        "changelog": "- added things"}, status=200)
    out = modrinth.project_changelog("V2")
    assert out["version"] == "0.6.0"
    assert out["date"] == "2026-07-10"
    assert "added things" in out["body_html"]


@responses.activate
def test_project_changelog_non_200_is_empty():
    responses.add(responses.GET, f"{API}/version/BAD", status=404)
    assert modrinth.project_changelog("BAD") == {"version": "", "date": "", "body_html": ""}
```

- [ ] **Step 2: Write the failing CurseForge tests** — append to `tests/test_curseforge.py`:

```python
@responses.activate
def test_project_changelog_wraps_file_changelog():
    responses.add(responses.GET, f"{API}/mods/999/files/7600000/changelog",
                  json={"data": "<p>Fixed the map</p>"}, status=200)
    out = curseforge.project_changelog(999, "7600000", api_key="CF")
    assert out["version"] == "" and out["date"] == ""      # CF changelog endpoint has no version/date
    assert "Fixed the map" in out["body_html"]


@responses.activate
def test_project_changelog_non_200_is_empty():
    responses.add(responses.GET, f"{API}/mods/999/files/1/changelog", status=404)
    assert curseforge.project_changelog(999, "1", api_key="CF")["body_html"] == ""


def test_project_changelog_no_key_is_empty():
    assert curseforge.project_changelog(999, "1", api_key="")["body_html"] == ""
```

- [ ] **Step 3: Run the tests to verify they fail**

Run (from `ModpackManager/`): `.venv/Scripts/python -m pytest tests/test_modrinth.py tests/test_curseforge.py -k project_changelog -v`
Expected: FAIL — `AttributeError: module 'modpack_manager.sources.modrinth' has no attribute 'project_changelog'` (and the same for `curseforge`).

- [ ] **Step 4: Implement `modrinth.project_changelog`** — append to `modpack_manager/sources/modrinth.py` (after `project_versions`, [modrinth.py:257](../../../ModpackManager/modpack_manager/sources/modrinth.py:257)):

```python
def project_changelog(version_id, api_key=""):
    """One version's changelog for the Add preview. `version_id` is the `ref`
    from project_versions (the Modrinth version id). Best-effort: any failure
    returns an all-empty object so the Add preview degrades instead of 500-ing."""
    try:
        session = _session(api_key)
        r = session.get(f"{API}/version/{version_id}", timeout=30)
        if r.status_code != 200:
            return {"version": "", "date": "", "body_html": ""}
        v = r.json()
        return {"version": v.get("version_number", ""),
                "date": (v.get("date_published") or "")[:10],
                "body_html": render_markdown(v.get("changelog") or "")}
    except Exception:  # noqa: BLE001
        return {"version": "", "date": "", "body_html": ""}
```

- [ ] **Step 5: Implement `curseforge.project_changelog`** — append to `modpack_manager/sources/curseforge.py` (after `project_versions`, [curseforge.py:285](../../../ModpackManager/modpack_manager/sources/curseforge.py:285)):

```python
def project_changelog(mod_id, file_id, api_key=""):
    """One file's changelog for the Add preview. `mod_id` = the CF project id
    (hit.id); `file_id` = the `ref` from project_versions (the CF file id).
    Reuses `_changelog` (sanitized HTML, "" on non-200). CF's changelog endpoint
    carries no version/date, so those stay empty and the frontend falls back to
    the dropdown label. Best-effort: any failure returns an all-empty object."""
    if not api_key:
        return {"version": "", "date": "", "body_html": ""}
    try:
        session = _session(api_key)
        return {"version": "", "date": "", "body_html": _changelog(session, mod_id, file_id)}
    except Exception:  # noqa: BLE001
        return {"version": "", "date": "", "body_html": ""}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py tests/test_curseforge.py -k project_changelog -v`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add ModpackManager/modpack_manager/sources/modrinth.py ModpackManager/modpack_manager/sources/curseforge.py ModpackManager/tests/test_modrinth.py ModpackManager/tests/test_curseforge.py
git commit -m "feat: add per-version project_changelog to Modrinth/CurseForge sources"
```

---

## Task 2: Backend — service dispatch, webapp route, app wiring (TDD)

**Files:** Modify `service.py`, `webapp.py`, `__main__.py`. Test: `tests/test_service.py`, `tests/test_webapp.py`.

- [ ] **Step 1: Write the failing service tests** — append to `tests/test_service.py`:

```python
def test_real_project_changelog_dispatches_by_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "pack_paths",
                        lambda: types.SimpleNamespace(config_ini=tmp_path / "c.ini"))
    monkeypatch.setattr(service, "load_config", lambda p: types.SimpleNamespace(
        mc_version="1.21.1", loader="neoforge", modrinth_api_key="MK", curseforge_api_key="CK"))
    seen = {}
    monkeypatch.setattr(service.modrinth, "project_changelog",
                        lambda ref, key: seen.update(mr=(ref, key)) or {"version": "1.0", "date": "", "body_html": "<p>m</p>"})
    monkeypatch.setattr(service.curseforge, "project_changelog",
                        lambda mod_id, ref, key: seen.update(cf=(mod_id, ref, key)) or {"version": "", "date": "", "body_html": "<p>c</p>"})

    mr = service.real_project_changelog("modrinth", "AAB", "V1")
    assert mr["body_html"] == "<p>m</p>"
    assert seen["mr"] == ("V1", "MK")             # modrinth uses ref (version id) + its api key

    cf = service.real_project_changelog("curseforge", "999", "7600000")
    assert cf["body_html"] == "<p>c</p>"
    assert seen["cf"] == (999, "7600000", "CK")   # id int-coerced (= mod id), ref = file id


def test_real_project_changelog_bad_curseforge_id_is_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "pack_paths",
                        lambda: types.SimpleNamespace(config_ini=tmp_path / "c.ini"))
    monkeypatch.setattr(service, "load_config", lambda p: types.SimpleNamespace(
        mc_version="1.21.1", loader="neoforge", modrinth_api_key="MK", curseforge_api_key="CK"))
    out = service.real_project_changelog("curseforge", "not-a-number", "1")
    assert out == {"version": "", "date": "", "body_html": ""}
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_service.py -k project_changelog -v`
Expected: FAIL — `AttributeError: module 'modpack_manager.service' has no attribute 'real_project_changelog'`.

- [ ] **Step 3: Implement `real_project_changelog`** — add to `modpack_manager/service.py` after `real_project_versions` ([service.py:91-98](../../../ModpackManager/modpack_manager/service.py:91)):

```python
def real_project_changelog(platform, project_id, ref):
    paths = pack_paths()
    config = load_config(paths.config_ini)
    if platform == "curseforge":
        try:
            mod_id = int(project_id)
        except (TypeError, ValueError):        # a CF preview without a numeric id -> empty, no 500
            return {"version": "", "date": "", "body_html": ""}
        return curseforge.project_changelog(mod_id, ref, config.curseforge_api_key)
    return modrinth.project_changelog(ref, config.modrinth_api_key)
```

- [ ] **Step 4: Run to verify the service tests pass**

Run: `.venv/Scripts/python -m pytest tests/test_service.py -v`
Expected: PASS (all, including the two new tests).

- [ ] **Step 5: Write the failing webapp test + thread `changelog_fn` through every `create_app` call**

In `tests/test_webapp.py`, add a `changelog_fn` to the `_client(...)` fake — inside the `webapp.create_app(...)` call ([test_webapp.py:25-36](../../../ModpackManager/tests/test_webapp.py:25)), add this line (e.g. right after `versions_fn=...`):

```python
        changelog_fn=lambda platform, i, ref: {"version": "1.0", "date": "2026-07-01", "body_html": "<p>cl</p>"},
```

Add `changelog_fn` to the other three inline `create_app(...)` calls so they still construct (they pass every collaborator explicitly):
- `test_failed_generate_leaves_nothing_committable` ([test_webapp.py:119](../../../ModpackManager/tests/test_webapp.py:119)) — add `changelog_fn=lambda p, i, r: {},`
- `test_discard_failure_keeps_paths_retryable` ([test_webapp.py:140](../../../ModpackManager/tests/test_webapp.py:140)) — add `changelog_fn=lambda p, i, r: {},`
- `test_updates_route_returns_candidates_and_warnings` ([test_webapp.py:153](../../../ModpackManager/tests/test_webapp.py:153)) — add `changelog_fn=lambda p, i, r: {},`

Append the new route test:

```python
def test_project_changelog_route():
    data = _client({}).get("/api/project-changelog?platform=modrinth&id=AAB&ref=V1").get_json()
    assert data["body_html"] == "<p>cl</p>"
    assert data["version"] == "1.0"
```

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v`
Expected: FAIL — `TypeError: create_app() got an unexpected keyword argument 'changelog_fn'`.

- [ ] **Step 6: Add the `changelog_fn` param + route in `webapp.py`**

Update the signature ([webapp.py:11-12](../../../ModpackManager/modpack_manager/webapp.py:11)) — add `changelog_fn` after `versions_fn`:

```python
def create_app(scan_fn, generate_fn, pack_fn, search_fn, resolve_fn, versions_fn,
               changelog_fn, commit_fn, discard_fn) -> Flask:
```

Add the route right after `project_versions` ([webapp.py:47-50](../../../ModpackManager/modpack_manager/webapp.py:47)):

```python
    @app.get("/api/project-changelog")
    def project_changelog():
        return jsonify(changelog_fn(
            request.args.get("platform", "modrinth"),
            request.args.get("id", ""),
            request.args.get("ref", "")))
```

- [ ] **Step 7: Wire the real collaborator in `__main__.py`**

Add the import to the existing `from .service import (...)` block ([__main__.py:6-7](../../../ModpackManager/modpack_manager/__main__.py:6)):

```python
from .service import (real_scan, generate_events, real_pack, real_search,
                      real_resolve, real_project_versions, real_project_changelog,
                      real_commit, real_discard)
```

Pass it in the `create_app(...)` call ([__main__.py:14-17](../../../ModpackManager/modpack_manager/__main__.py:14)):

```python
    app = create_app(scan_fn=real_scan, generate_fn=generate_events, pack_fn=real_pack,
                     search_fn=real_search, resolve_fn=real_resolve,
                     versions_fn=real_project_versions,
                     changelog_fn=real_project_changelog,
                     commit_fn=real_commit, discard_fn=real_discard)
```

- [ ] **Step 8: Run the webapp tests + full suite**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v` then `.venv/Scripts/python -m pytest -q`
Expected: all green (the new route test plus the whole pre-existing suite).

- [ ] **Step 9: Commit**

```bash
git add ModpackManager/modpack_manager/service.py ModpackManager/modpack_manager/webapp.py ModpackManager/modpack_manager/__main__.py ModpackManager/tests/test_service.py ModpackManager/tests/test_webapp.py
git commit -m "feat: add GET /api/project-changelog route + service dispatch"
```

---

## Task 3: Frontend — "Needs manual update" section (§4.1)

**Files:** Modify `web/index.html`, `web/style.css`, `web/app.js`. (No JS runner — `node --check` guards parsing; runtime is Task 6.)

- [ ] **Step 1: Add the `#manual-updates` band to `index.html`**

In the Updates panel, insert it between `#scan-warnings` and `.panes` ([index.html:23-24](../../../ModpackManager/modpack_manager/web/index.html:23)):

```html
    <div id="scan-warnings" class="warnings" hidden></div>
    <div id="manual-updates" class="manual-updates" hidden></div>
    <div class="panes">
```

- [ ] **Step 2: Add the manual-section styles to `style.css`** (append to the end):

```css
/* --- "Needs manual update" section (Updates tab) --- */
.manual-updates { margin:.5rem .9rem 0; border:1px solid rgba(255,159,10,.3);
  background:rgba(255,159,10,.08); border-radius:8px; overflow:hidden; }
.manual-updates[hidden] { display:none; }
.manual-head { display:flex; align-items:center; gap:.5rem; padding:.5rem .7rem;
  cursor:pointer; color:var(--minor); font-size:.82rem; font-weight:600; }
.manual-head .manual-title { flex:1; }
.manual-head .caret { transition:transform .15s; }
.manual-head.collapsed .caret { transform:rotate(-90deg); }
.manual-body { max-height:32vh; overflow-y:auto; border-top:1px solid rgba(255,159,10,.2); }
.manual-row { display:flex; align-items:center; gap:.6rem; padding:.45rem .7rem;
  border-bottom:1px solid var(--border); cursor:pointer; }
.manual-row:last-child { border-bottom:none; }
.manual-row.active { background:var(--sel); box-shadow:inset 3px 0 0 var(--accent); }
.manual-row .main { flex:1; min-width:0; }
.manual-row .name { font-weight:600; font-size:.85rem; }
.manual-row .ver { font-size:.72rem; color:var(--muted); }
.manual-row .ver b { color:var(--accent); }
.manual-row .reason { font-size:.72rem; max-width:40ch; text-align:right; }
.manual-row a.open { color:var(--accent); text-decoration:none; padding:2px 5px; }
```

- [ ] **Step 3: Split `visible()` into a shared predicate + two views in `app.js`**

Replace the whole `visible()` function ([app.js:52-56](../../../ModpackManager/modpack_manager/web/app.js:52)) with:

```javascript
function matchesFilters(c) {
  return (!state.filters.severity || c.severity === state.filters.severity) &&
         (!state.filters.source || c.platform === state.filters.source);
}
function visible() { return state.candidates.filter((c) => c.status !== "manual" && matchesFilters(c)); }
function manualVisible() { return state.candidates.filter((c) => c.status === "manual" && matchesFilters(c)); }
```

- [ ] **Step 4: Add `manualCollapsed` to `state`**

In the `state` object literal, change the last line ([app.js:5](../../../ModpackManager/modpack_manager/web/app.js:5)) from:

```javascript
  releaseFilter: "", dismissed: new Set(),
```
to:
```javascript
  releaseFilter: "", dismissed: new Set(), manualCollapsed: false,
```

- [ ] **Step 5: Add `renderManual()` and call it from `renderUpdates()`**

Add `renderManual` right after `renderUpdates` ([app.js:57-76](../../../ModpackManager/modpack_manager/web/app.js:57)):

```javascript
function renderManual() {
  const band = $("#manual-updates");
  band.innerHTML = "";
  const rows = manualVisible();
  band.hidden = rows.length === 0;
  if (!rows.length) return;
  const head = document.createElement("div");
  head.className = "manual-head" + (state.manualCollapsed ? " collapsed" : "");
  head.innerHTML = `<span class="manual-title">⚠ Needs manual update (${rows.length})</span><span class="caret">▾</span>`;
  head.addEventListener("click", () => { state.manualCollapsed = !state.manualCollapsed; renderManual(); });
  band.append(head);
  if (state.manualCollapsed) return;
  const body = document.createElement("div"); body.className = "manual-body";
  for (const c of rows) {
    const row = document.createElement("div");
    row.className = "manual-row" + (state.active === c.mod_id ? " active" : "");
    const main = document.createElement("div"); main.className = "main";
    main.innerHTML = `<div class="name">${esc(c.name)}</div><div class="ver">${esc(c.current_version)} → <b>${esc(c.latest_version)}</b></div>`;
    const reason = document.createElement("div"); reason.className = "reason muted";
    reason.textContent = c.note || "";
    const link = document.createElement("span");
    link.innerHTML = openLink(c.project_url);
    row.append(main, reason, link);
    row.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;               // let the "open page" link work
      state.active = c.mod_id; renderUpdates();
    });
    body.append(row);
  }
  band.append(body);
}
```

In `renderUpdates`, change the count line ([app.js:73](../../../ModpackManager/modpack_manager/web/app.js:73)) from:

```javascript
  $("#update-count").textContent = `${state.candidates.length} updates`;
```
to (count only the actionable `ok` rows; the manual total lives in the section header):
```javascript
  $("#update-count").textContent = `${state.candidates.filter((c) => c.status === "ok").length} updates`;
```

Then insert a `renderManual()` call immediately before the final `renderReader();` in `renderUpdates` ([app.js:75](../../../ModpackManager/modpack_manager/web/app.js:75)):

```javascript
  renderManual();
  renderReader();
```

- [ ] **Step 6: Verify the JS parses**

Run (from repo root): `node --check ModpackManager/modpack_manager/web/app.js`
Expected: success (no output).

- [ ] **Step 7: Commit**

```bash
git add ModpackManager/modpack_manager/web/index.html ModpackManager/modpack_manager/web/style.css ModpackManager/modpack_manager/web/app.js
git commit -m "feat: pull distribution-blocked mods into a Needs-manual-update section"
```

---

## Task 4: Frontend — Updates name filter + keyboard navigation (§4.2)

**Files:** Modify `web/index.html`, `web/app.js`. Depends on `matchesFilters` / `manualVisible` from Task 3 (both views inherit the new text clause for free).

- [ ] **Step 1: Add the `#updates-filter` input to the toolbar in `index.html`**

Insert it right after the `.counts` div in the Updates toolbar ([index.html:18-19](../../../ModpackManager/modpack_manager/web/index.html:18)):

```html
      <div class="counts"><span id="update-count">0 updates</span> · <span id="selected-count">0 selected</span></div>
      <input id="updates-filter" placeholder="Filter updates…">
      <select id="filter-severity"><option value="">All severity</option><option>major</option><option>minor</option><option>patch</option></select>
```

(No new CSS — `.toolbar input`, [style.css:55](../../../ModpackManager/modpack_manager/web/style.css:55), already styles it, as it does `#remove-filter`.)

- [ ] **Step 2: Add `filters.text` to `state`**

Change the `filters` line in the `state` literal ([app.js:3](../../../ModpackManager/modpack_manager/web/app.js:3)) from:

```javascript
  filters: { severity: "", source: "" },
```
to:
```javascript
  filters: { severity: "", source: "", text: "" },
```

- [ ] **Step 3: Add the text clause to `matchesFilters`**

Replace `matchesFilters` (added in Task 3) with the version that also tests the name substring:

```javascript
function matchesFilters(c) {
  return (!state.filters.severity || c.severity === state.filters.severity) &&
         (!state.filters.source || c.platform === state.filters.source) &&
         (!state.filters.text || c.name.toLowerCase().includes(state.filters.text));
}
```

- [ ] **Step 4: Wire the filter input handler**

Add it beside the existing severity/source handlers ([app.js:98-99](../../../ModpackManager/modpack_manager/web/app.js:98)):

```javascript
$("#updates-filter").addEventListener("input", (e) => { state.filters.text = e.target.value.toLowerCase(); renderUpdates(); });
```

- [ ] **Step 5: Add the keyboard-navigation handler**

Add a single global `keydown` listener right after the filter handlers (e.g. after the `#select-all` handler, [app.js:100-105](../../../ModpackManager/modpack_manager/web/app.js:100)):

```javascript
// Keyboard nav for the Updates list: ↑/↓ (+ k/j) move the active row through the
// filtered visible() order, Enter opens its page, Space toggles its selection.
// Gated so it never fires on other tabs, under an open review/result modal, or
// while a text field / interactive control (input, select, button, link) has focus.
document.addEventListener("keydown", (e) => {
  if ($("#tab-updates").hidden || !$("#review").hidden || !$("#result").hidden) return;
  const el = document.activeElement;
  if (el && /^(INPUT|SELECT|TEXTAREA|BUTTON|A)$/.test(el.tagName)) return;
  const rows = visible();
  if (!rows.length) return;
  const idx = rows.findIndex((c) => c.mod_id === state.active);   // -1 if active is filtered out / unset
  if (["ArrowDown", "ArrowUp", "j", "k"].includes(e.key)) {
    e.preventDefault();
    const down = e.key === "ArrowDown" || e.key === "j";
    const next = idx < 0 ? 0 : Math.min(Math.max(idx + (down ? 1 : -1), 0), rows.length - 1);
    state.active = rows[next].mod_id;
    renderUpdates();
    const activeRow = $("#mod-list").children[next];              // render order === visible() order
    if (activeRow) activeRow.scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") {
    const c = rows[idx];
    if (c && c.project_url && /^https?:\/\//i.test(c.project_url)) {
      e.preventDefault();
      window.open(c.project_url, "_blank", "noopener");
    }
  } else if (e.key === " " || e.key === "Spacebar") {
    const c = rows[idx];
    if (c && c.status === "ok") { e.preventDefault(); toggleUpdate(c.mod_id); }
  }
});
```

- [ ] **Step 6: Verify the JS parses**

Run: `node --check ModpackManager/modpack_manager/web/app.js`
Expected: success (no output).

- [ ] **Step 7: Commit**

```bash
git add ModpackManager/modpack_manager/web/index.html ModpackManager/modpack_manager/web/app.js
git commit -m "feat: name filter + keyboard nav on the Updates list"
```

---

## Task 5: Frontend — changelog / description preview on Add (§4.3)

**Files:** Modify `web/app.js`, `web/style.css`. Uses the `/api/project-changelog` route from Task 2.

- [ ] **Step 1: Add the add-preview styles to `style.css`** (append to the end):

```css
/* --- Add-tab changelog/description preview --- */
.add-result { display:flex; flex-direction:column; }
.add-row .disc { background:transparent; border:none; color:var(--muted); cursor:pointer;
  font-size:.8rem; padding:0 2px; }
.add-result .name { cursor:pointer; }  /* scope to results only — .add-row is reused by the Add Queue */
.add-preview { margin:2px 0 0 1.6rem; padding:.5rem .7rem; background:var(--bg);
  border:1px solid var(--border); border-radius:8px; }
.add-preview[hidden] { display:none; }
.add-preview .cl-ver { font-weight:700; margin:.6rem 0 .3rem; font-size:.8rem; }
.add-preview .cl-ver:first-child { margin-top:0; }
.add-preview .cl-date { color:var(--muted); font-weight:400; font-size:.72rem; margin-left:.4rem; }
.add-preview .cl-body { font-size:.82rem; color:#d0d0d2; }
.add-preview .cl-body :is(h1,h2,h3) { font-size:.9rem; }
```

- [ ] **Step 2: Rewrite `renderResults` to add the disclosure control + preview container**

Replace the whole `renderResults` function ([app.js:123-147](../../../ModpackManager/modpack_manager/web/app.js:123)) with:

```javascript
function renderResults(hits) {
  const box = $("#add-results"); box.innerHTML = "";
  if (!hits.length) { box.innerHTML = '<p class="muted" style="padding:.5rem">No results. Try a link or id.</p>'; return; }
  for (const hit of hits.slice(0, 12)) {
    const wrap = document.createElement("div"); wrap.className = "add-result";
    const row = document.createElement("div"); row.className = "add-row";
    const inPack = state.pack.some((m) => m.name.toLowerCase() === hit.name.toLowerCase());
    row.innerHTML = `<button class="disc" type="button" aria-expanded="false" aria-label="Toggle details">▸</button>
      <div class="main"><div class="name">${esc(hit.name)}</div><div class="sum">${esc(hit.summary)}</div></div>
      <span class="tag">${hit.platform === "curseforge" ? "CF" : "MR"}</span>${openLink(hit.page_url)}
      <select class="ver-sel"><option>loading…</option></select>
      <button class="add-btn" disabled>${inPack ? "In pack" : "Add"}</button>`;
    const preview = document.createElement("div"); preview.className = "add-preview"; preview.hidden = true;
    wrap.append(row, preview);
    box.append(wrap);
    const sel = row.querySelector(".ver-sel");
    const btn = row.querySelector(".add-btn");
    const toggle = () => togglePreview(wrap, hit, sel);
    row.querySelector(".disc").addEventListener("click", toggle);
    row.querySelector(".name").addEventListener("click", toggle);
    sel.addEventListener("change", () => { if (!preview.hidden) loadPreview(preview, hit, sel); });
    // fetch each row's versions in parallel — don't block rendering the next row
    fetchVersions(hit).then((versions) => {
      populateVersions(sel, versions);
      if (!versions.length) { sel.innerHTML = "<option>no compatible versions</option>"; return; }
      btn.disabled = inPack;
      btn.addEventListener("click", () => {
        const opt = versions.find((v) => v.ref === sel.value);
        if (opt) queueAdd(hit, opt, versions.side);
      });
      if (!preview.hidden) loadPreview(preview, hit, sel);   // refresh if expanded before versions arrived
    }).catch(() => { sel.innerHTML = "<option>versions unavailable</option>"; });
  }
}

function togglePreview(wrap, hit, sel) {
  const preview = wrap.querySelector(".add-preview");
  const disc = wrap.querySelector(".disc");
  const open = preview.hidden;                 // currently hidden -> we're opening it
  preview.hidden = !open;
  disc.textContent = open ? "▾" : "▸";
  disc.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) loadPreview(preview, hit, sel);
}

async function loadPreview(preview, hit, sel) {
  const req = (preview._req = (preview._req || 0) + 1);   // supersede any in-flight load
  const descHtml = `<div class="cl-ver">Description</div><div class="cl-body">${esc(hit.summary) || '<span class="muted">No description.</span>'}</div>`;
  const optEl = sel.options[sel.selectedIndex];
  const label = optEl ? optEl.textContent : "";
  const placeholder = /^(loading…|no compatible versions|versions unavailable)$/.test(label);
  if (!sel.value || placeholder) {
    preview.innerHTML = descHtml + `<div class="cl-ver">Changelog</div><div class="cl-body muted">Select a version.</div>`;
    return;
  }
  preview.innerHTML = descHtml + `<div class="cl-ver">Changelog</div><div class="cl-body muted">Loading changelog…</div>`;
  try {
    const cl = await fetchChangelog(hit.platform, hit.id, sel.value);
    if (preview._req !== req) return;   // a newer load superseded this one
    const ver = cl.version || label;
    const date = cl.date ? `<span class="cl-date">${esc(cl.date)}</span>` : "";
    const bodyHtml = cl.body_html || '<span class="muted">No changelog provided.</span>';
    preview.innerHTML = descHtml + `<div class="cl-ver">${esc(ver)}${date}</div><div class="cl-body">${bodyHtml}</div>`;
  } catch (e) {
    if (preview._req !== req) return;   // a newer load superseded this one
    preview.innerHTML = descHtml + `<div class="cl-ver">Changelog</div><div class="cl-body muted">Changelog unavailable.</div>`;
  }
}

async function fetchChangelog(platform, id, ref) {
  const res = await fetch(`/api/project-changelog?platform=${encodeURIComponent(platform)}&id=${encodeURIComponent(id)}&ref=${encodeURIComponent(ref)}`);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}
```

*(Note: `body_html` is server-sanitized, so it is injected via `innerHTML` exactly as `renderReader` injects changelog bodies. The description reuses the full `hit.summary` un-clamped — the row's `.sum` stays truncated.)*

- [ ] **Step 3: Verify the JS parses**

Run: `node --check ModpackManager/modpack_manager/web/app.js`
Expected: success (no output).

- [ ] **Step 4: Commit**

```bash
git add ModpackManager/modpack_manager/web/app.js ModpackManager/modpack_manager/web/style.css
git commit -m "feat: expandable description + per-version changelog preview on Add"
```

---

## Task 6: Full regression + live verification

**Files:** none (verification only).

- [ ] **Step 1: Full backend suite**

Run (from `ModpackManager/`): `.venv/Scripts/python -m pytest -q`
Expected: all green (sources `project_changelog`, service dispatch, webapp route, plus the entire pre-existing suite).

- [ ] **Step 2: JS parse check**

Run (from repo root): `node --check ModpackManager/modpack_manager/web/app.js`
Expected: success (no output).

- [ ] **Step 3: Live verification via the `ModpackManager:verify` skill**

Invoke `Skill(ModpackManager:verify)`, launch the app, open the browser pane. Because the update list is ~130 rows, drive assertions with `javascript_tool` (per the skill). Verify all three behaviors (spec §10):

1. **Manual section** — after load, confirm every `status == "manual"` candidate renders in `#manual-updates` (not `#mod-list`), the header count matches, and the reason + "open page ↗" link show. Drive it deterministically:
   `fetch("/api/updates").then(r=>r.json()).then(d => ({manual: d.candidates.filter(c=>c.status==="manual").length, band: !document.querySelector("#manual-updates").hidden, headCount: (document.querySelector(".manual-head .manual-title")||{}).textContent}))`
   — assert `manual > 0 ⇒ band === true` and the header count equals `manual`. Confirm `#mod-list` contains no `.row.manual`. Toggle the header and assert `.manual-body` hides/shows.
2. **Filter + keyboard** — set `document.querySelector("#updates-filter").value = "<substr>"` and dispatch an `input` event; assert both `#mod-list` and (if any manual match) the manual band narrow to names containing the substring. With focus off the input, dispatch `keydown` ArrowDown/ArrowUp (and `j`/`k`) and assert `.row.active` moves and the reader updates; `Space` toggles the active row's checkbox/selection; `Enter` on a row with a `project_url` opens a tab. Confirm none fire while focus is in `#updates-filter`.
3. **Changelog-on-add** — search a common mod, click a result's `.disc` (or its name); assert `.add-preview` un-hides with the full description and, after the fetch, the selected version's changelog (`.cl-body`). Change `.ver-sel` and assert the changelog re-fetches. Confirm the **Add** button still queues regardless of the preview.

Kill the server afterward.

- [ ] **Step 4: Final commit (only if verification required tweaks)**

```bash
git add -A ModpackManager/
git commit -m "chore: ux-surfacing verification tweaks"
```
(Skip if nothing changed.)

---

## Notes for the implementer

- **`changelog_fn` is a required DI param, no default** — matching the codebase's explicit-DI convention ([webapp.py:11](../../../ModpackManager/modpack_manager/webapp.py:11)). Every `create_app(...)` call site (the app in `__main__.py` and all four in `test_webapp.py`) must pass it; Task 2 updates them together so the suite is green at that commit.
- **`ref` identity differs per platform.** Modrinth: `ref` = the version id, and `project_changelog(ref, key)` ignores `id`. CurseForge: `ref` = the file id and `id` = the mod id; both are needed (`int(id)` is guarded in `real_project_changelog`). This mirrors what `project_versions` already returns for each platform ([modrinth.py:264](../../../ModpackManager/modpack_manager/sources/modrinth.py:264), [curseforge.py:294](../../../ModpackManager/modpack_manager/sources/curseforge.py:294)).
- **`matchesFilters` is the single source of truth** for both `visible()` (main list) and `manualVisible()` (manual band). Task 3 introduces it with severity+source; Task 4 adds the text clause — both views pick it up automatically. Don't duplicate the predicate.
- **`#update-count` counts `ok` candidates only.** Manual (and error) rows are excluded so the count doesn't double the manual band's header count.
- **Keyboard nav traverses the filtered `visible()` order** and relies on `#mod-list` render order matching `visible()` (it does — `renderUpdates` iterates `visible()`). If the active mod is filtered out or is a manual row, `idx === -1` and the first ↑/↓ jumps to index 0 (spec §9). Space is guarded to `status === "ok"` to match the disabled-checkbox rule.
- **Frontend has no JS runner** — `node --check` only catches parse errors; Task 6's `ModpackManager:verify` is the real behavioral gate. Run it.
- **Commits are YubiKey-signed** — each `git commit` step needs a physical key touch and will time out unattended, so run commits interactively (warn before touching).
