# Update History & Rollback — In-app History surface and layer un-apply (Design)

- **Date:** 2026-07-19
- **Status:** Draft for review
- **Relates to:** [2026-07-19-close-the-loop-design.md](2026-07-19-close-the-loop-design.md)
- **Builds on:** [2026-07-18-modpack-pack-manager-design.md](2026-07-18-modpack-pack-manager-design.md), [2026-07-17-modpack-update-picker-design.md](2026-07-17-modpack-update-picker-design.md)
- **Repo:** Gears & Frontiers (MCUpdater modpack, NeoForge 1.21.1)

## 1. Problem / goal

Every generate writes a dated `updates/updates-YYYY-MM-DD.xml` and wires an
`<Import>` into the Preview pack ([service.py:156](../../../ModpackManager/modpack_manager/service.py:156)).
Over time these accumulate: the Preview pack currently stacks nine imports —
`base`, `config`, then seven dated batches back to 2015 —
([GearsAndFrontiers_Preview.xml:4](../../../GearsAndFrontiers_Preview.xml:4)).
This *is* the pack's history, but it is only legible by reading raw XML in an
editor, and there is **no way to un-apply a batch** short of hand-editing the
Preview pack to delete an `<Import>` and re-number the revision.

Two concrete gaps:

1. **No history view.** The maintainer can't see, in-app, what each past batch
   changed (which mods it updated / added / removed) or which batches are
   actually live in the Preview vs merely sitting on disk.
2. **No rollback.** When a batch turns out bad (the `2026-05-01` Minecolonies
   compat that "bricked the save" per its own commit log is the canonical
   example), un-applying it means a manual editor trip — exactly the terminal
   detour that [close-the-loop](2026-07-19-close-the-loop-design.md) set out to
   eliminate for the forward direction.

Goal: **give the maintainer an in-app History surface** that reads the on-disk
layers and shows each batch's ops, and a **rollback** that un-applies a batch by
removing its `<Import>` from the Preview pack — reusing close-the-loop's
commit/discard machinery and preserving the same safety stance: **Preview-only,
never `main`, never push.**

## 2. Key decisions

- **The Preview `<Import>` order is the authoritative applied stack.** History is
  read from the same source `_pack_layer_paths`
  ([service.py:19](../../../ModpackManager/modpack_manager/service.py:19)) already
  parses — the `<Import url=…>` list, in order, mapped from the GitHub raw URL to
  a local path under the repo root. The `updates/` directory is *not* the source
  of truth: a dated file can exist on disk without being imported (e.g. after a
  rollback), and an import can point at a file that no longer exists. History
  surfaces **both** — the applied stack (from imports) and any unapplied dated
  files on disk (§6) — and never conflates them.

- **Ops are derived, not stored.** A written batch does **not** record whether
  each module was an *update* or an *add* — `write_batch_xml`
  ([generate.py:52](../../../ModpackManager/modpack_manager/generate.py:52))
  writes both as an identical `<ModType>Regular</ModType>` module with
  URL/Size/MD5/Meta; only `Removal` is self-describing
  ([generate.py:29](../../../ModpackManager/modpack_manager/generate.py:29)). So
  the op of each module is **reconstructed** by classifying it against the merge
  of all layers *below* it (§7.1): a `Regular` module whose `mod_id` already
  existed below is an **update**; one that didn't is an **add**; a `Removal` is a
  **removal**. This reuses the exact merge semantics `parse_packs`/`_merge`
  ([xml_model.py:120](../../../ModpackManager/modpack_manager/xml_model.py:120),
  [xml_model.py:89](../../../ModpackManager/modpack_manager/xml_model.py:89))
  already implement, so History's ops match what MCUpdater actually resolves.

- **Rollback = remove the `<Import>`, bump the revision, leave the file on disk.**
  The natural inverse of `wire_into_preview`
  ([generate.py:80](../../../ModpackManager/modpack_manager/generate.py:80)):
  delete the one import line whose URL carries that dated filename, bump the
  `<Server revision>` (forward — reuse `_bump_revision`
  ([generate.py:73](../../../ModpackManager/modpack_manager/generate.py:73)), a
  rollback still needs a *new* revision so MCUpdater clients re-sync), and write
  the Preview pack. The dated XML file is **kept** — it's on-disk history, and
  keeping it makes rollback cheap and reversible (re-applying is just re-adding
  the import). This mutates **only** `GearsAndFrontiers_Preview.xml`.

- **v1 rolls back the top of the stack only (safe LIFO).** Because `_merge`
  applies later imports over earlier ones
  ([xml_model.py:127](../../../ModpackManager/modpack_manager/xml_model.py:127)),
  removing the **topmost** dated layer reverts exactly the mods it touched to the
  state below it — no later layer exists to have re-overridden anything, so the
  merged result is precisely "as if that batch never applied." Removing a
  **middle** layer is *not* generally safe (§9), so v1 offers rollback only on
  the current top dated layer; popping it repeatedly (one commit each) covers
  "undo the last N updates." Arbitrary-layer rollback is deferred (§11).

- **Rollback reuses the close-the-loop commit/discard flow.** A rollback produces
  a single Preview-only working-tree change — exactly the shape close-the-loop
  already commits. `/api/rollback` writes the Preview pack and records
  `cache["last_touched"] = ["GearsAndFrontiers_Preview.xml"]`
  ([webapp.py:14](../../../ModpackManager/modpack_manager/webapp.py:14)); the
  existing `/api/commit` and `/api/discard`
  ([webapp.py:61](../../../ModpackManager/modpack_manager/webapp.py:61)) then
  commit or revert it unchanged. No new git code — `git_ops.diff`/`commit`/
  `discard` ([git_ops.py:26](../../../ModpackManager/modpack_manager/git_ops.py:26))
  already handle a single tracked path.

- **Git enrichment is optional and best-effort.** Each dated file maps loosely to
  the commits that touched it (`git log -- updates/updates-2026-05-01.xml` returns
  several), but the mapping is fuzzy (many commits edit one file over its life).
  History may show the introducing commit as a muted hint, computed best-effort
  like `git_ops.diff` (a git failure yields no hint, never an error). The XML is
  the source of truth; git is decoration.

## 3. Non-goals (v1)

- **No promote-to-`main`, no push.** Same stance as close-the-loop
  ([close-the-loop §3](2026-07-19-close-the-loop-design.md)) — History and
  rollback read and write **only** the Preview pack and the dated files, never
  `GearsAndFrontiers.xml`
  ([paths.py:33](../../../ModpackManager/modpack_manager/paths.py:33)).
- **No arbitrary / middle-layer rollback.** Top-of-stack only in v1 (§2, §9).
- **No file deletion on rollback.** The dated XML stays on disk; History shows it
  as an unapplied layer afterward.
- **No re-apply / re-order UI.** Re-adding a rolled-back batch is out of scope for
  v1 (it would re-import at the top, changing order — §9). Deferred (§11).
- **No batch rollback in a single commit.** One rollback = one pending Preview
  change to commit or discard, mirroring close-the-loop's single-slot
  `last_touched` model. Popping several means committing several. Deferred (§11).
- **No editing of a past batch's contents** (add/remove mods within a dated file).

## 4. UX

### 4.1 A fourth tab — History

A **History** tab joins Updates / Add / Remove
([index.html:10](../../../ModpackManager/modpack_manager/web/index.html:10)),
loaded lazily on first activation (mirroring how `remove` lazy-loads its pack —
[app.js:18](../../../ModpackManager/modpack_manager/web/app.js:18)). The pane is a
vertical **timeline of layers, newest at top** (the reverse of import order, so
the most recent batch — the rollback candidate — reads first).

Each layer row shows:
- **Date** (`2026-05-01`) as the heading, parsed from the filename.
- **Op counts** as pills reusing the existing counts vocabulary:
  `3 updates · 1 add · 0 removals`.
- A muted **git hint** when available: `d740923 · "Update Minecolonies…"`.
- An **Applied / On disk** state chip: applied layers (in the Preview imports) vs
  unapplied dated files found only on disk.
- On the **topmost applied layer only**, a **`Roll back →`** button. Lower applied
  layers show the button **disabled** with a tooltip: *"Roll back the newer
  batches above this one first."* Unapplied layers show no rollback button.

Clicking a row expands it (or opens a detail panel reusing `.review-overlay` /
`.review-panel` — [style.css:67](../../../ModpackManager/modpack_manager/web/style.css:67))
into the three op sections — **Updates / Adds / Removals** — each item rendered
with the same `.review-item` shape the batch review already uses
([app.js:335](../../../ModpackManager/modpack_manager/web/app.js:335)): name +
version transition for updates, `+ name version` for adds, `− name` for removals.

### 4.2 Rollback flow (reuses the Result modal)

`Roll back →` opens the **existing Result modal**
([index.html:67](../../../ModpackManager/modpack_manager/web/index.html:67)) in a
rollback variant:

1. **Confirm** — a short line: *"Un-apply the 2026-05-01 batch? This removes its
   import from the Preview pack and bumps the revision. The dated file stays on
   disk."* plus the batch's op summary (so the maintainer sees exactly what
   un-applying reintroduces/removes).
2. **Preview change written** — the modal moves straight to the close-the-loop
   **Review & commit** state: the **diff** of `GearsAndFrontiers_Preview.xml`
   (the removed `<Import>` line and the revision bump, rendered by the existing
   `renderDiff` — [app.js:316](../../../ModpackManager/modpack_manager/web/app.js:316)),
   a prefilled **commit message** (§6), and the same
   **`Commit preview` / `Discard` / `Close`** actions
   ([app.js:373](../../../ModpackManager/modpack_manager/web/app.js:373),
   [app.js:393](../../../ModpackManager/modpack_manager/web/app.js:393)).
3. **Commit / Committing / Committed / Discard** — identical to close-the-loop
   (YubiKey touch state, SHA + push hint, or restore-to-HEAD on discard). No new
   commit UI is introduced.

After a successful commit or discard, the History tab **refreshes** so the
rolled-back layer moves to *On disk* (or, on discard, stays applied).

### 4.3 Where History is not

History is **read-mostly**; the only mutating control is `Roll back` on the top
layer. It does not offer forward generation (that's the other tabs) — it is the
"look back and undo" surface.

## 5. Architecture

### 5.1 Backend — history read (new `history.py`, pure)

A small pure module (no Flask), symmetric with how the pack is parsed today:

- `read_history(paths) -> HistoryView` — the core. Reads the Preview pack's
  `<Import>` elements **in order** (the same parse as
  `_pack_layer_paths` — [service.py:26](../../../ModpackManager/modpack_manager/service.py:26),
  but retaining imports whose local file is missing so the applied set is truthful,
  not silently pruned as `_pack_layer_paths` does at
  [service.py:35](../../../ModpackManager/modpack_manager/service.py:35)). For each
  import that is a **dated update layer** (basename matches
  `(?:updates-)?\d{4}-\d{2}-\d{2}\.xml`, which excludes `base.xml` and `config.xml`):
  - parse its modules via `parse_pack_file`
    ([xml_model.py:108](../../../ModpackManager/modpack_manager/xml_model.py:108));
  - classify each against the **cumulative merge of every layer below it** (§7.1),
    yielding `updates` / `adds` / `removals` lists;
  - record date, file (repo-relative), applied=true, import URL.
- It also globs `updates/*.xml`
  ([paths.py:31](../../../ModpackManager/modpack_manager/paths.py:31)), drops
  `base.xml` and any file already in the applied set, and emits the remainder as
  **unapplied** layers (date + file only, no op classification needed).
- `top_rollback_target(view) -> str | None` — the repo-relative path of the
  single topmost **applied dated** layer (the only v1-rollbackable layer), or
  `None` if the stack has no dated layers.

Non-goal for this module: git. Git enrichment (§7.3) is a separate best-effort
helper so `history.py` stays a pure XML function that is trivially unit-testable
against fixture packs.

### 5.2 Backend — rollback (new `remove_import` in `generate.py`)

The inverse of `wire_into_preview`, placed beside it so the import-wiring logic
lives in one file:

- `remove_import(preview_path, import_url_substr) -> str` — read the Preview text,
  delete the single line containing `import_url_substr` (the dated filename), bump
  the `<Server revision>` via the existing `_bump_revision`
  ([generate.py:73](../../../ModpackManager/modpack_manager/generate.py:73))
  regex-sub (same one `wire_into_preview` uses at
  [generate.py:88](../../../ModpackManager/modpack_manager/generate.py:88)), write,
  return the new revision. Line-oriented removal mirrors the line-oriented
  insertion at [generate.py:95](../../../ModpackManager/modpack_manager/generate.py:95).
  Raises / returns a sentinel if the import line is absent (defense in depth; the
  route only ever calls it for the known top layer).

### 5.3 Backend — service functions

Two thin wrappers, matching `real_commit`/`real_discard`
([service.py:167](../../../ModpackManager/modpack_manager/service.py:167)):

- `real_history()` — `read_history(pack_paths())`, plus best-effort git enrichment
  (§7.3), returns the serialized `HistoryView`.
- `real_rollback(file)` — resolves `pack_paths()`, **validates `file` is the
  current top rollback target** (`top_rollback_target`), calls
  `generate.remove_import(preview_pack, <dated basename>)`, then returns
  `{ok, removed_import, new_revision, touched_files: ["GearsAndFrontiers_Preview.xml"],
  diff: git_ops.diff(root, touched)}` — the same result shape the generate stream's
  terminal event carries ([service.py:162](../../../ModpackManager/modpack_manager/service.py:162)),
  minus the streaming. A non-top or unknown `file` returns `{ok:false, error:…}`.

### 5.4 Backend — webapp routes

`create_app` ([webapp.py:11](../../../ModpackManager/modpack_manager/webapp.py:11))
gains two injected fns (`history_fn`, `rollback_fn`) and two routes:

- `GET /api/history` → `jsonify(history_fn())`.
- `POST /api/rollback` `{file}` → `rollback_fn(file)`; on `ok`, store
  `cache["last_touched"] = result["touched_files"]` **exactly as the generate
  route does** ([webapp.py:55](../../../ModpackManager/modpack_manager/webapp.py:55))
  so the existing `/api/commit` and `/api/discard` operate on it with **zero
  change**. 400 when `file` is missing or not the current top layer.

`__main__.py` ([__main__.py:14](../../../ModpackManager/modpack_manager/__main__.py:14))
wiring adds `history_fn=real_history, rollback_fn=real_rollback`.

### 5.5 Frontend

A new `#tab-history` panel + a `renderHistory()` / `loadHistory()` pair in
`app.js` following the `loadPack()`/`renderRemove()` pattern
([app.js:195](../../../ModpackManager/modpack_manager/web/app.js:195)). Rollback
**reuses the existing Result-modal functions verbatim** — `openResultModal`,
`renderResult`-style commit state, `commitPreview`, `discardChanges`
([app.js:292](../../../ModpackManager/modpack_manager/web/app.js:292)) — by
feeding the modal a rollback result (summary + diff + prefilled message) instead
of a generate result. No new commit/discard JS.

## 6. Data shapes

```jsonc
// GET /api/history
{
  "layers": [                                  // applied stack, TOP (newest) first
    {
      "file": "updates/updates-2026-05-01.xml",
      "date": "2026-05-01",
      "applied": true,
      "rollbackable": true,                    // only the single top applied layer
      "import_url": "https://raw.githubusercontent.com/edwardg117/Gears-Frontiers/refs/heads/main/updates/updates-2026-05-01.xml",
      "counts": { "updates": 3, "adds": 1, "removals": 0 },
      "ops": {
        "updates":  [ { "mod_id": "minecolonies", "name": "MineColonies", "version": "1.1.842" } ],
        "adds":     [ { "mod_id": "…", "name": "…", "version": "…" } ],
        "removals": [ { "mod_id": "…", "name": "…" } ]
      },
      "commit": { "sha": "d740923", "subject": "Update Minecolonies and add compat back" } // or null
    }
    // … older applied dated layers, rollbackable:false …
  ],
  "unapplied": [                               // dated files on disk, not imported
    { "file": "updates/2025-06-19.xml", "date": "2025-06-19", "applied": false }
  ]
}
```

```jsonc
// POST /api/rollback  request
{ "file": "updates/updates-2026-05-01.xml" }

// response (ok) — same shape as the generate terminal event, non-streamed
{ "ok": true,
  "removed_import": "…/updates/updates-2026-05-01.xml",
  "new_revision": "5",
  "touched_files": ["GearsAndFrontiers_Preview.xml"],
  "diff": "diff --git a/GearsAndFrontiers_Preview.xml …" }

// response (rejected — not the top layer, or unknown file)
{ "ok": false, "error": "Only the most recent applied batch can be rolled back in v1." }
```

Default rollback commit message (frontend-built, backend accepts as given —
parallel to close-the-loop's `chore(preview): update …` at
[app.js:368](../../../ModpackManager/modpack_manager/web/app.js:368)):

`chore(preview): roll back <YYYY-MM-DD> — <u> updates, <a> adds, <r> removals`

(pluralized, zero-count segments dropped; single line, no trailer).

## 7. Backend details

### 7.1 Op classification (the load-bearing derivation)

`read_history` walks the applied imports **bottom → top**, maintaining a running
`merged: dict[str, Module]` seeded empty and fed by `parse_pack_file` +
`_merge` — i.e. it reconstructs the same cumulative state
`parse_packs` ([xml_model.py:120](../../../ModpackManager/modpack_manager/xml_model.py:120))
builds, but *pauses at each dated layer* to classify before merging it in:

For each module `m` in a dated layer, given `merged` = everything below it:
- `m.mod_type == "Removal"` → **removal** (name only).
- `m.mod_id in merged` → **update** (name + `m.version`; the transition
  `merged[m.mod_id].version → m.version` is available if the row wants it).
- else → **add** (name + `m.version`).

Then fold the layer into `merged` via `_merge`
([xml_model.py:89](../../../ModpackManager/modpack_manager/xml_model.py:89)) and
continue. `base.xml` and `config.xml` are merged (they contribute to `merged`)
but never classified or listed — they're not dated update layers. This guarantees
History's op counts equal what MCUpdater resolves from the same import order.

Edge: a `Regular` module can *re-add* a mod that a lower layer marked `Removal`.
Because a `Removal` module is retained in `merged` (with `mod_type="Removal"` —
[xml_model.py:59](../../../ModpackManager/modpack_manager/xml_model.py:59)), such a
mod **is** `in merged`, so it classifies as an **update**. That's the correct
reading (it transitions the mod from removed back to present); no special-casing.

### 7.2 Rollback write

`real_rollback` → `generate.remove_import(preview_pack, "updates-2026-05-01.xml")`.
Deleting the whole `<Import …updates-2026-05-01.xml…>null</Import>` line is robust
against the element's `null` text and attribute ordering (matched by the dated
substring), symmetric with the whole-line insert at
[generate.py:95](../../../ModpackManager/modpack_manager/generate.py:95). Revision
is bumped **forward** — never decremented — because MCUpdater clients treat the
`<Server revision>` ([GearsAndFrontiers_Preview.xml:3](../../../GearsAndFrontiers_Preview.xml:3))
as a monotonic "something changed, re-sync" signal; a rollback that lowers the mod
set still must advance it. Only the Preview pack is touched; the dated file and
`main` are untouched.

### 7.3 Git enrichment (best-effort, optional)

A `history` git helper (or an extension of `git_ops`) computes, per dated file,
the **introducing commit** — e.g. the last entry of
`git log --diff-merges=first-parent --format=%h%x00%s -- <file>` (oldest touch),
or simply the most recent commit that added the import to the Preview pack. Like
`git_ops.diff` ([git_ops.py:26](../../../ModpackManager/modpack_manager/git_ops.py:26))
it is **best-effort**: any `subprocess`/git failure yields `commit: null` and
never aborts `/api/history`. Not a git repo / git missing → all `commit` fields
null, History still fully functional from XML alone.

## 8. Frontend details

- **`loadHistory()`** — `GET /api/history`; on success `renderHistory(view)`; on
  error a muted inline message (pattern from `loadPack` —
  [app.js:195](../../../ModpackManager/modpack_manager/web/app.js:195)). Called on
  first History-tab activation and re-called after a successful rollback
  commit/discard so the applied/unapplied split refreshes.
- **`renderHistory(view)`** — renders `view.layers` (already top-first) then a
  muted **On disk (not applied)** group for `view.unapplied`. Each layer row uses
  `.row`/`.main` ([style.css:20](../../../ModpackManager/modpack_manager/web/style.css:20))
  with op-count pills; expansion renders the three `.review-sec`/`.review-item`
  sections. `Roll back →` is enabled only where `rollbackable`.
- **`rollback(file, summary)`** — `openResultModal()`
  ([app.js:292](../../../ModpackManager/modpack_manager/web/app.js:292)); POST
  `/api/rollback {file}`; on `{ok:true}` feed the modal a **rollback result**
  (the op summary + `result.diff` + a prefilled rollback message per §6) via the
  same body/foot rendering `renderResult` uses for a generate result
  ([app.js:355](../../../ModpackManager/modpack_manager/web/app.js:355)); on
  `{ok:false}` show the error and close. From there **`commitPreview` /
  `discardChanges` are the existing functions, unchanged**
  ([app.js:373](../../../ModpackManager/modpack_manager/web/app.js:373)).
- **Styling** — no new components: reuse `.row`, `.badge`, `.tag`,
  `.review-overlay`/`.review-panel`/`.review-sec`/`.review-item`, `.diff`/`.dl`,
  `.btn-danger` ([style.css:67](../../../ModpackManager/modpack_manager/web/style.css:67),
  [style.css:96](../../../ModpackManager/modpack_manager/web/style.css:96),
  [style.css:106](../../../ModpackManager/modpack_manager/web/style.css:106)). One
  small addition: an `.applied` / `.ondisk` state-chip class.

## 9. Error handling / edge cases

- **Rolling back a middle layer (the core caveat).** Removing a non-top import
  silently reverts any mod that layer touched *and that no later layer
  re-overrode* to its below-state — because merge is last-wins
  ([xml_model.py:127](../../../ModpackManager/modpack_manager/xml_model.py:127)).
  Example: `2026-05-01` updated MineColonies to v5; if a later batch never touched
  MineColonies, un-applying `2026-05-01` reverts it to v4 — usually intended, but
  occasionally surprising for mods the maintainer forgot that batch owned. v1
  sidesteps this entirely by **only enabling rollback on the top layer** (where
  the revert is exactly "as if it never applied"); lower layers are disabled with
  a tooltip. The backend re-validates (§5.3) so a crafted request can't bypass the
  UI guard.
- **Import present but file missing on disk.** History still lists it as applied
  (read from the import, not the file); its ops can't be classified, so it renders
  with a muted *"file missing — cannot show details"* note and is **not**
  rollbackable via the normal path (its diff/re-parse is unreliable). This is the
  case `_pack_layer_paths` silently drops at
  [service.py:35](../../../ModpackManager/modpack_manager/service.py:35); History
  deliberately does not.
- **Dated file on disk, no import.** Listed under **On disk (not applied)** — the
  expected post-rollback state, and also covers files a maintainer added manually
  without wiring.
- **Two batches, same date.** The dated filename is the key (`updates-2026-05-01.xml`);
  the legacy bare-date files (`2015-06-13.xml`, `2025-06-19.xml` —
  [GearsAndFrontiers_Preview.xml:6](../../../GearsAndFrontiers_Preview.xml:6)) are
  matched by the same date regex and shown too. Import URL disambiguates if a date
  ever recurs.
- **Rollback then discard.** `git_ops.discard`
  ([git_ops.py:63](../../../ModpackManager/modpack_manager/git_ops.py:63)) restores
  the (tracked) Preview pack to HEAD — the import reappears, revision restored.
  `cache["last_touched"]` is cleared ([webapp.py:78](../../../ModpackManager/modpack_manager/webapp.py:78)).
  No dated file was deleted, so nothing to un-delete.
- **Rollback with an uncommitted generate pending.** `last_touched` is
  single-slot; a rollback overwrites it. The UI should only offer rollback when no
  generate result is mid-flight (or warn), so the maintainer commits/discards one
  change before starting another — matching close-the-loop's one-pending-change
  model.
- **Empty history / fresh pack.** No dated imports → History shows only `base`/
  `config` context (or an empty-state line); `top_rollback_target` is `None`; no
  rollback offered.
- **Not a git repo / git missing.** `/api/history` still works (git hints null);
  rollback still writes the Preview pack; only commit/discard surface the git error
  (as close-the-loop already handles).

## 10. Testing

`history.py` unit tests (pure, against fixture packs — the risky core):
- **Op classification** over a fixture stack (`base` + two dated layers): a mod
  updated in the top layer classifies as *update*; a brand-new mod as *add*; a
  `Removal` module as *removal*; a `Regular` re-adding a previously-`Removal` mod
  classifies as *update* (§7.1).
- **Applied vs unapplied split**: an import whose file exists → applied; a dated
  file in `updates/` with no import → unapplied; an import whose file is missing →
  applied-but-detail-less (not dropped).
- **Dated-layer detection** excludes `base.xml`/`config.xml` and includes both
  `updates-YYYY-MM-DD.xml` and legacy `YYYY-MM-DD.xml`.
- **`top_rollback_target`** returns the last dated import, `None` for a
  base/config-only pack.

`generate.remove_import` unit tests (against a temp Preview pack):
- Removing the top import deletes exactly that line and bumps the revision by one;
  re-parsing the pack shows the import gone and the file otherwise byte-identical
  except the revision.
- Removing a nonexistent import is a no-op / sentinel (no revision change).
- Round-trip: `wire_into_preview` then `remove_import` for the same URL restores
  the import list (revision advanced twice — forward-only, as designed).

Webapp tests (injected fakes, matching the existing `create_app` DI —
[test_webapp.py:23](../../../ModpackManager/tests/test_webapp.py:23)):
- `GET /api/history` returns the injected view.
- `POST /api/rollback {file}` for the top layer calls `rollback_fn`, and the route
  **stores `last_touched`** so a subsequent `/api/commit` receives
  `["GearsAndFrontiers_Preview.xml"]` (assert via the same stored-paths pattern as
  [test_webapp.py:77](../../../ModpackManager/tests/test_webapp.py:77)).
- `POST /api/rollback` for a non-top / unknown file → 400, `last_touched`
  untouched.
- Rollback → `/api/discard` clears `last_touched` (reuses existing discard test
  shape — [test_webapp.py:100](../../../ModpackManager/tests/test_webapp.py:100)).

`service` test: `real_rollback` validates the top target and delegates to
`generate.remove_import` + `git_ops.diff` (monkeypatched, as
[test_service.py:69](../../../ModpackManager/tests/test_service.py:69) does for
`real_commit`).

Frontend (no JS runner — vanilla): verified by running the app (`run.bat` /
`run.ps1`): open History, confirm the layer list and op counts match the raw
Preview imports; expand a layer; roll back the top batch, confirm the diff shows
the removed import + revision bump, commit (touch the key), see the SHA, and
confirm History now lists that batch as *On disk*; in a fresh run, roll back and
**Discard**, confirm the import reappears and `git status` is clean.

## 11. Deferred (v2)

- **Arbitrary / middle-layer rollback** with an explicit "this reverts N mods to
  their pre-batch state" warning derived from the merge diff (§9).
- **Batch rollback** — pop several top layers into one Preview change / one commit
  (needs a multi-slot `last_touched` or an accumulate-then-commit model).
- **Re-apply** a rolled-back (on-disk) batch — re-add its import. Note the
  semantics: re-applying wires it at the **top** (before `<Loader>` —
  [generate.py:93](../../../ModpackManager/modpack_manager/generate.py:93)), not
  its original position, so it re-applies "as newest," which may reorder relative
  to later batches.
- **Delete an on-disk unapplied file** (a destructive action; kept out of v1 which
  never deletes).
- **Richer git integration** — full per-batch commit list, author/date, link out.
- **Diff-against-now preview** — before rolling back, show which currently-merged
  mods would change and to what, computed from the merge below the target layer.
