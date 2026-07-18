# Dependency Auto-Add (Design)

- **Date:** 2026-07-18
- **Status:** Approved for planning
- **Builds on:** [2026-07-18-modpack-pack-manager-design.md](2026-07-18-modpack-pack-manager-design.md)
- **Repo:** Gears & Frontiers (MCUpdater modpack, NeoForge 1.21.1)

## 1. Problem / goal

Some updates introduce a **new required dependency** that isn't in the pack yet.
Today the scan detects this (Modrinth only) and the changelog reader shows an
orange warning banner — but the user then has to switch to the Add tab, search
for that dependency, pick a version, and queue it by hand.

Goal: when a new required dependency is detected, **automatically queue the
latest compatible version of it** in the Add tab's "Queued to add" section, each
auto-added dependency carrying a **chip that names the mod(s) it's a new
dependency for**.

## 2. Key decisions

- **Reactive, selection-driven queue.** Auto-added dependencies are a *derived*
  view of the currently **selected** updates. On load all updatable mods are
  selected, so their new deps are all queued. Deselect an update on the Updates
  tab and any dependency queued *only* because of it drops out; re-select it and
  the dependency comes back **instantly, with no re-fetch** (the resolved spec is
  cached in `state.candidates` for the whole session — see §5.1).
- **Backend resolves the add-spec during scan.** The scan resolves each new dep
  to a full, queueable spec (slug, latest compatible version, download URL, side,
  size) and attaches it to the candidate. This keeps all Modrinth API logic in
  the source layer and makes the session-cache behavior above fall out for free.
- **Auto-deps are governed by update selection, not a per-row ✕.** An update
  genuinely needs its required dep, so auto-dep rows have **no remove button**;
  you drop one by deselecting its update. To use a *different* version, manually
  search + add it — the auto-dep dedupes out (§8).
- **Chip = one per requiring mod.** A dependency needed by two selected updates
  shows as **one queue row with two chips**. Chips are orange-tinted to echo the
  dependency warning banner.
- **Modrinth-scoped.** New-dependency detection exists only for Modrinth
  ([modrinth.py](../../../ModpackManager/modpack_manager/sources/modrinth.py)
  `build_candidate`); CurseForge candidates always carry `added_dependencies=[]`
  and the banner never renders for them. This feature therefore covers Modrinth
  deps only, matching where the warning already appears.

## 3. Non-goals (v1)

- **No transitive resolution.** Only the *direct* new required deps of an updated
  mod are queued. A dep's own new deps are not chased.
- **No CurseForge dependency detection.** Unchanged; out of scope (§11).
- **No per-row version picker on auto-deps.** Auto-deps always take the latest
  compatible version. Want a specific version? Add it manually.
- **No "optional" deps.** Only `required` dependencies are considered, exactly as
  the current detection does.

## 4. UX

### 4.1 Add tab — Queued to add
The existing "Queued to add" list renders **auto-added deps first**, then manual
adds. An auto-dep row shows: platform pill (MR), name, resolved version,
**open-page ↗**, and **one chip per requiring mod** (`dep of <ModName>`). It has
**no ✕** (manual add rows keep theirs). The list header count
(`Queued to add (N)`) and the footer batch summary count auto-deps + manual adds
together.

### 4.2 Updates tab — changelog banner
The orange banner ([app.js:66](../../../ModpackManager/modpack_manager/web/app.js:66))
is updated to reflect the auto-add:
- **addable** → `⚠ New required dependency: <b>Name</b> (version) — added to the Add queue`
- **not addable** → `⚠ New required dependency: <b>Name</b> — not in your pack; add it manually`

("addable" = the scan resolved a compatible latest version; see §7.)

### 4.3 Review batch panel
The Review panel's **Adds** section
([app.js `openReview`](../../../ModpackManager/modpack_manager/web/app.js:189))
includes auto-deps alongside manual adds, so it remains an exact "what will be
written" list. Auto-dep entries show their requiring-mod chip(s) and have **no
remove control** (consistent with §2 — remove by deselecting the update).

## 5. Architecture

### 5.1 Frontend state
No new stored collection — auto-deps are **derived**, keeping the cache-on-reselect
behavior trivially correct:
- `candidates` (existing) now carry enriched `added_dependencies` (§6). This is
  the session cache: it persists across selection toggles, so re-selecting an
  update re-derives its dep with zero network calls.
- `computeAutoDeps()` (new, pure) walks `candidates`, keeps only those whose
  `mod_id` is in `selected`, collects each candidate's `addable` deps, **dedupes
  by slug**, **merges requiring-mod names**, and **skips** any slug already in
  `adds` (manual) or already present in `pack`. Returns
  `[{ dep, requiredBy: [name, …] }]`.
- The queue render, batch count, review panel, and generate payload all read from
  `computeAutoDeps()` + `adds`.

### 5.2 Backend
- [base.py](../../../ModpackManager/modpack_manager/sources/base.py) —
  `AddedDependency` gains `slug`, `side`, `version`, `download_url`, `size`,
  `addable` (§6).
- [updates.py](../../../ModpackManager/modpack_manager/updates.py) —
  `_resolve_dependency_names` becomes `_resolve_dependencies`: it gathers every
  unsatisfied dep id across the Modrinth candidates and fills the new fields in
  one enrichment pass. Runs only when new deps exist. Best-effort: any dep it
  can't fully resolve is left `addable=False` (banner still shows, not queued).
- [modrinth.py](../../../ModpackManager/modpack_manager/sources/modrinth.py) —
  new `resolve_dependencies(dep_ids, mc_version, loader, api_key)` (§7). No
  webapp/route/service signature changes — enrichment happens inside the existing
  `scan()` path, and the enriched fields ride along in the existing
  `GET /api/updates` payload via `Candidate.to_dict()`.

## 6. Data shapes

```python
# base.py — AddedDependency (extended; existing fields unchanged)
@dataclass
class AddedDependency:
    id: str                     # Modrinth project id (existing)
    satisfied: bool             # existing; always False for detected new deps
    name: str | None = None     # existing; project title
    url: str = ""               # existing; project page (for the "open" link)
    slug: str = ""              # NEW: used as the add's module_id
    side: str = "BOTH"          # NEW: CLIENT | SERVER | BOTH (detected)
    version: str = ""           # NEW: resolved latest compatible version name
    download_url: str = ""      # NEW: primary-file jar URL to hash/add
    size: int | None = None     # NEW: primary-file size (bytes)
    addable: bool = False       # NEW: True once resolved to a queueable spec
```

```jsonc
// Auto-dep -> AddSpec sent in POST /api/generate "adds" (same shape manual adds use)
{ "platform": "modrinth", "module_id": "<dep.slug>", "name": "<dep.name>",
  "version": "<dep.version>", "url": "<dep.download_url>",
  "side": "<dep.side>",        // detected CLIENT|SERVER|BOTH, not hardcoded
  "required": true }
```

The `POST /api/generate` body is unchanged — auto-deps are just extra entries in
the existing `adds` array, which `real_generate`'s add branch already handles.

## 7. Backend details — `modrinth.resolve_dependencies`

Input: the set of unsatisfied dep project ids, plus `mc_version`, `loader`,
`api_key`. Output: `{ dep_id: {name, slug, side, version, download_url, size,
addable} }`.

1. **Bulk project meta** — one `GET /v2/projects?ids=[…]` (reusing the pattern in
   the current `resolve_project_names`): for each project take `title` → name,
   `slug`, and `client_side`/`server_side` → side via the existing `_detect_side`.
2. **Latest compatible version per dep** — concurrently (a `ThreadPoolExecutor`,
   as `scan()` already uses), for each dep id call the existing `_fetch_versions`
   (filtered by `game_versions`/`loaders`), sort by `date_published` desc, take
   the newest, then `_primary_file` → `download_url` + `size`, and
   `version_number` → version.
3. **addable** = project meta present **and** a `download_url` was found.

Failure isolation: the bulk-meta call and each per-dep version fetch are wrapped
independently. A dep with no compatible version, a distribution issue, or a
network error resolves to `addable=False` — the reader still shows the warning,
and it simply isn't queued. This mirrors the per-mod isolation already in
`scan()`/`_check`.

`updates._resolve_dependencies` then copies these fields onto each
`AddedDependency` on each candidate (matching by `id`).

## 8. Frontend details

- **`computeAutoDeps()`** — pure; described in §5.1. Dedupe key = `slug`. A dep is
  skipped if `!dep.addable`, if its slug matches any `adds[].module_id` (manual
  add wins), or if its slug matches a `pack` entry's `mod_id` (belt-and-suspenders;
  detected deps are `satisfied=False` so this is rare).
- **`renderQueue()`** — renders `computeAutoDeps()` rows (chips, no ✕) above the
  existing manual-add rows; sets the header count to auto + manual.
- **Recompute wiring** — call the queue render (and `updateBatch`) from
  `toggleUpdate`, the **Select all** handler, and `load` (after `selected` is
  populated), plus the existing manual add/remove paths, so the derived queue
  tracks selection live.
- **`batchCounts()` / `updateBatch()`** — adds count = `adds.length +
  computeAutoDeps().length`.
- **`generate()`** — `payload.adds` = manual adds (existing mapping) concatenated
  with `computeAutoDeps()` mapped to the AddSpec in §6.
- **`openReview()`** — Adds section includes auto-deps (chips, no remove control).
- **Banner** — `renderReader` dep line uses the §4.2 text based on `dep.addable`.

### Styling
A `.dep-chip` pill: small, pill-radius, orange-tinted
(`rgba(255,159,10,.16)` bg / `--minor` text) to match the dependency banner —
paralleling the existing `.badge.minor`. Chips sit in a `.dep-chips` row under the
mod name inside the queue row's `.main`.

## 9. Error handling / edge cases

- **Dep unresolvable** (`addable=False`) → not queued; banner says "add it
  manually" (§4.2).
- **Dep required by multiple selected updates** → one queue row, one chip per
  requiring mod.
- **Dep already queued manually** (same slug) → auto-dep deduped out; the manual
  entry (user-chosen version) stands.
- **Dep already in the pack** → skipped (shouldn't occur for `satisfied=False`
  deps, but guarded).
- **All requiring updates deselected** → dep leaves the queue; its resolved spec
  stays cached on the candidate, so re-selecting re-queues it with no fetch.
- **Scan finds no new deps** → enrichment pass is a no-op; behavior unchanged.

## 10. Testing

Backend unit tests (mocked Modrinth HTTP), fitting the existing `pytest` setup:
- `resolve_dependencies` happy path → fields populated, `addable=True`, side
  detected from `client_side`/`server_side`.
- Multi-requirer: two candidates share a dep id → both get the enriched fields;
  the derived-queue dedupe/merge is exercised at the JS layer, so the Python test
  asserts enrichment only.
- Failure isolation: version fetch raises / no compatible version / no primary
  file → `addable=False`, name still filled from bulk meta.
- Bulk-meta failure → deps left `addable=False`, name falls back to id.
- `_resolve_dependencies` maps enriched fields onto the right candidate by dep id.

Frontend has no JS test harness (vanilla JS, no runner), so the UI is verified by
running the app (`run.bat` / `run.ps1`): trigger a scan with a known
new-dependency update, confirm the dep appears in "Queued to add" with the correct
chip, that deselecting/re-selecting the update removes/restores it without a
reload, and that Generate writes the dependency into the dated update file.

## 11. Deferred (v2)

- **Transitive dependency resolution** (chase a queued dep's own new deps).
- **CurseForge dependency detection** (populate `added_dependencies` for CF
  candidates via the CF files' `dependencies`, then feed the same pipeline).
- **Optional-dependency prompts** (offer, don't auto-queue).
- **Per-row version override** on an auto-dep without dropping to manual search.
