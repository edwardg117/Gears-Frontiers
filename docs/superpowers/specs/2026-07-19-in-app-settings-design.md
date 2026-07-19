# In-app Settings — Edit Config from the UI (Design)

- **Date:** 2026-07-19
- **Status:** Draft for review
- **Builds on:** [2026-07-18-modpack-pack-manager-design.md](2026-07-18-modpack-pack-manager-design.md), [2026-07-19-close-the-loop-design.md](2026-07-19-close-the-loop-design.md)
- **Repo:** Gears & Frontiers (MCUpdater modpack, NeoForge 1.21.1)

## 1. Problem / goal

The scan/add/generate flow is fully driven from the browser, but the settings that
*govern* it still live in a file the maintainer must hand-edit. `load_config`
([config.py:17](../../../ModpackManager/modpack_manager/config.py:17)) reads
`target_minecraft_version`, `target_loader`, `excluded_mods`, and the two API keys
from [mod_update_config.ini](../../../mod_update_config.ini) via `configparser`, and
there is **no write path anywhere** in the module — the file ends at
[config.py:33](../../../ModpackManager/modpack_manager/config.py:33). So changing the
MC version, switching loader, or silencing a noisy mod's updates means: quit the app
(or not), open the INI in an editor, edit the right key in the right section, save,
and re-scan.

Two of those settings are edited often. `excluded_mods` is the "stop nagging me about
this mod" list — it's consulted on every scan by `_eligible`
([updates.py:12](../../../ModpackManager/modpack_manager/updates.py:12)), so the mod
never even appears as a candidate — yet adding to it is a text-file chore. And the
API keys are a plaintext secret sitting in a file the maintainer would rather not
open in an editor next to a screen-share.

Goal: **let the maintainer read and edit the config the app actually consumes, from
the app** — write it back to the INI safely, invalidate the cached scan so the change
takes effect, and handle the API keys without ever painting a secret into the page.

## 2. Key decisions

- **Edit only the five fields the app actually reads.** `load_config` consumes
  exactly `mc_version`, `loader`, `excluded_mods`, `curseforge_api_key`,
  `modrinth_api_key`
  ([config.py:26-32](../../../ModpackManager/modpack_manager/config.py:26)). The INI
  also carries `rate_limit_per_minute`, `request_timeout`, `pinned_versions`, and the
  whole `[UPDATE_POLICY]` / `[OUTPUT]` / `[SCANNING]` sections
  ([mod_update_config.ini:4-29](../../../mod_update_config.ini:4)) — **none of which
  `load_config` reads today.** Surfacing them would be a lie (editing them changes
  nothing), so v1 leaves them alone. They are **preserved untouched** by the write
  (§7.2), not hidden by deletion.
- **API keys are write-only. Never echo a secret to the browser.** `GET /api/config`
  reports **presence only** (`curseforge_api_key_set: true|false`), never the value.
  A key is written only when the maintainer types a replacement or explicitly clears
  it. The security tradeoff is discussed and taken in §7.4 — the short version: the
  keys are the user's own local secret, but the browser DOM is the wrong place for
  them (devtools, history, screen-share, and this repo's own screenshot-based verify
  skill all read the DOM), and presence-only costs us nothing.
- **A Settings modal, not a fourth tab.** Reuse the `.review-overlay` pattern
  ([style.css:67](../../../ModpackManager/modpack_manager/web/style.css:67)) already
  carrying `#review` and `#result`
  ([index.html:60-85](../../../ModpackManager/modpack_manager/web/index.html:60)),
  opened from a gear button in the nav. Rationale in §4.1 — settings is a
  "configure-and-leave" surface, not a step in the per-batch Updates/Add/Remove flow
  the tabs represent.
- **Partial-update writes.** `POST /api/config` applies **only the keys present in
  the body**; absent keys are left exactly as they were. This one rule serves three
  callers cleanly: the modal Save (sends whatever changed), the per-row ignore toggle
  (sends only `excluded_mods`), and the write-only keys (sent only when entered).
- **Per-mod "ignore updates" toggle wired to `excluded_mods`.** Each Updates-tab row
  gets a small mute control that appends that candidate's `mod_id` to `excluded_mods`
  and persists immediately (§4.3). It's the high-value half of the feature: excluding
  a mod is the single most common config edit, and the mod's `mod_id` is right there
  on the row. Un-ignoring happens from the modal's excluded list (an excluded mod
  isn't scanned, so it can't offer its own un-ignore control).
- **A successful save invalidates the scan cache.** All five fields change scan
  results, and the webapp caches candidates in `cache["candidates"]`
  ([webapp.py:14](../../../ModpackManager/modpack_manager/webapp.py:14)) until
  `?refresh=1` ([webapp.py:26](../../../ModpackManager/modpack_manager/webapp.py:26)).
  Because the service already reloads config fresh on every request
  ([service.py:42](../../../ModpackManager/modpack_manager/service.py:42),
  [service.py:100](../../../ModpackManager/modpack_manager/service.py:100)), the
  *only* thing standing between a saved change and a correct scan is that cache — so
  the route nulls it on success (§5.3).
- **Validate before touching the file; write atomically with a backup.** A bad
  `loader` value silently empties every CurseForge/Modrinth query (an unmapped loader
  falls back to `neoforge` id 6 on CF —
  [curseforge.py:70](../../../ModpackManager/modpack_manager/sources/curseforge.py:70)
  — and returns nothing on Modrinth), so a garbage save could make the pack look
  empty with no error. Validation rejects it up front (§7.1); the write goes to a temp
  file, is re-parsed through `load_config` before it replaces the real INI, and the
  previous file is kept as `.ini.bak` (§7.2).

## 3. Non-goals (v1)

- **No editing of the unread INI fields.** `rate_limit_per_minute`, `request_timeout`,
  `pinned_versions`, `[UPDATE_POLICY]`, `[OUTPUT]`, `[SCANNING]` are out of scope until
  something in the app actually reads them. They round-trip untouched.
- **No comment-preserving edits.** The live
  [mod_update_config.ini](../../../mod_update_config.ini) has **zero comments**; the
  `configparser` round-trip (§7.2) drops comments and normalizes whitespace, which is
  acceptable here. A comment-preserving line-editor is deferred (§12) and flagged as
  an open question (§11).
- **No secret-at-rest hardening.** Keys stay plaintext in the INI, exactly as today.
  An OS-keychain / encrypted store is a different project (§12).
- **No new-key validation against the live APIs.** We store keys as entered; we don't
  test-call CurseForge/Modrinth to prove a key works.
- **No multi-profile / multi-pack config.** One INI, one pack, as today.

## 4. UX

### 4.1 Surface — a gear in the nav, opening a modal

Add a right-aligned **⚙ button** to the `.tabs` nav
([index.html:10-14](../../../ModpackManager/modpack_manager/web/index.html:10)). It is
**not a tab** — it doesn't switch `.tab-panel`s; it opens a new `#settings`
`.review-overlay` block, a sibling of `#review` and `#result`. Reasons to prefer a
modal over a fourth tab:

- The three tabs (Updates / Add / Remove) are the **stages of assembling one batch**;
  settings is orthogonal to that flow, not a fourth stage.
- Modal semantics ("focus, change one thing, save, close") fit a low-frequency config
  surface, and the overlay CSS already exists — a tab would need a new panel layout.
- It keeps the batch footer
  ([index.html:55-58](../../../ModpackManager/modpack_manager/web/index.html:55)) and
  the 3-tab mental model intact.

### 4.2 The Settings modal

Reuses `.review-panel` / `.review-head` / `.review-foot`
([style.css:69-71](../../../ModpackManager/modpack_manager/web/style.css:69)). On
open it `GET`s `/api/config` and populates:

- **Minecraft version** — a text input, prefilled (e.g. `1.21.1`). Helper text notes
  the expected `major.minor[.patch]` shape.
- **Loader** — a `<select>` whose options are the server-supplied known set
  (`forge`, `fabric`, `quilt`, `neoforge` — §7.1), current value selected.
- **Excluded mods** — the list of currently-excluded `mod_id`s, each a removable row
  (`name ✕`, name resolved via `/api/pack` where possible — §8.3), plus a raw
  add-by-id input for ids not in the pack. This is the modal-side manager that
  complements the per-row toggle (§4.3).
- **API keys** — two rows, CurseForge and Modrinth. Each shows a **status pill**
  (`Set ✓` / `Not set`), a `password`-type input placeheld `Enter a new key to
  replace`, and a **Clear** button (disabled when already `Not set`). The existing
  value is **never** placed in the input — the field is empty on open (§7.4).

Footer: **Save** (primary, reusing `.review-foot .primary`) and **Close**. Save is
enabled only when something changed (dirty-tracking, §8.2).

**Feedback states** (mirroring the `#result` modal's inline error/success pattern,
[app.js:309-315](../../../ModpackManager/modpack_manager/web/app.js:309)):

- Saving → button disabled, "Saving…".
- Saved, scan-affecting change → success line *"Saved. Re-scanning with the new
  settings…"* and the modal triggers a refresh (§8.2).
- Validation error → inline red message under the offending field (e.g. *"Loader must
  be one of forge, fabric, quilt, neoforge."*), file untouched, nothing re-scanned.
- Write error (permissions/disk) → *"Couldn't write the config file: <error>. Your
  previous settings are unchanged."*

### 4.3 Per-mod ignore toggle (Updates tab)

Each Updates row ([app.js:40-53](../../../ModpackManager/modpack_manager/web/app.js:40))
gains a small **mute control** (a 🔕 icon button, right of the severity badge). Click:

1. `POST /api/config` with `{ "excluded_mods": [...current, mod_id] }` — the frontend
   holds the current excluded set from the last `GET /api/config` and appends this
   row's `c.mod_id`
   ([base.py:29](../../../ModpackManager/modpack_manager/sources/base.py:29)).
2. **Optimistically** drop the row from the current view and clear it from
   `state.selected` (so it leaves the batch too).
3. The backend nulls the scan cache (§5.3); the row is already gone from view, so
   **no forced 30-second re-scan** on a single ignore — the persisted change is
   already correct for the next real scan, since `_eligible` will filter it
   ([updates.py:16](../../../ModpackManager/modpack_manager/updates.py:16)).

Un-ignore is the modal's `✕` on the excluded list (§4.2). Because an un-ignored mod
isn't in the current candidate list, seeing it return requires a re-scan — so the
modal re-scans on close when the excluded set shrank (§8.2).

## 5. Architecture

### 5.1 Backend — config gains a write path

[config.py](../../../ModpackManager/modpack_manager/config.py) grows two pure helpers
alongside the existing `Config` / `load_config` (the natural home — it already owns
the INI's key/section names):

- `KNOWN_LOADERS = ("forge", "fabric", "quilt", "neoforge")` — the canonical set,
  matching CurseForge's `_LOADER_ID` keys
  ([curseforge.py:11](../../../ModpackManager/modpack_manager/sources/curseforge.py:11)).
  (Follow-up, deferred: have `_LOADER_ID` reference this constant so there's one source
  of truth — §12.)
- `validate_config_changes(changes: dict) -> list[str]` — pure; returns a list of
  human-readable errors (empty = valid). Rules in §7.1. No I/O.
- `save_config(ini_path, changes: dict) -> None` — the write. Reads the existing INI
  with `configparser(interpolation=None)`, applies only the present `changes` to
  `[API]` / `[MODPACK]`, and atomically replaces the file with a `.bak` backup (§7.2).
  Assumes its input already passed `validate_config_changes`.

### 5.2 Backend — service collaborators

[service.py](../../../ModpackManager/modpack_manager/service.py) gains two thin fns
that resolve `pack_paths().config_ini`
([paths.py:33](../../../ModpackManager/modpack_manager/paths.py:33)) and delegate,
mirroring the shape of `real_commit` / `real_discard`
([service.py:167-174](../../../ModpackManager/modpack_manager/service.py:167)):

- `real_get_config()` → loads via `load_config`, returns the **presentation dict**
  (§6): scalar fields, `excluded_mods` as a sorted list, `*_api_key_set` booleans (a
  key is "set" iff its loaded value is non-empty), and `loaders` for the dropdown.
  **Never** includes a key value.
- `real_save_config(changes)` → `config.save_config(paths.config_ini, changes)`.
  Returns `{"ok": True}`; on `OSError`, `{"ok": False, "error": ...}`. Validation is
  done in the route (§5.3) so a 400 is returned before any write is attempted.

### 5.3 Backend — webapp routes

[webapp.py](../../../ModpackManager/modpack_manager/webapp.py) `create_app` gains two
injected fns (`get_config_fn`, `save_config_fn`), following the same DI style the
`commit_fn` / `discard_fn` pair uses
([webapp.py:11-12](../../../ModpackManager/modpack_manager/webapp.py:11)):

- `GET /api/config` → `jsonify(get_config_fn())`.
- `POST /api/config` → read the JSON body; run `validate_config_changes`; on errors
  return `400 {"ok": False, "error": "; ".join(errors)}` (the same 400-on-bad-input
  shape as `/api/commit`,
  [webapp.py:65-68](../../../ModpackManager/modpack_manager/webapp.py:65)). On success
  call `save_config_fn(changes)`, then **`cache["candidates"] = None`** so the next
  `/api/updates` re-scans, and return the saver's result. Reject an empty body with
  400.

`__main__.py` ([__main__.py:14-17](../../../ModpackManager/modpack_manager/__main__.py:14))
wires `get_config_fn=real_get_config, save_config_fn=real_save_config` into the
`create_app(...)` call, exactly as `commit_fn` / `discard_fn` are wired today.

### 5.4 Frontend

A new `#settings` overlay block in
[index.html](../../../ModpackManager/modpack_manager/web/index.html) parallel to
`#review` / `#result`, a `⚙` button in `.tabs`, and a 🔕 control per Updates row. New
transient state: `state.config` (the last `GET /api/config` snapshot, incl. the
current excluded set the toggle appends to) and per-modal dirty flags. No new
persistent client state. Details in §8.

## 6. Data shapes

```jsonc
// GET /api/config  — presentation dict; NEVER contains a key value
{
  "mc_version": "1.21.1",
  "loader": "neoforge",
  "excluded_mods": ["appleskin", "someid"],   // sorted; the raw mod_ids
  "curseforge_api_key_set": true,             // presence only
  "modrinth_api_key_set": false,              // presence only
  "loaders": ["forge", "fabric", "quilt", "neoforge"]  // for the <select>
}
```

```jsonc
// POST /api/config  — PARTIAL; only present keys are written (absent = unchanged)
{
  "mc_version": "1.21.1",            // optional
  "loader": "fabric",               // optional; validated ∈ loaders
  "excluded_mods": ["appleskin"],   // optional; FULL replacement list
  "curseforge_api_key": "new-secret",   // optional; write-only; absent = unchanged
  "clear_curseforge_api_key": true,     // optional; explicit clear (unambiguous)
  "clear_modrinth_api_key": true        // optional
}
// success
{ "ok": true }
// validation failure (nothing written)
{ "ok": false, "error": "Loader must be one of forge, fabric, quilt, neoforge." }  // HTTP 400
```

**Why explicit `clear_*` flags instead of an empty string.** An empty
`curseforge_api_key: ""` is ambiguous — is it "clear it" or "I didn't touch it"?
Making *absent* mean "unchanged" and a dedicated `clear_*: true` mean "empty it"
removes the ambiguity, and lets the frontend safely omit the key field whenever the
input is blank (the common case) without risking an accidental wipe.

`excluded_mods` is sent as the **full desired list**, not a delta — it's small, and a
whole-list replacement is trivial to validate and to reason about (the modal's list
editor and the row toggle both just compute the new list and send it).

## 7. Backend details

### 7.1 Validation (`validate_config_changes`)

Pure, runs in the route before any write. Only validates keys that are **present**:

- `loader` — must be in `KNOWN_LOADERS`. This is the load-bearing guard: an unmapped
  loader silently empties scans (CF falls back to id 6,
  [curseforge.py:70](../../../ModpackManager/modpack_manager/sources/curseforge.py:70);
  Modrinth's facet/param queries just return nothing,
  [modrinth.py:28](../../../ModpackManager/modpack_manager/sources/modrinth.py:28)).
- `mc_version` — must match `^\d+\.\d+(?:\.\d+)?$` (e.g. `1.21`, `1.21.1`). We
  deliberately don't verify it's a *real* MC version (that needs a network call and
  goes stale); the regex just stops obvious garbage that would empty every scan.
- `excluded_mods` — must be a list of strings; each is trimmed, empties dropped,
  deduped (same normalization `load_config` does when parsing the comma list,
  [config.py:31](../../../ModpackManager/modpack_manager/config.py:31)). No format
  constraint — mod_ids are arbitrary XML `id` attributes.
- API keys — no format check (CF keys look like `$2a$10$…`, Modrinth keys are opaque);
  stored verbatim, whitespace-trimmed.

### 7.2 The write strategy — configparser round-trip, atomic, backed up

**Chosen approach: `configparser` round-trip**, over a targeted line-editor, because
the live INI has no comments to preserve and the round-trip is far less fragile.
Mechanics and guards:

1. `parser = configparser.ConfigParser(interpolation=None)` — **`interpolation=None`
   is required**: the CF key already contains `$`
   ([mod_update_config.ini:3](../../../mod_update_config.ini:3)) and default
   `BasicInterpolation` chokes on `%`; disabling it makes any `%`/`$` in a value safe
   to read *and* write.
2. `parser.read(ini_path)` loads **every** section — including the ones `load_config`
   ignores — so writing the parser back **preserves `[UPDATE_POLICY]` / `[OUTPUT]` /
   `[SCANNING]` / `pinned_versions` / timeouts** intact. Ensure `[API]` and
   `[MODPACK]` exist (create if the file was missing — `load_config` already tolerates
   a missing file, [config.py:19](../../../ModpackManager/modpack_manager/config.py:19)).
3. Apply present changes to the **INI's own key names**, not the dataclass names:
   `mc_version → [MODPACK] target_minecraft_version`,
   `loader → [MODPACK] target_loader`,
   `excluded_mods → [MODPACK] excluded_mods` (join the list with `, `),
   `curseforge_api_key / modrinth_api_key → [API] …` (skip if absent; set to `""` on
   the matching `clear_*` flag).
4. **Atomic + verified + backed up:** write to `ini_path + ".tmp"`, re-run
   `load_config(tmp)` and assert it reflects the intended change (self-check that we
   didn't corrupt the file), copy the current INI to `ini_path + ".bak"`, then
   `os.replace(tmp, ini_path)` (atomic on Windows and POSIX). A failure at any step
   leaves the original INI in place.

**Accepted cost:** comments are dropped and whitespace normalized (`key = value`).
The live file has none, so this is invisible today; the `.bak` makes even a surprising
round-trip recoverable. See §11 for when this stops being acceptable.

### 7.3 Cache invalidation timing

The route nulls `cache["candidates"]` **after** a successful write. Because every
service entry point reloads config fresh
([service.py:42](../../../ModpackManager/modpack_manager/service.py:42)), no process
restart is needed — the next scan simply reads the new INI. The only staleness window
is a scan already **in flight** at save time: it finishes and repopulates the cache
with the *old* config, so a save landing mid-scan may need one more Refresh to show.
On a single-user localhost tool this is acceptable and not guarded further (noted §9).

### 7.4 API-key handling — the stance and its tradeoff

**Stance: presence-only in, write-only out. The key value never crosses into the
browser.**

The counter-argument is real: these are the *user's own* keys, already sitting in
plaintext in a file on their own machine, served from `127.0.0.1`. Hiding them from
the very person who owns them can feel like security theater, and it does cost a
little UX (you can't see the current key to confirm which one is set — only that
*something* is).

We take presence-only anyway, because the DOM is a uniquely bad place for a secret
even when the secret isn't otherwise protected:

- **This repo screenshots the running app.** The ModpackManager verify skill drives
  and captures the UI; a key rendered into a field lands in a saved PNG.
- Devtools, `view-source`, autofill, browser history, and any future logging all read
  the DOM; a `password` input that's never populated leaks through none of them.
- Screen-share / shoulder-surf during a support session.
- The cost is trivial: a boolean and an empty input. There's no feature we lose except
  "reveal my key back to me," which the user can do by opening the INI.

Reinforcing rules: the `GET /api/config` payload is built from booleans, never the
value (§5.2); the `POST /api/config` route and saver **must not** log the request body
(no `print`/logging of `changes`); the input is `type="password"` and empty on open.

## 8. Frontend details

### 8.1 Opening & populating

- **`openSettings()`** — `GET /api/config`, stash the result in `state.config`,
  populate the fields (§4.2), set the loader `<select>` options from
  `config.loaders`, render status pills from `*_api_key_set`, leave key inputs empty,
  render the excluded list (§8.3). Show `#settings` (`hidden = false`, the same
  toggle `#review` uses, [app.js:253](../../../ModpackManager/modpack_manager/web/app.js:253)).

### 8.2 Saving

- **`saveSettings()`** — build a **partial** payload: include `mc_version` / `loader`
  only if changed; `excluded_mods` only if the list changed; a key only if its input
  is non-empty; a `clear_*` flag only if Clear was clicked. POST it.
  - `400` → render the error inline; leave the modal open; nothing changed.
  - `ok` → show "Saved"; if any scan-affecting field changed (all five are), close the
    modal and call `load(true)`
    ([app.js:22](../../../ModpackManager/modpack_manager/web/app.js:22)) to re-scan
    with `?refresh=1`. Refresh `state.config` from the response's implied new state.
- Dirty-tracking gates the Save button so an unchanged modal can't fire an empty POST
  (defense-in-depth alongside the route's empty-body 400).

### 8.3 Excluded-list name resolution

The excluded list holds raw `mod_id`s; excluded mods aren't scanned, so we have no
name from candidates. Resolve names best-effort from `/api/pack`
([webapp.py:30-32](../../../ModpackManager/modpack_manager/webapp.py:30)), whose
entries carry `{mod_id, name}` for every installed mod
([service.py:50-51](../../../ModpackManager/modpack_manager/service.py:50)) — the pack
is already loaded eagerly on startup
([app.js:414](../../../ModpackManager/modpack_manager/web/app.js:414)). An id with no
pack match renders as the bare id.

### 8.4 The row toggle

- **`ignoreMod(mod_id)`** — POST `{ excluded_mods: [...state.config.excluded_mods,
  mod_id] }`; on ok, update `state.config.excluded_mods`, remove the candidate from
  `state.candidates` + `state.selected`, and re-render Updates/queue/batch
  ([app.js:75-78](../../../ModpackManager/modpack_manager/web/app.js:75) is the
  existing toggle-and-rerender shape to follow). No forced re-scan (§4.3).

### Styling

Reuse `.review-overlay` / `.review-panel` / `.review-head` / `.review-foot`
([style.css:67-71](../../../ModpackManager/modpack_manager/web/style.css:67)); the
key inputs reuse `.commit-message`'s input styling
([style.css:104](../../../ModpackManager/modpack_manager/web/style.css:104)); the
Clear button reuses `.btn-danger`
([style.css:106](../../../ModpackManager/modpack_manager/web/style.css:106)); the
`Set ✓` / `Not set` pills reuse the `.badge` shape
([style.css:27](../../../ModpackManager/modpack_manager/web/style.css:27)) (green
`--patch` for set, muted for not-set). The gear and 🔕 buttons reuse the transparent
`.tab` / icon-button styling already in the nav and rows. All field escaping goes
through the existing `esc()`
([app.js:8](../../../ModpackManager/modpack_manager/web/app.js:8)).

## 9. Error handling / edge cases

- **Invalid loader / mc_version** → `400`, file untouched, inline field error (§4.2).
- **Empty POST body** → `400` (defense-in-depth behind the dirty-gated Save button).
- **INI file missing entirely** → `save_config` creates `[API]`/`[MODPACK]` with the
  provided values; consistent with `load_config` tolerating a missing file
  ([config.py:19](../../../ModpackManager/modpack_manager/config.py:19)).
- **Write fails (permissions / disk full)** → the temp-file + `os.replace` strategy
  means the real INI is never half-written; return `{ok:false,error}`, original intact.
- **`$` / `%` in a key value** → handled by `interpolation=None` on both read and write
  (§7.2).
- **Save lands mid-scan** → the in-flight scan may repopulate the cache with old
  config; one extra Refresh resolves it (§7.3). Not guarded on a single-user tool.
- **Ignoring a mod that's currently selected in the batch** → the toggle also removes
  it from `state.selected`, so it can't be generated after being excluded.
- **Un-ignoring from the modal** → the mod returns only on the next scan; the modal
  re-scans on close when the excluded set shrank (§8.2).
- **Comment/formatting loss on round-trip** → invisible today (no comments in the live
  file), recoverable via `.bak`; escalation path in §11.
- **Bad save silently emptying scans** → prevented by loader/mc_version validation
  *before* the write, plus the post-write `load_config` self-check (§7.2).

## 10. Testing

`config.save_config` / `validate_config_changes` unit tests (pytest, using the
existing `ini_file` fixture,
[tests/conftest.py:6](../../../ModpackManager/tests/conftest.py:6), and the
round-trip assertion style of
[tests/test_config.py](../../../ModpackManager/tests/test_config.py)):

- **Partial write preserves the rest:** save only `{loader: "fabric"}`; assert
  `load_config` sees `fabric` **and** that `[UPDATE_POLICY]`, `[OUTPUT]`, `[SCANNING]`,
  `pinned_versions`, `rate_limit_per_minute` are all still present and unchanged.
- **CF key with `$` round-trips** (write a new `curseforge_api_key`, re-load, assert
  equal) — proves `interpolation=None`.
- **Key write semantics:** absent key field leaves the existing key; a present key
  replaces it; `clear_curseforge_api_key: true` empties it; each verified through
  `load_config`.
- **excluded_mods normalization:** whitespace/dupes/empties in the list collapse the
  same way `load_config`'s parse does.
- **Backup + atomicity:** after a save, `.bak` exists with the pre-save content; a
  simulated write error leaves the original INI intact.
- **Validation:** bad loader and malformed mc_version each return an error string;
  valid inputs return `[]`.

Webapp tests (injected fakes, matching the `create_app` DI in
[tests/test_webapp.py](../../../ModpackManager/tests/test_webapp.py:23)):

- `GET /api/config` returns the presentation dict and **carries no key value** (assert
  the serialized body contains neither key string).
- `POST /api/config` with a bad loader → `400`, `save_config_fn` **not** called.
- `POST /api/config` valid → `save_config_fn` called with the partial changes, and
  **`cache["candidates"]` is nulled** (assert a subsequent `/api/updates` re-invokes
  `scan_fn`).

Frontend has no JS runner (vanilla JS), so the modal is verified by running the app
via the ModpackManager verify skill: open Settings, change the loader and Save,
confirm a re-scan fires; set a CF key, confirm the status flips to `Set ✓` **and the
value never appears** in the field, the DOM, or the `/api/config` response; Clear it
and confirm `Not set`; on the Updates tab, 🔕 a mod, confirm it drops from the list and
reappears in the modal's excluded list, and that reopening the app still excludes it
(persisted to the INI).

## 11. Open questions

1. **Which fields are editable — settle the `pinned_versions` case.** v1 edits the
   five fields `load_config` reads. `pinned_versions` is the tempting sixth: it lives
   in `[MODPACK]` right next to the others and is clearly config-shaped, but
   `load_config` **doesn't read it**, so exposing it needs a parallel change to the
   scan (pin a mod to a version) — a real feature, not a settings-panel line. Confirm
   we're happy deferring it (§12) vs. pulling that scope in.
2. **API-key handling — is presence-only the agreed stance?** §7.4 argues for it and
   takes it. The dissent (they're the user's own keys, on localhost, already
   plaintext) is legitimate; if the maintainer would rather *see* the current key to
   confirm it, that overturns the core decision. Flagged for explicit sign-off.
3. **`configparser` round-trip vs. targeted line-edit.** The round-trip preserves all
   unread *sections/keys* but **drops comments and normalizes formatting**. The live
   INI has no comments, so this is a non-issue *today* — but the shipped
   [mod_update_config.ini.example](../../../mod_update_config.ini.example) is
   comment-heavy, and a maintainer who ever pastes those comments into their real file
   would lose them on first save. Decision needed: accept the round-trip (with `.bak`)
   as specified, or invest in a comment-preserving line-editor now (§12). Recommend:
   round-trip now, revisit only if comments appear.
4. **Could a bad save break scans, and is the guard enough?** An invalid `loader` is
   the sharp edge (silently empties scans). The spec guards it three ways —
   pre-write validation, a post-write `load_config` self-check, and `.bak` — which we
   believe is sufficient; confirm no additional "settings sanity" gate (e.g. a dry-run
   scan after save) is wanted before it's considered safe.
5. **Modal vs. tab.** §4.1 recommends the modal. If the maintainer expects settings to
   be a persistent, always-visible surface (rather than a focused pop-over), a fourth
   tab is the alternative — worth a one-line confirmation since it changes the nav.

## 12. Deferred (v2)

- **Editing the unread INI fields** (`rate_limit_per_minute`, `request_timeout`,
  `[UPDATE_POLICY]`, `[OUTPUT]`, `[SCANNING]`) — only once the app reads them; editing
  inert settings is worse than not offering them.
- **`pinned_versions` end-to-end** — surface it *and* teach the scan to honor pins.
- **Comment-preserving writer** — a line-level editor that rewrites only the changed
  keys, if/when the live INI grows comments.
- **Single source of truth for loaders** — have
  [curseforge.py](../../../ModpackManager/modpack_manager/sources/curseforge.py:11)
  `_LOADER_ID` reference `config.KNOWN_LOADERS`.
- **Secret-at-rest hardening** — OS keychain / encrypted store instead of plaintext INI.
- **Live key validation** — a "Test key" button that makes one authenticated probe per
  platform and reports whether the key works.
- **Config change history / undo** beyond the single `.bak`.
