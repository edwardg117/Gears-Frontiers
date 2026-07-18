# Modpack Pack Manager — Add & Remove Mods (Design)

- **Date:** 2026-07-18
- **Status:** Approved for planning
- **Builds on:** [2026-07-17-modpack-update-picker-design.md](2026-07-17-modpack-update-picker-design.md)
- **Repo:** Gears & Frontiers (MCUpdater modpack, NeoForge 1.21.1)

## 1. Problem / goal

The update picker only updates mods that are already in the pack. This extends it
into a **pack manager**: also **add** new mods and **remove** existing ones, from
the same UI, all funnelling into the existing "generate → preview pack" pipeline.

## 2. Key decisions

- **Three tabs — Updates / Add / Remove** — above the current picker area.
- **One shared batch.** Selections across all three tabs accumulate into a single
  pending-changes batch (shown in a footer bar). One **Generate preview** writes
  everything into a single `updates/updates-YYYY-MM-DD.xml`, with one `<Import>`
  and one revision bump on the Preview pack — exactly the existing generate flow.
- **Add = paste + search, both platforms.** Paste a Modrinth/CurseForge link or
  id, or search by name. A **platform filter** (Both / Modrinth / CurseForge) and
  a **release-type filter** (all / stable / beta / alpha) narrow results and
  versions. Each result and each queued item has an **open-page ↗** button.
- **Remove = current-pack list.** Lists the merged pack (minus config files and
  already-removed mods); check mods to remove → each becomes a URL-less
  `<ModType>Removal</ModType>` entry.
- **Review batch panel.** The footer bar is clickable → a consolidated review of
  every queued update, add, and removal (each removable) with the final Generate
  button.

## 3. Non-goals (v1)

- No dependency **auto-add** — added/updated mods still only *warn* about missing
  required deps (as the update picker does).
- No editing of arbitrary module attributes in the UI beyond `side`/`Required` on
  an add. `ModPath`/`depends` on added mods default empty.
- No CF search sorting/pagination niceties beyond the first page of results.

## 4. UX

### 4.1 Tab bar + shared batch footer
A tab bar (Updates / Add / Remove) sits above the panes. A persistent footer shows
`Review batch · N updates · M adds · K removals` (a button) on the left and
**Generate preview** on the right — visible on every tab. Clicking the review
button opens the Review panel (§4.5).

### 4.2 Updates tab
Unchanged — the existing two-pane picker. Its checked mods are the "updates" part
of the batch.

### 4.3 Add tab
- **Search box** — paste a link/id, or type a name; searches on submit (Enter),
  not per keystroke.
- **Filters** — Platform (Both / Modrinth / CurseForge) selects which API(s) to
  query; Release type (all / stable / beta / alpha) narrows each result's version
  dropdown. Defaults: Both platforms, all release types.
- **Results** — each row: icon/initial, name, one-line summary, platform pill,
  **open-page ↗**, a **version dropdown** (every version labeled with its type,
  e.g. `0.5.8 (release)`, filtered by the release-type filter, default = newest
  matching), and an **Add** button.
- **On Add** — the mod joins the queue with its chosen version. `side` is
  auto-detected for Modrinth (from `client_side`/`server_side`), defaults BOTH
  otherwise; `Required` defaults true. If the mod is already in the pack, it's
  flagged ("already installed — update it from the Updates tab") rather than
  double-added.
- **Queued to add** — a list below the results: platform pill, name, chosen
  version, **open-page ↗**, remove ×.

### 4.4 Remove tab
Lists the current pack (merged state, excluding config-file modules and modules
already `ModType=Removal`) with a **text filter** and the same **platform filter**.
Each row is a checkbox; checked rows are the "removals" part of the batch.

### 4.5 Review batch panel
Opened from the footer. A faux-viewport panel listing three sections — Updates,
Adds, Removals — each item with its key facts and a remove control, plus the
**Generate preview** button. This is the single "exactly what will change"
confirmation before writing the file.

## 5. Architecture

### 5.1 Frontend
One tabbed page (still vanilla HTML/CSS/JS, no build). Client state:
- `updates`: the scanned candidates + `selected` set (existing).
- `adds`: list of `AddSpec` (queued adds).
- `removals`: set of pack mod-ids to remove.
The batch counts and Review panel derive from these three.

### 5.2 Backend endpoints (Flask)
- `GET /api/updates` — existing scan.
- `GET /api/pack` — current pack mods for the Remove tab: `[{mod_id, name,
  version, platform, side}]` (merged state, minus config + removals).
- `GET /api/search?q=&platform=` — search Modrinth and/or CurseForge; returns
  `SearchHit`s (below). `platform` ∈ `both|modrinth|curseforge`.
- `GET /api/resolve?ref=` — a pasted link/slug/id → one `SearchHit` (the project).
- `GET /api/project-versions?platform=&id=` — `{side, versions}` where each
  version is `{ref, name, type, url}`, `type ∈ release|beta|alpha`, `url` is the
  jar download URL, and `side` is the project's detected side.
- `POST /api/generate` — extended body `{updates:[mod_id], adds:[AddSpec],
  removals:[mod_id]}`.

### 5.3 New source functions
- `modrinth.search(q, mc_version, loader)` → hits; `modrinth.resolve(ref)` →
  project id from a link/slug/id; `modrinth.project_versions(id, mc, loader)` →
  versions with `version_type` and `client_side/server_side` for side detection.
- `curseforge.search(q, mc_version, loader)` → hits;
  `curseforge.resolve(ref)` → modId (numeric id, or slug via
  `GET /v1/mods/search?slug=`); `curseforge.project_files(mod_id, mc, loader)` →
  files with `releaseType`.

## 6. Data shapes

```jsonc
// SearchHit
{ "platform": "modrinth", "id": "AANobbMI", "slug": "sodium",
  "name": "Sodium", "summary": "…", "icon_url": "…", "page_url": "https://…" }

// version option (from /api/project-versions)
{ "ref": "<version_id or file_id>", "name": "0.5.8", "type": "release",
  "url": "https://…jar" }

// AddSpec (client -> POST /api/generate)
{ "platform": "modrinth", "module_id": "sodium", "name": "Sodium",
  "version": "0.5.8", "url": "https://…jar",
  "side": "BOTH", "required": true }

// POST /api/generate
{ "updates": ["create", "jei"],
  "adds": [ AddSpec, … ],
  "removals": ["farsight", "customnpcs"] }
```

## 7. Backend details

- **Modrinth search:** `GET /v2/search?query={q}&limit=20&facets=[["project_type:mod"],["categories:{loader}"],["versions:{mc}"]]`
  → hits with `project_id`, `slug`, `title`, `description`, `icon_url`; page_url =
  `https://modrinth.com/mod/{slug}`.
- **Modrinth resolve:** accept `modrinth.com/mod/{slug}`, a bare slug, a project
  id, or a `cdn.modrinth.com/data/{id}/…` URL → project id → project info.
- **Modrinth versions + side:** reuse the version list (`version_number`,
  `version_type`, `files`, `date_published`); the project's `client_side` /
  `server_side` (`required|optional|unsupported`) map to `CLIENT`/`SERVER`/`BOTH`.
- **CurseForge search:** `GET /v1/mods/search?gameId=432&searchFilter={q}&gameVersion={mc}&modLoaderType={id}&pageSize=20`
  → hits with `id`, `slug`, `name`, `summary`, `logo.url`, `links.websiteUrl`.
- **CurseForge resolve:** `curseforge.com/minecraft/mc-mods/{slug}` → slug →
  `GET /v1/mods/search?gameId=432&slug={slug}` → modId; or a numeric id directly.
- **CurseForge versions:** `GET /v1/mods/{modId}/files?gameVersion=&modLoaderType=`
  (the paginated `_list_files`), `releaseType` 1/2/3 → release/beta/alpha; side
  defaults BOTH.

## 8. Generate changes

`generate.write_update_xml` currently writes one module per selected update. It
becomes op-aware, handling three op kinds in one dated file:

- **update** — existing candidate; download the selected jar → real MD5 + size,
  preserve `side`/`Required`/`ModType`/`depends`/`ModPath` from the current module
  (unchanged behavior).
- **add** — a new module from an `AddSpec`: download the spec's `url` → real MD5 +
  size; module `id` = `module_id` (the platform slug, lowercased, hyphens kept),
  `name` = the spec name, `side`/`Required` from the spec, `ModType=Regular`,
  `depends`/`ModPath` empty; `Meta/version` = the spec `version`.
- **removal** — a minimal `<Module id="…" side="…"><ModType>Removal</ModType></Module>`
  (no URL/Size/MD5, no download); `side` from the current pack module.

Generate stays **transactional** — all adds/updates are downloaded and hashed
first; the file is only written if all succeed; failures are reported per-item.
Preview wiring (`<Import>` + revision bump) is unchanged.

## 9. Error handling

- Search/resolve failures surface in the tab (not silent); an unrecognized paste
  shows "couldn't recognize that link or id".
- Adding a mod already present in the pack → flagged, not double-added.
- A removal whose id isn't in the current pack → skipped with a note.
- Download/hash failure on an add at generate → per-item failure, nothing written
  (same transactional guarantee as updates).
- Empty batch (nothing queued anywhere) → Generate returns the "nothing selected"
  note (as today).

## 10. Testing

Unit (mocked HTTP):
- Modrinth search + CF search response parsing → `SearchHit`s.
- Resolve parsing: Modrinth link/slug/id/cdn-url; CF link→slug→modId and numeric.
- Version listing with release-type mapping (release/beta/alpha) and filtering.
- Modrinth side auto-detection from `client_side`/`server_side`.
- `generate` over a **mixed batch** (update + add + removal) → golden XML: add =
  full module with MD5/size, removal = minimal `ModType=Removal` module.
- Extended `POST /api/generate` + new routes (`/api/pack`, `/api/search`,
  `/api/resolve`, `/api/project-versions`) via the Flask test client with injected
  fakes.

## 11. Deferred (v2)

- CurseForge search paging/sorting; richer result ranking.
- Dependency auto-add (queue a mod's missing required deps in one click).
- Editing `ModPath`/`depends`/arbitrary attributes on added mods in the UI.
- Bulk add (paste a list of links).
