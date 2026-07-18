# Modpack Update Picker — Design (v1)

- **Date:** 2026-07-17
- **Status:** Approved for planning
- **Repo:** Gears & Frontiers (MCUpdater modpack, NeoForge 1.21.1)
- **Supersedes:** the all-or-nothing flow in `mod_update_automation.py`

## 1. Problem

Updating the pack today is all-or-nothing. `mod_update_automation.py` scans the
MCUpdater XML, checks Modrinth for newer versions, and writes a dated update XML
containing **every** available update. In practice not every mod can be updated
safely at once, so there's no good way to review what changed and pick a subset.

Three concrete problems:

1. **No per-mod control or changelog review.** You can't see what changed between
   your installed version and the candidate, so you can't make an informed
   per-mod decision.
2. **CurseForge never worked.** `_check_curseforge_update()` is an unimplemented
   stub that returns `None`. This is a code gap, not (only) an API-key problem —
   though the key should also be validated.
3. **MD5 hashes are wrong.** The generator writes Modrinth's **SHA-1** into the
   `<MD5>` element (`_extract_hash()` prefers sha256→sha1→md5; Modrinth only
   exposes sha1/sha512). MCUpdater compares a real MD5 of the file bytes, so it
   never matches and re-downloads. Several `<Size>` values are also wrong
   (e.g. AmbientSounds is listed at ~80 MB).

## 2. Goals (v1)

- A **local web app** that lists every mod with an available update, shows the
  **full changelog range** between installed and candidate versions, and lets you
  **pick per mod** which to update this round.
- **Generate** writes a filtered dated update XML (only selected mods) with a
  **correct MD5 and exact size**, and wires it into the **Preview pack**
  (`GearsAndFrontiers_Preview.xml`) by adding the `<Import>` and bumping the
  revision.
- **CurseForge implemented properly** alongside Modrinth.
- Reuse the existing script's proven Modrinth + XML-parsing logic; fix the bugs.

## 3. Non-goals (v1)

- No git commit/push performed by the tool.
- No editing of the **main** pack (`GearsAndFrontiers.xml`) — promotion from
  Preview to main is manual.
- No persistent "hold/pin" state — skipping a mod is per-round only.
- No downloading of all 91 jars — only the selected subset, at Generate time.
- No hosted or multi-user deployment; localhost, single user.

## 4. Key decisions (and why)

| Decision | Choice | Rationale |
|---|---|---|
| Form factor | Local web app (Python backend + browser UI) | Changelogs (Modrinth markdown, CurseForge HTML) render natively and cleanly in a browser; Tkinter can't. Reuses backend logic directly. |
| Output boundary | Write filtered XML **and** wire it into the **Preview** pack | Automates the error-prone bookkeeping (Import line + revision bump) without touching git or the main pack. |
| CurseForge | Implement properly | It's a code gap; 6 CF mods are unmanaged today. |
| Changelog depth | All intermediate versions, newest-first | A breaking change can hide in a version you'd skip past. |
| Skipping a mod | Per-round only | Simplest; no persisted state to manage in v1. |
| Layout | Master–detail two-pane (list + reader), versions in the left rail | Best for reading long multi-version changelogs while keeping the full pickable list visible. |
| Code structure | Refactor the monolith into a small package | The bugs live in the monolith; a library boundary makes them testable. Old CLI stays as a thin wrapper. |

## 5. Background: how the pack is structured

- `GearsAndFrontiers.xml` — the **main** pack users subscribe to. A `<Server>`
  with `revision` and a stack of `<Import>` elements: `base.xml`, `config.xml`,
  then dated `updates/*.xml` files. Later imports override earlier (layering).
- `GearsAndFrontiers_Preview.xml` — the **preview** pack. Structurally identical
  to main except `Server id`/`name`/`iconUrl` and its own `revision`.
- `updates/base.xml` — 91 modules (85 Modrinth, 6 CurseForge) — the baseline.
- `updates/updates-YYYY-MM-DD.xml` — dated incremental packs; each `<Module>`
  overrides the same id from earlier layers.
- `updates/local.xml`, `config.xml` — additional imported layers (note
  `local.xml` uses `<ModPath>kubejs/assets</ModPath>`).

Each `<Module>` carries: `name`, `id`, `depends`, `side` (CLIENT/SERVER/BOTH),
`<URL>` (modrinth cdn or forgecdn), optional `<ModPath>`, `<Size>`, `<Required>`,
`<ModType>` (Regular/Removal), `<MD5>`, and `<Meta>` (version, authors, etc.).

## 6. Architecture

All new work lives in a **`ModpackManager/`** subfolder at the repo root, so it's
self-contained and easy to track. It reuses the existing script's working pieces:

```
ModpackManager/
  pyproject.toml            # package metadata + deps (flask, requests, packaging, markdown, bleach)
  README.md                 # how to run
  modpack_manager/          # the importable package
    __init__.py
    __main__.py             # `python -m modpack_manager` → start server, open browser
    config.py               # read mod_update_config.ini (keys, target MC/loader, excludes)
    xml_model.py            # parse MCUpdater XML, merge layers → current state
    sources/
      __init__.py
      modrinth.py           # version listing, current→latest diff, changelogs
      curseforge.py         # NEW: real implementation (see §9)
    updates.py              # orchestrator: assemble update candidates
    hashing.py              # download jar → lowercase-hex MD5 + exact size (cached)
    generate.py             # write filtered XML; wire Import + bump revision (Preview)
    webapp.py               # Flask: GET /api/updates, POST /api/generate, serve UI
    web/
      index.html            # single page, Layout A
      app.js                # fetch + render + selection (vanilla, no build step)
      style.css
  tests/                    # pytest suite (see §11)
  cache/                    # on-disk cache of API responses + jar hashes (gitignored)
```

The tool reads and writes the pack XML at the **repo root** (`updates/`,
`GearsAndFrontiers_Preview.xml`); paths are resolved relative to the repo root,
not `ModpackManager/`, and are configurable. The existing `XMLParser`,
`ModuleAttributeMapper`, `ModrinthAPIClient`, and the XML-writing logic in
`OutputGenerator` are refactored into the modules above rather than rewritten
from scratch. The existing root-level `mod_update_automation.py` CLI can remain
as a thin wrapper over the new package (or be retired later).

**Frontend:** vanilla HTML/CSS/JS, no build toolchain. One page, two panes
(Layout A). Rationale: single-user local tool, keep dependencies minimal.

**Backend framework:** Flask. Rationale: simplest well-known option; the
concurrent API fan-out is already handled server-side by a thread pool.

## 7. Data flow

**Phase 1 — Scan (on launch):**

1. Parse `base.xml` + all imported `updates/*.xml` (+ `config.xml`, `local.xml`)
   and merge into the **current mod state** (later layer wins; `ModType=Removal`
   removes; excludes honored).
2. For each mod, query its source (Modrinth/CurseForge) for versions compatible
   with the target MC version + loader, compute the diff against the installed
   version, and fetch changelogs for **every version in between**.
3. Assemble **update candidates** (§8) and return them to the browser as JSON.
   Results are cached on disk so re-launches are fast and rate-limit-friendly.

**Phase 2 — Generate (on click):**

1. Browser POSTs the selected mod ids.
2. For **each selected mod**: download the candidate jar (streaming, to a temp
   area), compute lowercase-hex **MD5** and **exact byte size**.
3. Write `updates/updates-YYYY-MM-DD.xml` containing only the selected modules,
   with preserved attributes (§9) and correct MD5/size.
4. Insert an `<Import>` for that file into `GearsAndFrontiers_Preview.xml`
   (before `<Loader>`) and bump the Preview `revision`.
5. Return a summary (per-mod MD5/size/ok, files changed) for the UI to show,
   alongside a git-diff-style preview. The user tests the Preview pack, then
   promotes to main manually.

Generate is **transactional**: jars are downloaded and hashed first; the XML is
only written if all selected mods succeed, so a partial failure never yields a
half-written pack.

## 8. Data model

**Update candidate** (one per updatable mod; sent to the frontend):

```jsonc
{
  "mod_id": "immersiveengineering",
  "name": "Immersive Engineering",
  "platform": "modrinth" | "curseforge",
  "source_url": "https://cdn.modrinth.com/.../<new>.jar",
  "current_version": "12.4.0",
  "latest_version": "12.5.1",
  "severity": "major" | "minor" | "patch" | "unknown",
  "side": "BOTH", "required": true, "mod_type": "Regular",
  "changelogs": [                        // newest-first, every version in between
    { "version": "12.5.1", "date": "2026-07-14", "body_html": "..." },
    { "version": "12.5.0", "date": "2026-07-01", "body_html": "..." }
  ],
  "added_dependencies": [                 // required deps the new version adds
    { "id": "morered", "name": "MoreRed", "range": ">=1.5", "satisfied": false }
  ],
  "status": "ok" | "manual" | "error",   // manual = CF distribution blocked
  "note": ""                             // human-readable reason for manual/error
}
```

**Generate request / response:**

```jsonc
// POST /api/generate
{ "selected_mod_ids": ["immersiveengineering", "create", "..."] }

// response
{
  "written_file": "updates/updates-2026-07-17.xml",
  "preview_pack_updated": true,
  "new_revision": "5",
  "mods": [ { "id": "create", "md5": "…", "size": 1234567, "ok": true } ],
  "failures": []                          // any mod that failed to download/hash
}
```

## 9. Component behavior

### xml_model
- Parse with namespace awareness (reuse existing logic).
- Merge layers in import order → current state per mod id.
- **Preserve attributes** when writing updates: `side`, `Required`, `ModType`,
  `depends`, `ModPath`, and `Meta` where applicable — via the existing
  `ModuleAttributeMapper` priority logic.
- Skip `ModType=Removal` and configured excludes when checking for updates.

### sources/modrinth
- Project id + installed version id come from the CDN URL:
  `cdn.modrinth.com/data/{projectId}/versions/{versionId}/{file}`.
- `GET /v2/project/{projectId}/version?loaders=["neoforge"]&game_versions=["1.21.1"]`
  → versions. Sort by `date_published` desc.
- **Changelog range:** find the installed `versionId` in the list; take every
  version newer than it. Each version supplies `version_number`,
  `date_published`, `changelog` (markdown → rendered), `files[].hashes`,
  `dependencies`. Fallback if the installed id isn't present (old/other loader):
  compare by `date_published`, else show only the latest with a note.
- **Bulk prefilter (implemented):** before any per-mod call, one bulk pass finds
  which Modrinth mods have updates at all — `GET /v2/versions?ids=[…]` to resolve
  installed sha1 hashes (chunked ≤100), then `POST /v2/version_files/update` with
  those hashes + loader + game version. Only mods flagged as updated (or that the
  bulk pass can't resolve) get the per-mod `GET /project/{id}/version` above for
  their changelog range. Cuts a ~270-call scan to a few bulk calls + one per
  updated mod; verified live to flag the same updates as the per-mod path.

### sources/curseforge (new)
- Validate the API key first with a lightweight authenticated call (e.g.
  `GET /v1/games`); if invalid/missing, CF mods are shown as `status:"error"`
  with a clear note.
- **Recover the project id:** the forgecdn URL
  `edge.forgecdn.net/files/7568/054/<file>` encodes file id `7568054`
  (concatenate the two path groups). `POST /v1/mods/files {"fileIds":[…]}` →
  each file object has `modId`.
- **Find newer files:** `GET /v1/mods/{modId}/files?gameVersion=1.21.1&modLoaderType=6`
  (6 = NeoForge); take files newer than the installed one.
- **Changelogs:** `GET /v1/mods/{modId}/files/{fileId}/changelog` → HTML
  (sanitized before render).
- **Distribution flag:** if `GET /v1/mods/{modId}` reports
  `allowModDistribution:false` (or the file `downloadUrl` is null), mark
  `status:"manual"` — we can't fetch the jar to hash it. Optionally emit
  `<Curse project="…" file="…"/>` with empty `<MD5>` so MCUpdater resolves the
  hash itself (documented option; uniform download is the default path).
- **Bulk prefilter (implemented):** one bulk pass decides which CF mods have
  updates before any per-mod call — `POST /v1/mods/files` (installed file-ids →
  mod-ids, chunked ≤50) then `POST /v1/mods` (mod-ids → mod objects). The latest
  compatible file is read from each mod's `latestFilesIndexes` (match
  `gameVersion` + `modLoader`); a differing file-id means an update. Only updated
  (or unresolvable) mods get the per-mod file-list + changelog calls, and the
  bulk-resolved mod-id/`allowModDistribution`/website are passed into
  `build_candidate` so it skips the redundant recover + info calls. Verified live
  to flag the same updates as the per-mod path.

### updates (orchestrator)
- For each current mod, call the right source, build the candidate, compute
  **severity** from semver (major/minor/patch bump), and compute
  **added_dependencies** (required deps of the new version whose ids aren't in
  the current pack).
- Mods whose URL is neither Modrinth nor CurseForge (e.g. raw-hosted config
  files from `config.xml`) are not update-checked — they have no version source.
- Per-mod failures are isolated: one mod erroring becomes an `error` candidate,
  the scan continues. Concurrent fan-out via a thread pool + rate limiter
  (reused from the existing client).

### hashing
- Stream-download the candidate jar to a temp file; compute `hashlib.md5`
  hexdigest (lowercase) and byte size from the real file.
- On-disk cache keyed by source URL (or project+version) so regenerating the
  same selection doesn't re-download.
- **Confirmed against MCUpdater source:** `<MD5>` must be the lowercase-hex MD5
  of the raw jar bytes; MCUpdater's schema/parser support **no** other hash type
  for a module. So Modrinth's sha1/sha512 are unusable and downloading to hash
  is required. No jar normalization occurs on either side, so identical bytes →
  identical MD5 regardless of host.

### generate
- Write `updates/updates-YYYY-MM-DD.xml` — a ServerPack containing only the
  selected modules, correct `<MD5>`/`<Size>`, preserved attributes, and `<Meta>`
  version.
- **Wire into Preview:** add
  `<Import url="…/updates/updates-YYYY-MM-DD.xml">null</Import>` immediately
  before `<Loader>` in `GearsAndFrontiers_Preview.xml`, and bump the Preview
  `revision` (increment the trailing numeric component: `"4"`→`"5"`,
  `"4.3"`→`"4.4"`).
- **Idempotent per day:** if today's file/import already exists, rewrite the file
  and reuse the single existing `<Import>` rather than duplicating.
- The generated Import references the main-branch raw GitHub URL (existing
  pattern); it only goes live once the user commits and pushes.

### webapp
- `GET /api/updates` → run/scan (or serve cache) → candidates JSON.
- `GET /api/updates?refresh=1` → bypass cache and re-scan.
- `POST /api/generate` → write files, return summary.
- `GET /` → serve the single-page UI. `python -m modpack_manager` starts the
  server and opens the browser.

### web UI (Layout A)
- Toolbar: update count + selected count, severity filter, source filter,
  select-all, **Generate preview** button.
- Left rail: per-mod rows — checkbox, name, `current → new` version, severity
  badge, source tag on CurseForge rows; click selects the row for the reader.
- Right pane: stacked changelogs (newest-first) for the highlighted mod, an
  "open on Modrinth/CurseForge" link, and an inline warning for added
  dependencies. `manual`/`error` mods are visibly flagged and not selectable.
- After Generate: a summary panel (files written, per-mod MD5/size, any
  failures).

## 10. Error handling

- **Scan:** per-mod API failures isolated → `error` candidate; scan continues.
- **CF key invalid/missing:** CF mods shown as not-checked with a clear note;
  Modrinth unaffected.
- **Generate:** transactional — download+hash all selected first; write XML only
  if all succeed; report any failures without writing a partial pack.
- **Rate limiting:** preserved from the existing client; cache reduces calls.

## 11. Testing (TDD)

Unit (HTTP mocked with recorded fixtures):
- XML parse + layer merge → current state (incl. Removal, ModPath preservation).
- Semver severity classification.
- Changelog-range selection (installed id present; absent → fallbacks).
- Added-dependency computation.
- MD5 + size from a known byte blob.
- XML generation → golden-file compare.
- `<Import>` insertion + revision bump (fresh; idempotent re-run same day).

Integration:
- Fixture XML + mocked Modrinth/CF → expected candidate set.
- Generate over a selection → golden update XML + modified Preview pack.

## 12. Deferred to a later version

- Persistent hold/pin list for known-incompatible mods.
- Auto-promotion from Preview to main; optional git staging.
- Dependency **auto-add** (pulling in a newly-required dependency automatically).
- Richer diffing (config/quest file changes, not just mod versions).

## 13. Open questions / risks

- **Revision scheme:** v1 increments the trailing numeric component of the
  Preview `revision`. If a different scheme is wanted, it's a small change.
- **CF rate limits / distribution:** some CF mods block API distribution; those
  are flagged manual. Volume of CF mods is small (6), so impact is low.
- **Changelog quality:** some authors leave changelogs empty; the UI shows
  "no changelog provided" rather than hiding the version.
```
