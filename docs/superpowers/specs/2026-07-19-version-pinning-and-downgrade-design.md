# Version Pinning & Downgrade (Design)

- **Date:** 2026-07-19
- **Status:** Draft for review
- **Builds on:** [2026-07-18-dependency-auto-add-design.md](2026-07-18-dependency-auto-add-design.md), [2026-07-19-close-the-loop-design.md](2026-07-19-close-the-loop-design.md)
- **Repo:** Gears & Frontiers (MCUpdater modpack, NeoForge 1.21.1)

## 1. Problem / goal

The Updates tab is a one-knob surface: each updatable mod gets a checkbox, and
checking it always targets **latest**. `renderUpdates`
([app.js:47](../../../ModpackManager/modpack_manager/web/app.js:47)) renders a
single `current → latest_version` transition, and `generate()` sends only the
mod_id ([app.js:261](../../../ModpackManager/modpack_manager/web/app.js:261)) so
the backend reaches for that candidate's `source_url`/`latest_version`
([service.py:117](../../../ModpackManager/modpack_manager/service.py:117)). The
`Candidate` dataclass itself only carries `current_version` and `latest_version`
([base.py:32](../../../ModpackManager/modpack_manager/sources/base.py:32)) — there
is no notion of "some other version."

Two real needs fall outside that knob:

1. **A latest release regressed.** The maintainer wants to move to a *specific*
   version — often an **older** one than latest, sometimes older than what's
   installed (a **downgrade**) — without leaving for a terminal to hand-write a
   Module.
2. **A mod should stop nagging.** Some mods the maintainer deliberately holds
   back (a known-good version, a compatibility freeze). Today the only lever is
   `excluded_mods` ([config.py:25](../../../ModpackManager/modpack_manager/config.py:25),
   applied in `_eligible` [updates.py:12](../../../ModpackManager/modpack_manager/updates.py:12)),
   which removes the mod from the scan **entirely** — you lose visibility that a
   held-back version even exists.

Goal: let the maintainer **target a specific version (including a downgrade)**
per update, and **pin a mod to a version** so future scans stop presenting it as
updatable — while still showing that it's pinned and to what.

## 2. Key decisions

- **A downgrade rides the update path, not the add path.** The update spec in
  `generate_events` pulls `side`, `required`, `mod_type`, `depends`, and
  `mod_path` from the existing pack module + candidate
  ([service.py:116](../../../ModpackManager/modpack_manager/service.py:116)); the
  add spec hardcodes `side="BOTH"`, `mod_type="Regular"`, `depends=""`,
  `mod_path=None` ([service.py:120](../../../ModpackManager/modpack_manager/service.py:120)).
  Modelling a downgrade as an add would silently drop a mod's `ModPath`/`depends`/
  real side. So an override is an **update carrying a chosen `{ref, url, version}`**,
  and the update branch swaps only the URL + version, keeping everything else it
  already derives from the pack.

- **Overrides are session-transient; pins are persisted.** A per-update version
  choice is a batch decision — same lifetime as `state.adds` and
  `state.selected`, cleared on reload. A **pin** is standing maintainer intent, so
  it survives restarts in a file the app owns (§2 next).

- **Pins live in an app-owned JSON sidecar, not the INI.** The INI already has an
  unused `pinned_versions =` placeholder
  ([mod_update_config.ini:11](../../../mod_update_config.ini)), but three things
  argue against using it: (a) `config.py` only ever **reads** the INI
  ([config.py:17](../../../ModpackManager/modpack_manager/config.py:17)) and
  `configparser` cannot round-trip the maintainer's hand-commented INI on write
  without dropping comments/reordering; (b) a pin needs structured data
  (`ref` + `version` + `platform`), not a flat CSV of ids; (c) `configparser`'s
  default `optionxform` lowercases option keys, which would corrupt
  case-sensitive `mod_id`s if we used a `[PINS]` section. A JSON file the app
  fully owns for read **and** write (mirroring the `HashCache` JSON pattern in
  [hashing.py]) sidesteps all three. See §6 for shape, §12 for the open question
  on git-tracking it.

- **Pin = freeze at an exact chosen version (binary suppress), not a ceiling.**
  "Don't offer past X" needs a reliable cross-scheme version comparator;
  `version_utils` only classifies severity of a known pair
  ([updates.py:8](../../../ModpackManager/modpack_manager/updates.py:8)), not a
  total order over arbitrary Modrinth/CF version strings. So v1 records the pinned
  version for **display + staleness** and treats the pin as binary: a pinned mod
  is never presented as actionable. The ceiling variant is deferred (§11).

- **`pinned` is orthogonal to `status`.** Rather than add a `"pinned"` value to
  the `ok | manual | error` status vocabulary (which would force unpin to
  remember and restore the pre-pin status), `Candidate` gets a separate `pinned`
  flag. Unpinning just clears the flag and the intrinsic `status` shows through —
  no round-trip bookkeeping.

- **Inline expander, not a modal.** The Add tab already has an inline per-row
  version `<select>` fed by `/api/project-versions`
  ([app.js:111](../../../ModpackManager/modpack_manager/web/app.js:111),
  [app.js:128](../../../ModpackManager/modpack_manager/web/app.js:128)). The
  Updates picker reuses exactly that machinery behind a per-row "Change version"
  disclosure, so the default "just take latest" path is visually unchanged and
  the complexity only appears on demand.

- **MCUpdater needs nothing special for a downgrade.** `_write_module`
  ([generate.py:38](../../../ModpackManager/modpack_manager/generate.py:38))
  writes `URL(priority=1)`, `Size`, `Required`, `ModType`, `MD5`, `Meta/version`
  identically for any version, and the layered `_merge`
  ([xml_model.py:89](../../../ModpackManager/modpack_manager/xml_model.py:89)) lets
  the imported dated file's URL/MD5 win over the installed layer. MCUpdater
  re-syncs on MD5 mismatch regardless of direction — an older jar is just a
  different MD5. Confirmed: a downgrade Module is structurally identical to an
  update Module.

## 3. Non-goals (v1)

- **No downgrade of a mod that's already on latest.** Such a mod builds no
  candidate (`build_candidate` returns `None` when on newest —
  [modrinth.py:50](../../../ModpackManager/modpack_manager/sources/modrinth.py:50),
  [curseforge.py:113](../../../ModpackManager/modpack_manager/sources/curseforge.py:113))
  so it never appears on the Updates tab. Rolling back from latest is deferred to
  a Remove-tab surface (§11, §12).
- **No version-ceiling pins** ("don't offer past X") — exact-version freeze only.
- **No auto-repin after a downgrade.** Choosing an older version for a batch does
  not implicitly create a pin; pinning is a separate, explicit control (they're
  frequently combined, but the user asks for each — §4.2).
- **No cross-scheme version ordering.** The UI never claims "this is older/newer";
  it shows the chosen version and lets MCUpdater's MD5 comparison do the work.
- **No pin-as-target retargeting.** A pin suppresses; it does not make the scan
  offer to *move* an out-of-sync pack to the pinned version (§11).

## 4. UX

### 4.1 Updates tab — per-row version picker (override)

Each actionable (`status === "ok"`) update row
([app.js:43](../../../ModpackManager/modpack_manager/web/app.js:43)) gains a small
**"Change version ▾"** control after the severity badge. Clicking it expands an
inline drawer under the row containing a version `<select>` lazily populated from
`/api/project-versions` (the Add tab's `fetchVersions`/`populateVersions`,
[app.js:128](../../../ModpackManager/modpack_manager/web/app.js:128)) — every
compatible version with its `(release/beta/alpha)` label, newest first.

- **Default (collapsed, nothing chosen):** unchanged — the checkbox targets
  latest, the row shows `current → latest_version`.
- **A non-latest version chosen:** the row's transition switches to
  `current → <chosen> ` with a neutral **"chosen"** chip, and the severity badge
  (which described `current → latest`) is **hidden** for that row — it no longer
  describes the target and could read as a downgrade "major." The checkbox stays
  checked; generate will write the chosen version.
- **Re-selecting "latest" (or collapsing) clears the override** and restores the
  default transition + badge.

The changelog reader ([app.js:62](../../../ModpackManager/modpack_manager/web/app.js:62))
mirrors the chosen target in its `current → …` heading when an override is set.

### 4.2 Updates tab — pinning

Inside the same expander, below the version select:

- **"Pin (stop future updates)"** with two forms — **Pin to current** (`c.current_version`,
  the pure stop-nagging case, no download needed) and, once a version is chosen
  above, **Pin to chosen** (`<chosen>`, the downgrade-then-freeze case). Pinning
  POSTs to `/api/pin` and persists immediately.
- Pinning **does not** disturb the current batch. The row's selection/override is
  untouched, so a "downgrade to 6.0.4 **and** pin to 6.0.4" flow generates 6.0.4
  now and the pin materialises on the **next** scan (immediately flipping the row
  to a disabled "pinned" state would silently drop it from the in-progress batch —
  rejected). A subtle "will pin to 6.0.4" acknowledgement confirms the write.

### 4.3 Updates tab — the "Pinned (N)" disclosure

Pinned mods are removed from the main actionable list (`renderUpdates` filters
`!c.pinned`) and collected in a collapsed **"Pinned (N)"** disclosure above or
below the list. It is the single home for every pin, so pins whose mod is on
latest (no candidate) are still manageable. Each row:

`AmbientSounds — pinned to 6.0.4` · (if a newer version was detected) a muted
`· 6.0.6 available` · **Unpin**.

Its rows come from the union of (pinned candidates, which carry `latest_version`
for the "available" hint) and (pins with no candidate, from the `pins` array in
the `/api/updates` payload — §6). **Unpin** POSTs `/api/unpin`; the mod returns to
the main list on the spot (§8).

### 4.4 Review & result panels

The Review panel ([app.js:230](../../../ModpackManager/modpack_manager/web/app.js:230))
and the result-modal summary
([app.js:327](../../../ModpackManager/modpack_manager/web/app.js:327)) render each
update's transition from the **effective target** (`override.version ?? c.latest_version`),
so "what will be written" stays exact for downgrades. No new sections — an
overridden update is still an update; the batch-count segments
([app.js:363](../../../ModpackManager/modpack_manager/web/app.js:363)) are
unchanged.

## 5. Architecture

### 5.1 Backend — new `pins.py`

A small module owning the sidecar, no Flask imports:

- `Pin` dataclass: `mod_id, name, platform, ref, version, url, pinned_at`.
- `load_pins(path) -> dict[str, Pin]` — returns `{}` if the file is absent
  (mirrors `load_config`'s missing-file default,
  [config.py:18](../../../ModpackManager/modpack_manager/config.py:18)).
- `save_pins(path, pins)` — atomic write (temp file + `os.replace`) so a crash
  mid-write can't corrupt the store.
- `set_pin(path, pin)` / `remove_pin(path, mod_id)` — load, mutate, save;
  return the new map.

`paths.py` gains `pins_json` on `PackPaths`
([paths.py:12](../../../ModpackManager/modpack_manager/paths.py:12)); §12 fixes its
location.

### 5.2 Backend — `Candidate` gains three fields

[base.py](../../../ModpackManager/modpack_manager/sources/base.py) `Candidate`:

- `project_id: str = ""` — the id handle `/api/project-versions` expects
  (Modrinth project id / CF numeric mod id). Needed because the picker runs off a
  `Candidate`, but today only `project_url`/`source_url` are exposed
  ([base.py:44](../../../ModpackManager/modpack_manager/sources/base.py:44)).
  Populated by both sources (§7.1).
- `pinned: bool = False`, `pinned_version: str = ""` — set by `scan()` (§7.2),
  orthogonal to `status`.

All three serialise for free via `to_dict()`/`asdict`
([base.py:46](../../../ModpackManager/modpack_manager/sources/base.py:46)).

### 5.3 Backend — `scan()` honors pins

`real_scan()` ([service.py:40](../../../ModpackManager/modpack_manager/service.py:40))
loads pins and passes them to `scan(modules, config, pins)`
([updates.py:65](../../../ModpackManager/modpack_manager/updates.py:65)). After
building candidates and before `_resolve_dependencies`
([updates.py:90](../../../ModpackManager/modpack_manager/updates.py:90)), `scan`
sets `pinned=True` + `pinned_version` on any candidate whose `mod_id` is pinned.
Pinned mods stay **eligible** (still scanned, unlike `excluded_mods`) so the
disclosure can show "newer available"; a new `pinned` rank in `_STATUS_ORDER`/sort
([updates.py:9](../../../ModpackManager/modpack_manager/updates.py:9),
[updates.py:88](../../../ModpackManager/modpack_manager/updates.py:88)) drops them
to the bottom of any residual ordering. `_resolve_dependencies` skips pinned
candidates (a pinned mod isn't being updated, so it shouldn't auto-queue deps).

### 5.4 Backend — `generate_events` consumes overrides

`generate_events(payload, candidates)`
([service.py:96](../../../ModpackManager/modpack_manager/service.py:96)) reads a new
`payload["update_overrides"]` map. In the update spec loop
([service.py:111](../../../ModpackManager/modpack_manager/service.py:111)):

```python
override = overrides.get(mid)
if not c or (c.status != "ok" and not override) or c.pinned:
    continue
url     = override["url"]     if override else c.source_url
version = override["version"] if override else c.latest_version
specs.append(("update", c.name, mid, c.side, c.required, c.mod_type,
              m.depends if m else "", m.mod_path if m else None, url, version))
```

Two deliberate changes from today's guard
([service.py:113](../../../ModpackManager/modpack_manager/service.py:113)):
an override **bypasses `status != "ok"`** (a chosen url came from
`project_versions`, which only lists downloadable files — CF blocked files are
filtered at [curseforge.py:294](../../../ModpackManager/modpack_manager/sources/curseforge.py:294)),
so a CF "manual" mod can be moved to a specific downloadable older file; and a
`pinned` candidate is skipped defensively (the frontend won't select it anyway).
Everything downstream — `compute(url)` hashing
([service.py:129](../../../ModpackManager/modpack_manager/service.py:129)),
`write_batch_xml`, `wire_into_preview`, diff/commit — is untouched.

### 5.5 Backend — webapp routes

`create_app` ([webapp.py:11](../../../ModpackManager/modpack_manager/webapp.py:11))
gains `pin_fn`, `unpin_fn`, `pins_fn`, and its `cache`
([webapp.py:14](../../../ModpackManager/modpack_manager/webapp.py:14)) gains a
`"pins"` slot:

- `GET /api/updates` — after `scan_fn()`, also loads `cache["pins"]` via
  `pins_fn()` and returns `{candidates:[…], pins:[…]}` (§6). Because `scan()`
  already stamped `pinned`/`pinned_version`, no overlay is needed on a fresh scan.
- `POST /api/pin` `{mod_id, name, platform, ref, version, url}` → `pin_fn(pin)`
  persists, then mutates the **cached** candidate in place (`pinned=True`,
  `pinned_version=version`) and refreshes `cache["pins"]` — instant, no ~30 s
  re-scan.
- `POST /api/unpin` `{mod_id}` → `unpin_fn(mod_id)`; clears the cached candidate's
  `pinned` flag and drops it from `cache["pins"]` — instant, and because `pinned`
  is orthogonal to `status`, the intrinsic status shows through cleanly (§2).

`__main__.py` ([__main__.py:14](../../../ModpackManager/modpack_manager/__main__.py:14))
wires `pin_fn=real_pin, unpin_fn=real_unpin, pins_fn=real_pins`.

### 5.6 Frontend state

Two additions to `state`
([app.js:1](../../../ModpackManager/modpack_manager/web/app.js:1)):

- `versionOverrides: {}` — `mod_id → {ref, version, url}`, session-only.
- `pins: []` — the `pins` array from `/api/updates`, for the disclosure.

Expander open/closed is transient per-render local state (no store needed).

## 6. Data shapes

```jsonc
// pins.json — app-owned, keyed by mod_id
{
  "ambientsounds": {
    "name": "AmbientSounds",
    "platform": "modrinth",
    "ref": "P7xkVdcC",                 // version id (MR) / file id (CF), from project_versions
    "version": "6.0.4",                // display + staleness label
    "url": "https://cdn.modrinth.com/.../ambientsounds-6.0.4.jar",  // for future verify/re-pin
    "pinned_at": "2026-07-19"
  }
}
```

```jsonc
// GET /api/updates response (extended)
{ "candidates": [ { /* …existing… */,
                    "project_id": "P7xkVdcC",   // NEW: id for /api/project-versions
                    "pinned": false,            // NEW
                    "pinned_version": "" } ],   // NEW
  "pins": [ { "mod_id": "ambientsounds", "name": "AmbientSounds",
              "platform": "modrinth", "version": "6.0.4", "ref": "P7xkVdcC" } ] }  // NEW
```

```jsonc
// POST /api/generate body (extended — updates stays a mod_id array)
{ "updates": ["ambientsounds", "jei", …],
  "update_overrides": {                          // NEW; absent/empty = all latest
    "ambientsounds": { "ref": "P7xkVdcC", "version": "6.0.4",
                       "url": "https://cdn.modrinth.com/.../ambientsounds-6.0.4.jar" } },
  "adds": [ /* unchanged */ ],
  "removals": [ /* unchanged */ ] }
```

```jsonc
// POST /api/pin body            // POST /api/unpin body
{ "mod_id": "ambientsounds",     { "mod_id": "ambientsounds" }
  "name": "AmbientSounds", "platform": "modrinth",
  "ref": "P7xkVdcC", "version": "6.0.4",
  "url": "https://cdn.modrinth.com/.../ambientsounds-6.0.4.jar" }
// both respond { "ok": true }  (or { "ok": false, "error": "…" })
```

The `update_overrides` map keys by `mod_id` (parallel to `updates`) rather than
reshaping `updates` into objects, keeping the existing array shape and the
`state.selected` Set intact.

## 7. Backend details

### 7.1 Exposing `project_id` for the picker

- **Modrinth** `build_candidate`
  ([modrinth.py:76](../../../ModpackManager/modpack_manager/sources/modrinth.py:76)):
  set `project_id=module.project_id` (already used to build `project_url` at
  [modrinth.py:84](../../../ModpackManager/modpack_manager/sources/modrinth.py:84)).
- **CurseForge** `build_candidate`
  ([curseforge.py:139](../../../ModpackManager/modpack_manager/sources/curseforge.py:139)):
  set `project_id=str(mod_id)`, where `mod_id` is the resolved numeric CF id
  ([curseforge.py:96](../../../ModpackManager/modpack_manager/sources/curseforge.py:96)).
  `curseforge.project_versions` already takes that numeric id
  ([curseforge.py:287](../../../ModpackManager/modpack_manager/sources/curseforge.py:287)).

No change to `/api/project-versions`
([webapp.py:44](../../../ModpackManager/modpack_manager/webapp.py:44)) or
`real_project_versions`
([service.py:86](../../../ModpackManager/modpack_manager/service.py:86)) — the
picker calls the existing endpoint with `platform` + `project_id`.

### 7.2 Pin marking in `scan()`

```python
def scan(modules, config, pins=None, max_workers=5):
    …                                   # unchanged build
    pins = pins or {}
    for c in results:
        if c.mod_id in pins:
            c.pinned = True
            c.pinned_version = pins[c.mod_id].version
    _resolve_dependencies([c for c in results if not c.pinned], config)
    …
```

`pinned` mods keep their intrinsic `status`; the frontend decides presentation
(§8). A pinned mod on latest simply built no candidate — it's covered by the
`pins` array instead.

### 7.3 Persistence fns in `service.py`

- `real_pins() -> list[dict]` — `load_pins(paths.pins_json)` → list for the API.
- `real_pin(pin: dict) -> dict` — validate `mod_id`; `set_pin(...)`; `{"ok": True}`.
- `real_unpin(mod_id: str) -> dict` — `remove_pin(...)`; `{"ok": True}`.

Errors (unwritable file, malformed input) return `{"ok": False, "error": …}`,
matching the commit/discard convention
([service.py:167](../../../ModpackManager/modpack_manager/service.py:167)).

## 8. Frontend details

- **`renderUpdates`** ([app.js:38](../../../ModpackManager/modpack_manager/web/app.js:38)):
  skip `c.pinned` rows (they go to the disclosure); for a row with an override in
  `state.versionOverrides`, render `current → <chosen>` + a `.chosen-chip` and
  omit the severity badge ([app.js:50](../../../ModpackManager/modpack_manager/web/app.js:50));
  append the **Change version ▾** toggle.
- **`toggleVersionPicker(c, rowEl)`** (new): lazy `fetchVersions({platform:c.platform, id:c.project_id})`
  ([app.js:128](../../../ModpackManager/modpack_manager/web/app.js:128)), render a
  `<select>` via `populateVersions`
  ([app.js:134](../../../ModpackManager/modpack_manager/web/app.js:134)); on change,
  set/clear `state.versionOverrides[c.mod_id]` and re-render the row. The picker
  lists all release types with their label and is **decoupled** from the Add tab's
  `state.releaseFilter` (that filter belongs to Add; reusing it here would surprise).
- **`pinMod(c, {ref, version, url})` / `unpinMod(mod_id)`** (new): POST `/api/pin`
  / `/api/unpin`, then update `state.pins` and re-render (`renderUpdates` +
  `renderPinned`).
- **`renderPinned()`** (new): renders the "Pinned (N)" disclosure from
  `state.pins`, cross-referencing `state.candidates` for the "· X available" hint,
  each row wiring **Unpin**.
- **`renderReader`** ([app.js:58](../../../ModpackManager/modpack_manager/web/app.js:58)):
  when an override exists, show the chosen target in the heading; a pinned mod (if
  the reader ever targets one) shows a "Pinned to V" note reusing the `.dep` box
  style ([style.css:42](../../../ModpackManager/modpack_manager/web/style.css:42)).
- **`load`** ([app.js:22](../../../ModpackManager/modpack_manager/web/app.js:22)):
  store `state.pins = data.pins`; auto-select still filters `status === "ok"`
  ([app.js:29](../../../ModpackManager/modpack_manager/web/app.js:29)) — pinned
  candidates are excluded from the main list so they're never auto-selected.
- **`openReview`/`resultSummaryHtml`**
  ([app.js:240](../../../ModpackManager/modpack_manager/web/app.js:240),
  [app.js:335](../../../ModpackManager/modpack_manager/web/app.js:335)): read the
  effective target `state.versionOverrides[id]?.version ?? c.latest_version`.
- **`generate`** ([app.js:257](../../../ModpackManager/modpack_manager/web/app.js:257)):
  add `update_overrides` to the payload from `state.versionOverrides`, restricted
  to currently-selected mod_ids.

### Styling

A `.chosen-chip` (neutral/accent-tinted, paralleling `.dep-chip`
[style.css:83](../../../ModpackManager/modpack_manager/web/style.css:83)); a
`.ver-picker` drawer reusing `.add-row select` styling
([style.css:78](../../../ModpackManager/modpack_manager/web/style.css:78)); a
`.pinned-list` disclosure reusing `.review-sec`/`.review-item`
([style.css:74](../../../ModpackManager/modpack_manager/web/style.css:74)); a small
pin glyph/button. Pinned rows, if ever shown inline, reuse the dimmed
`.row.manual` treatment ([style.css:33](../../../ModpackManager/modpack_manager/web/style.css:33)).

## 9. Error handling / edge cases

- **Override url unreachable at hash time** → `compute` raises, the mod lands in
  `failures`, nothing is written
  ([service.py:130](../../../ModpackManager/modpack_manager/service.py:130)) — same
  as any failed download.
- **Chosen version == latest** → a harmless no-op override; identical output to
  the default path.
- **CF older target beyond the page cap** → `_list_files` fetches at most 4×50
  files ([curseforge.py:62](../../../ModpackManager/modpack_manager/sources/curseforge.py:62)),
  so very old versions won't appear in the picker (same limit the Add tab already
  lives with). Flagged in §12.
- **Pinning a CF distribution-blocked mod** → allowed; it only silences the "needs
  manual update" nag ([curseforge.py:147](../../../ModpackManager/modpack_manager/sources/curseforge.py:147)),
  it does not conjure a download.
- **Pin whose mod is on latest** → no candidate built; managed solely from the
  `pins` disclosure.
- **Stale pin** (pack hand-edited away from the pinned version) → detectable by
  comparing `pinned_version` to the merged module version; v1 just shows both in
  the disclosure, no auto-heal.
- **Override on a pinned mod** → can't happen through the UI (pinned mods leave the
  actionable list); the generate guard skips `c.pinned` regardless (§5.4).
- **Pins file missing/malformed** → `load_pins` returns `{}`; the app runs
  pin-free, no crash.
- **Concurrent pin writes** → single local user, single-writer; atomic replace
  (§5.1) prevents a torn file.

## 10. Testing

Backend unit tests (mocked HTTP), fitting the existing `pytest` layout
([tests/test_updates.py](../../../ModpackManager/tests/test_updates.py),
[tests/test_service.py](../../../ModpackManager/tests/test_service.py),
[tests/test_webapp.py](../../../ModpackManager/tests/test_webapp.py)):

- **`pins.py`** — `save_pins`→`load_pins` round-trips a `Pin`; `load_pins` of a
  missing file returns `{}`; `set_pin`/`remove_pin` mutate + persist.
- **`scan()` honors pins** — a pinned candidate comes back `pinned=True`,
  `pinned_version=<v>`, intrinsic `status` untouched; a non-pinned one unchanged
  (extends the `Config()`-driven pattern at
  [test_updates.py:16](../../../ModpackManager/tests/test_updates.py:16)).
- **`generate_events` override** — with `update_overrides`, the built spec uses the
  override url/version, not `c.source_url`/`c.latest_version`; a non-overridden
  update is unaffected; an overridden `status="manual"` candidate is **not**
  skipped, while an un-overridden manual one still is; a `pinned` candidate is
  skipped.
- **`build_candidate` project_id** — Modrinth and CF candidates carry the id
  `/api/project-versions` expects.
- **webapp** — `GET /api/updates` returns `pins`; `POST /api/pin` calls `pin_fn`
  and flips the cached candidate's `pinned`; `POST /api/unpin` calls `unpin_fn`
  and clears it (matching the injected-fake DI already used for commit/discard).

Frontend has no JS runner (vanilla JS), so the UI is verified by running the app
(the `ModpackManager:verify` skill / `run.bat`): expand an update, pick an older
version, confirm the row shows `current → chosen` and generate writes that version
into the dated update file; pin a mod, reload, confirm it moves to "Pinned (N)"
and no longer nags; unpin and confirm it returns to the actionable list.

## 11. Deferred (v2)

- **Roll back a mod that's already on latest** — a "Change version" affordance on
  the Remove tab (the only list of *all* pack mods,
  [app.js:201](../../../ModpackManager/modpack_manager/web/app.js:201)), since such
  mods build no update candidate (§3).
- **Version-ceiling pins** ("don't offer past X") — needs a real cross-scheme
  version comparator.
- **Pin-as-target** — when the pack drifts from a pin, offer to move it *to* the
  pinned version rather than only suppressing.
- **Deeper CF history** — raise/window `_list_files` paging so old downgrade
  targets are reachable.
- **Pin staleness auto-detection + one-click heal** when `pinned_version` no longer
  matches the merged pack version.

## 12. Open questions (flag before planning)

1. **Where does `pins.json` live, and is it git-tracked?** Recommended:
   `updates/pins.json` (repo-root-relative), grouped with the update artifacts and
   **committed**, so a pin is auditable in history — consistent with the tool's
   "commit the preview" philosophy
   ([2026-07-19-close-the-loop-design.md](2026-07-19-close-the-loop-design.md)).
   Alternative: keep it untracked (personal, machine-local intent). Needs a call.
2. **Retire the INI `pinned_versions =` placeholder?** This design bypasses it
   ([mod_update_config.ini:11](../../../mod_update_config.ini)). Leave it as a
   harmless no-op, or delete it to avoid implying two pin stores?
3. **Should the Updates picker offer beta/alpha downgrade targets by default, or
   default to stable-only** (with an opt-in), given a downgrade is usually a
   stability move?
4. **Confirm exact-version-freeze is the desired pin semantic** for v1 over a
   ceiling — this is the single biggest scope lever (§2, §11).
