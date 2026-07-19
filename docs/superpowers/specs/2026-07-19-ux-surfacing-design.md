# UX Surfacing — Manual-Update List, List Search & Keyboard Nav, Changelog-on-Add (Design)

- **Date:** 2026-07-19
- **Status:** Draft for review
- **Builds on:** [2026-07-19-close-the-loop-design.md](2026-07-19-close-the-loop-design.md), [2026-07-18-dependency-auto-add-design.md](2026-07-18-dependency-auto-add-design.md)
- **Repo:** Gears & Frontiers (MCUpdater modpack, NeoForge 1.21.1)

## 1. Problem / goal

Three small, unrelated rough edges have accumulated in the picker UI as the pack
has grown to ~130 mods. None is a new subsystem; each is a *surfacing* gap where
information the tool already has is hard to see or act on:

1. **Distribution-blocked CurseForge mods are easy to miss.** The scan marks them
   `status == "manual"` ([curseforge.py:147](../../../ModpackManager/modpack_manager/sources/curseforge.py:147))
   and `generate_events` deliberately excludes them from the written batch
   ([service.py:113](../../../ModpackManager/modpack_manager/service.py:113)). In
   the UI they render as a dimmed inline row (`.row.manual { opacity:.7 }`,
   [style.css:33](../../../ModpackManager/modpack_manager/web/style.css:33)) with a
   disabled checkbox ([app.js:44](../../../ModpackManager/modpack_manager/web/app.js:44)),
   lost among ~130 actionable rows. The maintainer only learns they were skipped
   *after* generating, via the `manual_count` note
   ([app.js:356](../../../ModpackManager/modpack_manager/web/app.js:356)) — too
   late to act in the same pass.

2. **The long lists are click-only, with no text search on Updates.** `visible()`
   filters by severity + source dropdowns only
   ([app.js:33](../../../ModpackManager/modpack_manager/web/app.js:33)); moving the
   active row is mouse-click-only ([app.js:51](../../../ModpackManager/modpack_manager/web/app.js:51)).
   The Remove tab *already* has a name filter (`#remove-filter`,
   [app.js:202](../../../ModpackManager/modpack_manager/web/app.js:202)); Updates
   has nothing equivalent, and neither list has keyboard navigation.

3. **Adds are queued blind.** The Updates reader shows changelogs
   ([app.js:58](../../../ModpackManager/modpack_manager/web/app.js:58)), but the
   Add tab's search results show only name + a one-line truncated summary + a
   version dropdown ([app.js:109](../../../ModpackManager/modpack_manager/web/app.js:109))
   — no way to read the selected version's changelog before committing to add it.

**Goal:** close all three surfacing gaps with the smallest faithful changes —
a dedicated "Needs manual update" section, a name filter + keyboard nav on the
Updates list, and an on-demand changelog preview when adding — reusing existing
data, styles, and endpoints wherever the data already exists.

## 2. Key decisions

- **Manual mods get their own always-visible section on the Updates tab, and
  leave the main list.** A collapsible band between the toolbar and the panes
  lists every `status == "manual"` candidate with its version transition, a direct
  open-page link, and the one-line reason. They are *pulled out of* the scrolling
  list (`visible()` stops emitting them) so the main list is purely actionable and
  the blocked ones can't be scrolled past. **Zero backend change** — `note`,
  `current_version`, `latest_version`, and `project_url` are already on the
  `Candidate` and already shipped by `/api/updates`
  ([base.py:41](../../../ModpackManager/modpack_manager/sources/base.py:41),
  [curseforge.py:150](../../../ModpackManager/modpack_manager/sources/curseforge.py:150)).
  *(Section on Updates vs. its own tab is an open question — §11.1; the tab option
  is rejected here because hiding the list behind a click reintroduces the exact
  "easy to miss" problem.)*

- **Updates gets a name filter that mirrors the Remove tab verbatim.** A new
  `#updates-filter` input drives `state.filters.text`, and `visible()` gains one
  substring test — the same lowercase `name.includes(q)` the Remove tab already
  uses ([app.js:206](../../../ModpackManager/modpack_manager/web/app.js:206)). No
  new pattern, no fuzzy matching.

- **Keyboard nav layers onto the existing `state.active` highlight — it does not
  add a second cursor.** Arrow keys move `state.active` through the *filtered*
  `visible()` order (reusing the `.row.active` highlight,
  [style.css:21](../../../ModpackManager/modpack_manager/web/style.css:21)),
  which already re-renders the reader on change
  ([app.js:59](../../../ModpackManager/modpack_manager/web/app.js:59)). Chosen
  bindings: **↑/↓ move, Enter opens the active mod's page, Space toggles its
  selection** (`j`/`k` offered as vim aliases for ↓/↑). *(Exact binding set is an
  open question — §11.2.)*

- **Changelog-on-add is lazy, via one new endpoint.** Each Add row gets a
  disclosure toggle; expanding it shows the (un-truncated) description the hit
  already carries plus the **selected version's** changelog, fetched on demand from
  a new `GET /api/project-changelog`. It re-fetches when the version dropdown
  changes while expanded. *(Why a new endpoint rather than extending
  `/api/project-versions` — §11.3: extending it would force N eager CurseForge
  changelog calls per search hit, since CF changelogs are a per-file endpoint,
  [curseforge.py:83](../../../ModpackManager/modpack_manager/sources/curseforge.py:83).)*

- **Two of three features are frontend-only.** The manual section and the
  filter+keyboard work touch only `web/*` (data already present). Only
  changelog-on-add adds a route + two thin source functions. This keeps the risk
  concentrated in one small, testable place.

## 3. Non-goals (v1)

- **No auto-fixing manual mods.** Distribution-blocked mods still require a manual
  download; the section surfaces and links them, it does not download or hash them.
  Generation still skips `status != "ok"`
  ([service.py:113](../../../ModpackManager/modpack_manager/service.py:113)).
- **No filter/keyboard nav on the Add or Remove results.** The Remove filter stays
  as-is; keyboard nav lands on the Updates list only (the ~130-row list that hurts).
- **No fuzzy / multi-field search.** Name substring only, matching Remove.
- **No changelog preview for the *whole* project body or README** on add — only the
  short description (already fetched) and the per-version changelog.
- **No caching layer for changelog-on-add.** One HTTP call per expand / version
  change; localhost, low volume. (Client-side memoization is deferred — §12.)
- **No persistence of collapse / filter / active state** across reloads — matches
  the app's existing in-memory-only `state` ([app.js:1](../../../ModpackManager/modpack_manager/web/app.js:1)).

## 4. UX

### 4.1 Updates tab — "Needs manual update" section

A new collapsible `#manual-updates` band sits between the toolbar
([index.html:17](../../../ModpackManager/modpack_manager/web/index.html:17)) and
`.panes` ([index.html:23](../../../ModpackManager/modpack_manager/web/index.html:23)),
full width, above both the list and the reader.

- **Header (always rendered when count > 0):**
  `⚠ Needs manual update (N) ▾` — click toggles collapse. Orange-tinted to match
  the existing dependency banner (`.dep`,
  [style.css:42](../../../ModpackManager/modpack_manager/web/style.css:42)).
  **Expanded by default** so the maintainer sees the blocked mods on load; hidden
  entirely (`hidden`) when `N == 0`.
- **Each row:** name · `current_version → latest_version` (always known for manual
  candidates — CF still computes both before the block check,
  [curseforge.py:130](../../../ModpackManager/modpack_manager/sources/curseforge.py:130)) ·
  **Open page ↗** (→ `project_url`, the CurseForge page) · a muted one-line reason
  (`note`: "This mod blocks third-party downloads — update it manually.",
  [curseforge.py:148](../../../ModpackManager/modpack_manager/sources/curseforge.py:148)).
- **Clicking a row** (not the link) sets `state.active`, so the reader shows that
  mod's changelog + note via the existing `renderReader()` path — manual candidates
  carry changelogs already ([curseforge.py:124](../../../ModpackManager/modpack_manager/sources/curseforge.py:124)).
- **Filter interaction:** the section honors the same severity / source / text
  filters as the main list, so it stays consistent (a source=Modrinth filter empties
  it, since all manual mods are CurseForge — acceptable, it's an explicit user action).
- The main list no longer renders manual rows; `#update-count`
  ([app.js:54](../../../ModpackManager/modpack_manager/web/app.js:54)) counts the
  actionable (`ok`) updates, and the manual total lives in the section header.

### 4.2 Updates tab — name filter + keyboard navigation

- **Filter input** `#updates-filter` added to the toolbar
  ([index.html:17](../../../ModpackManager/modpack_manager/web/index.html:17)),
  styled by the existing `.toolbar input` rule
  ([style.css:55](../../../ModpackManager/modpack_manager/web/style.css:55)),
  placeholder "Filter updates…". Typing re-renders the list live (and the manual
  section, §4.1). `#selected-count` is unaffected (selection is independent of the
  view filter).
- **Keyboard navigation** (active only when the Updates tab is visible and focus is
  **not** in an input/select):
  - **↑ / ↓** (aliases **k / j**): move `state.active` to the previous / next row in
    `visible()` order; if nothing is active, the first press selects the first
    visible row. The active row is scrolled into view (`scrollIntoView({block:
    "nearest"})`) and the reader updates automatically.
  - **Enter:** open the active mod's `project_url` in a new tab (mirrors the
    reader's "Open on Modrinth/CurseForge ↗" link,
    [app.js:63](../../../ModpackManager/modpack_manager/web/app.js:63)).
  - **Space:** toggle the active mod's selection (calls `toggleUpdate`), so an
    entire update pass is keyboard-drivable. `preventDefault()` stops the page from
    scrolling.
  - Keys we handle call `preventDefault()`; everything else falls through so the
    filter input keeps working normally.

### 4.3 Add tab — changelog / description preview

Each search-result row ([app.js:107](../../../ModpackManager/modpack_manager/web/app.js:107))
gains a disclosure control (a caret `▸` button before the name, or clicking the
name). Toggling it opens an inline `.add-preview` panel below the row:

- **Description:** the full `hit.summary`, un-clamped (today it's truncated with
  `text-overflow:ellipsis`, [style.css:60](../../../ModpackManager/modpack_manager/web/style.css:60)).
  Already in memory — no fetch.
- **Changelog:** the changelog of the **currently-selected** version in that row's
  `.ver-sel` dropdown, lazily fetched from `/api/project-changelog` on first expand.
  Rendered with the same `.cl-ver` / `.cl-body` treatment as the reader
  ([style.css:38](../../../ModpackManager/modpack_manager/web/style.css:38)).
- **States:** collapsed (default) → "Loading changelog…" → rendered, or
  "No changelog provided." / "Changelog unavailable." on empty/error. Changing the
  version dropdown while expanded re-fetches for the new `ref`.
- The **Add** button and version selector behave exactly as today; the preview is
  purely informational and never blocks queuing.

## 5. Architecture

### 5.1 Frontend — manual section (§4.1)

- `state.filters` gains `text: ""` (§5.2); `state` gains `manualCollapsed: false`.
- `visible()` ([app.js:33](../../../ModpackManager/modpack_manager/web/app.js:33))
  splits into two derived views over the same filter predicate:
  - `visible()` → candidates matching filters **and** `status !== "manual"` (the
    main list).
  - `manualVisible()` (new) → candidates matching filters **and** `status ==
    "manual"`.
- `renderManual()` (new) renders the `#manual-updates` band from `manualVisible()`;
  called from `renderUpdates()` so it tracks filter changes. No new fetch, no state
  beyond the collapse flag.

### 5.2 Frontend — filter + keyboard (§4.2)

- `visible()` adds one clause:
  `(!state.filters.text || c.name.toLowerCase().includes(state.filters.text))`,
  identical in spirit to `renderRemove()`
  ([app.js:206](../../../ModpackManager/modpack_manager/web/app.js:206)).
- `#updates-filter` `input` handler sets `state.filters.text = e.target.value
  .toLowerCase()` then `renderUpdates()` (parallel to the severity/source handlers,
  [app.js:79](../../../ModpackManager/modpack_manager/web/app.js:79)).
- A single `keydown` listener on `document`, gated by (a) the Updates tab being the
  visible `.tab-panel` and (b) `document.activeElement` not being
  `INPUT`/`SELECT`/`TEXTAREA`. It resolves the current index in `visible()` from
  `state.active`, computes the next index for ↑/↓/j/k, and reuses the existing
  active-set-and-render flow ([app.js:51](../../../ModpackManager/modpack_manager/web/app.js:51))
  plus `scrollIntoView`. Enter/Space act on the resolved active candidate.

### 5.3 Frontend + backend — changelog-on-add (§4.3)

- **Frontend:** `renderResults()` ([app.js:103](../../../ModpackManager/modpack_manager/web/app.js:103))
  adds the disclosure control + a hidden `.add-preview` container per row.
  `togglePreview(row, hit, sel)` (new) lazy-calls `fetchChangelog(hit.platform,
  hit.id, sel.value)` and renders into the container; the `.ver-sel` `change`
  handler re-invokes it when the panel is open.
- **Backend — new route** `GET /api/project-changelog` in
  [webapp.py](../../../ModpackManager/modpack_manager/webapp.py) alongside
  `/api/project-versions` ([webapp.py:44](../../../ModpackManager/modpack_manager/webapp.py:44)),
  delegating to an injected `changelog_fn` (added to `create_app`'s signature,
  [webapp.py:11](../../../ModpackManager/modpack_manager/webapp.py:11)).
- **Backend — service** `real_project_changelog(platform, project_id, ref)` in
  [service.py](../../../ModpackManager/modpack_manager/service.py) (mirrors
  `real_project_versions`, [service.py:86](../../../ModpackManager/modpack_manager/service.py:86)),
  wired in `__main__.py`'s `create_app(...)` call
  ([__main__.py:14](../../../ModpackManager/modpack_manager/__main__.py:14)).
- **Backend — sources:**
  - `modrinth.project_changelog(version_id, api_key)` — one `GET /version/{id}`,
    `render_markdown(changelog)` (reuses the helper already imported,
    [modrinth.py:9](../../../ModpackManager/modpack_manager/sources/modrinth.py:9)).
    Cheaper than refetching the full list, and the `ref` from
    `project_versions` is exactly the Modrinth version id
    ([modrinth.py:264](../../../ModpackManager/modpack_manager/sources/modrinth.py:264)).
  - `curseforge.project_changelog(mod_id, file_id, api_key)` — wraps the existing
    `_changelog(session, mod_id, file_id)`
    ([curseforge.py:83](../../../ModpackManager/modpack_manager/sources/curseforge.py:83));
    the `ref` from `project_versions` is the CF file id
    ([curseforge.py:296](../../../ModpackManager/modpack_manager/sources/curseforge.py:296)).
    Requires both `id` (mod id, = `hit.id`) and `ref` (file id).

## 6. Data shapes

No changes to `Candidate`, `AddedDependency`, or `SearchHit`
([base.py](../../../ModpackManager/modpack_manager/sources/base.py)) — features 1
and 2 are pure views over existing fields. One new endpoint:

```jsonc
// GET /api/project-changelog?platform=<modrinth|curseforge>&id=<projectOrModId>&ref=<versionOrFileId>
// id  = SearchHit.id  (hit.id in renderResults)
// ref = the selected .ver-sel value (Modrinth version id | CurseForge file id)
{
  "version": "0.5.8",         // version label, or "" if unknown
  "date": "2026-07-01",       // YYYY-MM-DD, or "" (CF changelog endpoint has no date)
  "body_html": "<p>…</p>"     // sanitized/rendered HTML, or "" when none provided
}
```

The response reuses the same sanitized-HTML contract the reader already trusts
(`render_markdown` for Modrinth, `sanitize_html` for CurseForge), so the frontend
injects `body_html` exactly as `renderReader` does for changelog bodies
([app.js:65](../../../ModpackManager/modpack_manager/web/app.js:65)).

## 7. Backend details

### 7.1 `/api/project-changelog` route

```
@app.get("/api/project-changelog")
def project_changelog():
    return jsonify(changelog_fn(
        request.args.get("platform", "modrinth"),
        request.args.get("id", ""),
        request.args.get("ref", "")))
```

Symmetric with `project_versions` ([webapp.py:44](../../../ModpackManager/modpack_manager/webapp.py:44)):
thin, no `cache` interaction, no state. `create_app` gains a `changelog_fn`
parameter ([webapp.py:11](../../../ModpackManager/modpack_manager/webapp.py:11)).

### 7.2 Service + sources

- `real_project_changelog(platform, project_id, ref)` loads config
  (`config.*_api_key`), then dispatches to
  `curseforge.project_changelog(int(project_id), ref, key)` or
  `modrinth.project_changelog(ref, key)` — the branch matching
  `real_project_versions` ([service.py:86](../../../ModpackManager/modpack_manager/service.py:86)).
- **Modrinth** `project_changelog(version_id, api_key)`:
  `GET /version/{version_id}` → `{ "version": v["version_number"], "date":
  v["date_published"][:10], "body_html": render_markdown(v.get("changelog") or "") }`.
  On non-200 or missing → `{ "version": "", "date": "", "body_html": "" }`.
- **CurseForge** `project_changelog(mod_id, file_id, api_key)`: reuse `_changelog`
  (already returns `sanitize_html(...)` or `""` on non-200,
  [curseforge.py:85](../../../ModpackManager/modpack_manager/sources/curseforge.py:85))
  → `{ "version": "", "date": "", "body_html": _changelog(session, mod_id, file_id) }`.
  (CF's changelog endpoint returns no version/date; those stay empty and the
  frontend falls back to the version label from the dropdown.)

Both wrap network calls in the same best-effort try/except style used across the
sources (e.g. [modrinth.py:189](../../../ModpackManager/modpack_manager/sources/modrinth.py:189)),
returning empty `body_html` rather than 500-ing, so a preview failure never breaks
the Add flow.

## 8. Frontend details

- **`renderUpdates()`** ([app.js:38](../../../ModpackManager/modpack_manager/web/app.js:38)):
  iterate `visible()` (now manual-free); call `renderManual()`; keep
  `#update-count`/`#selected-count` and the final `renderReader()`.
- **`renderManual()`** (new): if `manualVisible()` is empty → `#manual-updates`
  `hidden = true`, return. Else render the header (count + collapse caret reading
  `state.manualCollapsed`) and, when expanded, one `.manual-row` per candidate
  (name, `current → latest`, `openLink(c.project_url)`, muted `c.note`). Row click
  (excluding the link) → `state.active = c.mod_id; renderUpdates()`.
- **Filter wiring:** `$("#updates-filter").addEventListener("input", e => {
  state.filters.text = e.target.value.toLowerCase(); renderUpdates(); })`, beside
  the existing filter handlers ([app.js:79](../../../ModpackManager/modpack_manager/web/app.js:79)).
- **Keyboard handler** (new): described in §5.2. Uses `visible()` for order;
  `state.active` for the cursor; `toggleUpdate` ([app.js:75](../../../ModpackManager/modpack_manager/web/app.js:75))
  for Space; `window.open(c.project_url, "_blank", "noopener")` for Enter.
- **`renderResults()`** ([app.js:103](../../../ModpackManager/modpack_manager/web/app.js:103)):
  add the caret + `.add-preview` node; wire `togglePreview`. Keep the existing
  parallel `fetchVersions().then(...)` version wiring
  ([app.js:117](../../../ModpackManager/modpack_manager/web/app.js:117)) untouched.
- **`fetchChangelog(platform, id, ref)`** (new): `GET /api/project-changelog?…`,
  returns the §6 object; caller injects `body_html` and shows the version/date
  header (falling back to the dropdown's selected label when `version` is empty).

### Styling

- `#manual-updates`: an orange-tinted band reusing the `.dep` palette
  ([style.css:42](../../../ModpackManager/modpack_manager/web/style.css:42));
  `max-height` + `overflow-y:auto` so a large blocked set scrolls rather than
  eating the panes. `.manual-row` mirrors `.row`
  ([style.css:20](../../../ModpackManager/modpack_manager/web/style.css:20)) minus
  the checkbox; the collapse caret rotates on `state.manualCollapsed`.
- `.add-preview`: reuses the reader's changelog styles — introduce `.add-preview
  .cl-ver` / `.cl-body` paralleling `.reader .cl-ver` / `.cl-body`
  ([style.css:38](../../../ModpackManager/modpack_manager/web/style.css:38)) so the
  add preview and the update reader look identical.
- `#updates-filter` needs no new CSS — `.toolbar input`
  ([style.css:55](../../../ModpackManager/modpack_manager/web/style.css:55))
  already covers it (as it does `#remove-filter`).

## 9. Error handling / edge cases

- **No manual mods in a scan** → `#manual-updates` stays `hidden`; main list and
  counts unchanged.
- **Filter hides the active row** → keyboard nav resolves the current index against
  the *filtered* `visible()`; if `state.active` is no longer visible, the first
  ↑/↓ jumps to the first visible row (index falls back to 0). Enter/Space on a
  filtered-out active mod are ignored (guarded by "is active in `visible()`?").
- **Keyboard vs. typing** → the handler no-ops when focus is in an input/select, so
  ↑/↓/Space in the filter box behave as normal text editing.
- **Enter with no `project_url`** (rare; Modrinth always has one, a CF mod without a
  website) → no-op, matching the reader link's own `http(s)` guard
  ([app.js:63](../../../ModpackManager/modpack_manager/web/app.js:63)).
- **Changelog fetch fails / empty** → panel shows "Changelog unavailable." /
  "No changelog provided."; the Add button is never gated on it.
- **Version dropdown still "loading…"** ([app.js:111](../../../ModpackManager/modpack_manager/web/app.js:111))
  when the user expands → the preview shows "Select a version" until `.ver-sel` has
  a real value, then fetches.
- **CurseForge preview without a numeric `id`** → guarded server-side (`int(id)`
  wrapped); returns empty `body_html`, panel shows the unavailable state.
- **Manual section + source filter** → filtering to Modrinth empties the section
  (all manual mods are CF); this is intended filter behavior, called out in §4.1.

## 10. Testing

Backend (pytest, mocked HTTP — the pattern in
[tests/test_modrinth.py](../../../ModpackManager/tests/test_modrinth.py) /
[tests/test_curseforge.py](../../../ModpackManager/tests/test_curseforge.py)):

- `modrinth.project_changelog` happy path → `version`, `date`, rendered `body_html`
  from a mocked `GET /version/{id}`; non-200 → all-empty object.
- `curseforge.project_changelog` → returns `_changelog`'s sanitized HTML;
  non-200 changelog → empty `body_html` (no raise).
- `real_project_changelog` dispatches on `platform` and passes the api key
  (parallels the existing `real_project_versions` coverage).

Webapp (injected fakes, matching `create_app`'s DI in
[tests/test_webapp.py](../../../ModpackManager/tests/test_webapp.py:23)):

- `GET /api/project-changelog?platform=…&id=…&ref=…` calls `changelog_fn` with the
  three args and returns its dict (a `changelog_fn` fake is added to the existing
  `_client(...)` harness, [tests/test_webapp.py:23](../../../ModpackManager/tests/test_webapp.py:23)).

Frontend has no JS runner (vanilla JS), so the three UI behaviors are verified by
running the app (`run.bat` / `run.ps1`, or the ModpackManager verify skill):
1. **Manual section** — with a known distribution-blocked CF mod in the pack,
   confirm it appears in "Needs manual update" (not the main list), its open-page
   link works, and it is still absent from the generated batch.
2. **Filter + keyboard** — type in `#updates-filter` and confirm the list + manual
   section narrow; ↑/↓/j/k move the highlight and update the reader; Space toggles
   selection; Enter opens the page; and none of these fire while typing in the box.
3. **Changelog-on-add** — search a mod, expand a result, confirm the description and
   the selected version's changelog render, and that switching versions re-fetches.

## 11. Open questions (for review)

1. **Manual list: section on Updates vs. its own tab.** This spec chooses an
   in-line collapsible **section** (§4.1) — a separate tab would re-hide the blocked
   mods behind a click, defeating the goal. Confirm the section placement (above the
   panes) reads well, or whether it should pin to the top of the list pane instead.
   Sub-decision already made: manual rows are **pulled out** of the main list rather
   than mirrored in both places.
2. **Exact keyboard scheme.** Recommended: **↑/↓ (+ j/k) move, Enter opens page,
   Space toggles selection** (§4.2). Open points: should Enter instead just *focus*
   the reader (page-open is the reader's job), and is Space worth the
   `preventDefault` scroll-suppression, or should selection stay mouse-only? A
   minimal variant is ↑/↓ + Enter only.
3. **Changelog-on-add fetch cost / endpoint.** Recommended: a **new lazy
   `/api/project-changelog`** (§5.3), one call per expand / version change.
   Alternative considered and rejected: extend `/api/project-versions` to carry
   changelogs — free for Modrinth (already in the version payload,
   [modrinth.py:62](../../../ModpackManager/modpack_manager/sources/modrinth.py:62))
   but forcing **N eager per-file calls for CurseForge**
   ([curseforge.py:83](../../../ModpackManager/modpack_manager/sources/curseforge.py:83)),
   which is why the lazy endpoint wins. Confirm the endpoint over the asymmetric
   Modrinth-inline optimization.

## 12. Deferred (v2)

- **Client-side changelog memoization** — cache `{platform,id,ref} → body_html` for
  the session so re-expanding a row doesn't refetch.
- **Keyboard nav on the Add / Remove lists** — same handler, generalized per tab.
- **Full project-body / README preview** on add, beyond the short description.
- **Keyboard-driven "select all visible"** and range-select (Shift+↓).
- **Persisted UI state** (collapse, last filter) if the app ever gains storage.
- **Error-status rows** promoted into their own surfaced section, paralleling the
  manual section, if scan-failure rates ever warrant it (out of scope here — this
  spec covers `status == "manual"` only).
