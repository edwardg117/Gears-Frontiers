# CurseForge & Recursive Dependency Resolution (Design)

- **Date:** 2026-07-19
- **Status:** Draft for review
- **Builds on:** [2026-07-18-dependency-auto-add-design.md](2026-07-18-dependency-auto-add-design.md)
- **Repo:** Gears & Frontiers (MCUpdater modpack, NeoForge 1.21.1)

## 1. Problem / goal

The dependency auto-add feature ships two deliberate limits (its §3 non-goals):
it is **Modrinth-only** and **direct-only**. Both leak in practice.

- **CurseForge blind spot.** CF candidates always carry
  `added_dependencies=[]` ([curseforge.py:146](../../../ModpackManager/modpack_manager/sources/curseforge.py:146)),
  so a CF mod that starts requiring a new library produces no warning banner and
  no auto-add. The maintainer only finds out when MCUpdater (or a player) hits a
  missing-dependency crash. Roughly half the pack is CurseForge, so this is half
  the surface with none of the safety net.
- **Transitive blind spot.** Auto-add chases only the *direct* new deps of an
  updated mod ([modrinth.py:67](../../../ModpackManager/modpack_manager/sources/modrinth.py:67)).
  If that dep itself needs a mod not in the pack, nothing catches it — the queue
  is one level deep, but real dependency graphs are not.

Goal: extend the **same** selection-driven auto-add pipeline
([app.js `computeAutoDeps`](../../../ModpackManager/modpack_manager/web/app.js:151))
to (1) detect CurseForge dependencies, and (2) resolve the full transitive
closure of new required deps — for both platforms — so the "Queued to add"
section reflects everything an update actually pulls in, not just its first hop.

## 2. Key decisions

- **One pipeline, two new feeders.** No new queue, no new frontend model. Both
  extensions do exactly what Modrinth direct-detection does today: populate
  `AddedDependency` entries on candidates and let
  [`computeAutoDeps`](../../../ModpackManager/modpack_manager/web/app.js:151)
  derive the queue. The reactive, selection-driven behavior (deselect an update
  → its deps drop; re-select → they return with no re-fetch) is inherited for
  free and must stay intact.
- **CF detection mirrors Modrinth detection.** Read the latest CF file's
  `dependencies` array, keep `relationType == 3` (required), drop those whose
  target CF `modId` is already installed, and resolve each to a queueable
  add-spec via a new `curseforge.resolve_dependencies` that parallels
  [`modrinth.resolve_dependencies`](../../../ModpackManager/modpack_manager/sources/modrinth.py:151).
- **`allowModDistribution` gates addability, not detection.** A required CF dep
  whose latest compatible file has no `downloadUrl` (distribution blocked) is
  **detected and surfaced** but marked `addable=False` — there is no jar to hash,
  so it cannot be auto-queued. This reuses the exact `blocked` logic CF candidates
  already apply to themselves ([curseforge.py:138](../../../ModpackManager/modpack_manager/sources/curseforge.py:138))
  and the existing "add it manually" banner path.
- **Transitive = a bounded per-candidate fixpoint over a shared memo.** Each
  candidate's `added_dependencies` becomes the **flattened transitive closure** of
  its new required deps (not just the first hop). Resolution runs as a fixpoint
  (resolve the frontier, fold newly-discovered ids into the frontier, repeat)
  guarded by a `seen` set and a depth cap, with a process-wide memo so a subtree
  shared by two updates is fetched once. Flattening onto the requiring candidate
  is what keeps the selection-driven drop correct (see §5.3).
- **Resolution is same-platform.** A Modrinth version's `dependencies` reference
  Modrinth project ids; a CF file's `dependencies` reference CF modIds. Dependency
  edges are therefore **always within one platform** — there is no such thing as a
  CF file that names a Modrinth project id as a dependency. So recursion never
  crosses platforms *along edges*. Cross-platform trouble is a different, subtler
  problem (the "already satisfied by the other platform" hazard) — flagged as the
  headline open question in §2.1 and §9.
- **`AddedDependency` gains `platform`.** Today the field is implicitly Modrinth
  (the frontend hardcodes `platform: "modrinth"` when building the add-spec,
  [app.js:259](../../../ModpackManager/modpack_manager/web/app.js:259)). CF deps
  make platform explicit and load-bearing.

### 2.1 Open question — cross-platform "already in pack" (the genuinely hard one)

The dependency arrays never cross platforms, but **pack membership does**. Concrete
failure: the pack has *Architectury* installed from **CurseForge**; a freshly
updated **Modrinth** mod lists the *Architectury* **Modrinth project** as a required
dep. The Modrinth "already installed" set is
`current_project_ids` — Modrinth project ids only
([updates.py:66](../../../ModpackManager/modpack_manager/updates.py:66)) — and the
CF-installed Architectury contributes a `cf_file_id`/`modId`, **not** a Modrinth
project id ([xml_model.py:36-43](../../../ModpackManager/modpack_manager/xml_model.py:36)).
So the resolver sees Architectury as "missing", resolves the Modrinth copy, and
**auto-queues a duplicate of a library the pack already ships** under the other
platform.

There is no shared identifier to reconcile this by id. Options, with a recommended
v1 stance in §9. This is the one place the feature can be actively wrong rather than
merely incomplete, so it must be a conscious decision, not an accident.

## 3. Non-goals (v1)

- **No cross-platform de-duplication by identity.** v1 does not attempt to prove
  that a Modrinth dep and a CF pack entry are "the same mod." The mitigation in §9
  is a cheap name/slug heuristic, not a resolver. True cross-registry identity is
  deferred (§11).
- **No optional deps.** `relationType == 2` (CF) / `dependency_type == "optional"`
  (Modrinth) stay ignored, exactly as today. Only required edges are chased.
- **No CF per-dep side detection.** CF's API does not expose client/server side
  cleanly; `project_versions` already hardcodes `"BOTH"`
  ([curseforge.py:299](../../../ModpackManager/modpack_manager/sources/curseforge.py:299)).
  CF auto-deps default `side="BOTH"`. Modrinth deps keep real side detection via
  [`_detect_side`](../../../ModpackManager/modpack_manager/sources/modrinth.py:247).
- **No per-row version override / no "why is this here" tree view.** Auto-deps
  (direct or transitive) take the latest compatible version; the chip names the
  requiring *root* update, not the intermediate link (§5.3, deferred refinement in
  §11).
- **No change to generate/write.** `generate_events` already downloads whatever
  URL each add-spec carries and hashes it
  ([service.py:119-136](../../../ModpackManager/modpack_manager/service.py:119));
  CF and transitive deps are just more entries in the existing `adds` array.

## 4. UX

The surfaces are unchanged from the predecessor — they simply carry more, and now
correctly platform-labelled, entries.

### 4.1 Add tab — Queued to add
Auto-deps still render first, then manual adds. Two visible changes:
- **Platform pill is real.** A CF auto-dep shows the **CF** pill; a Modrinth one
  shows **MR**. Today the auto-dep row hardcodes `MR`
  ([app.js:171](../../../ModpackManager/modpack_manager/web/app.js:171)); it
  becomes `dep.platform`-driven.
- **Transitive deps look identical to direct deps.** A dep pulled in three hops
  deep is just another row with its requiring-mod chip(s). The user does not need
  to care whether it was direct or transitive — only that selecting this update
  entails adding it.

### 4.2 Updates tab — changelog banner
The dependency banner ([app.js:66-72](../../../ModpackManager/modpack_manager/web/app.js:66))
now renders for **CF candidates too** (they finally carry `added_dependencies`).
Text is unchanged and already `addable`-driven:
- **addable** → `⚠ New required dependency: <b>Name</b> (version) — added to the Add queue`
- **not addable** → `⚠ New required dependency: <b>Name</b> — not in your pack; add it manually`

The "not addable" line is exactly where a distribution-blocked CF dep lands (§7.2).

### 4.3 Review + Result panels
No structural change. Auto-deps (now including CF and transitive entries) already
flow through `openReview` ([app.js:236](../../../ModpackManager/modpack_manager/web/app.js:236))
and `resultSummaryHtml` ([app.js:330](../../../ModpackManager/modpack_manager/web/app.js:330))
via `computeAutoDeps`; they inherit the chips and the no-remove treatment.

## 5. Architecture

### 5.1 Data shape — `AddedDependency` gains one field

```python
# base.py — AddedDependency (one new field; all others unchanged)
@dataclass
class AddedDependency:
    id: str                     # platform id: Modrinth project_id OR CF modId (as str)
    satisfied: bool             # always False for detected new deps (unchanged)
    name: str | None = None
    url: str = ""
    slug: str = ""              # add's module_id
    side: str = "BOTH"
    version: str = ""
    download_url: str = ""
    size: int | None = None
    addable: bool = False
    platform: str = "modrinth"  # NEW: "modrinth" | "curseforge"
```

`id` is already generic ("platform id"); for CF it holds the `modId` as a string.
`platform` defaults to `"modrinth"` so existing Modrinth construction and every
current test are untouched. It rides along in `Candidate.to_dict()`
([base.py:46](../../../ModpackManager/modpack_manager/sources/base.py:46)) with no
route or serializer change.

### 5.2 Backend — where the two feeders hook in

- **CF detection** lives in
  [`curseforge.build_candidate`](../../../ModpackManager/modpack_manager/sources/curseforge.py:90),
  replacing the literal `added_dependencies=[]`
  ([curseforge.py:146](../../../ModpackManager/modpack_manager/sources/curseforge.py:146))
  with a collected list — the exact structural mirror of
  [modrinth.py:67-73](../../../ModpackManager/modpack_manager/sources/modrinth.py:67).
- **CF resolution** is a new `curseforge.resolve_dependencies(dep_mod_ids, …)`
  paralleling [`modrinth.resolve_dependencies`](../../../ModpackManager/modpack_manager/sources/modrinth.py:151)
  (§7.1).
- **The fixpoint driver** is
  [`updates._resolve_dependencies`](../../../ModpackManager/modpack_manager/updates.py:94),
  which today does a single Modrinth-only bulk pass. It becomes a bounded,
  two-platform, transitive resolver (§5.3). This is the only file whose *control
  flow* materially changes; the sources gain new functions but keep their shapes.

No webapp/route/service signatures change. Enrichment still happens inside
`scan()` ([updates.py:90](../../../ModpackManager/modpack_manager/updates.py:90))
and rides the existing `GET /api/updates` payload.

### 5.3 The "attach the closure to the requiring candidate" decision

A transitive dep (dep-of-a-dep) belongs to no candidate of its own — nothing in
`state.candidates` is the mod three hops up. Two ways to model it:

- **(A) Flatten the closure onto each requiring root candidate.** `candidate.added_dependencies`
  = the full set of new required deps reachable from that candidate. **Chosen.**
- (B) A separate top-level "resolved deps" collection outside candidates. Rejected:
  it breaks the selection-driven model — `computeAutoDeps` filters by
  `state.selected.has(c.mod_id)` ([app.js:154](../../../ModpackManager/modpack_manager/web/app.js:154)),
  so a dep not owned by a candidate could not drop when its root update is deselected.

Under (A) the existing frontend needs **zero new logic** for transitivity:
`computeAutoDeps` already dedupes across candidates by slug and merges chips, so a
library required by two different updates' subtrees shows as one row with two
chips, and deselecting either update drops its contribution. The only cost is that
a transitive dep's chip reads `dep of <RootUpdate>`, not `dep of <IntermediateLib>`
— acceptable and arguably clearer (§11 offers the chain view as a refinement).

To make (A) cheap, resolution is global-with-memo: every unique `(platform, id)` is
resolved once into a shared cache; each candidate then walks its own frontier
through that cache to assemble its closure. No subtree is fetched twice.

## 6. Data shapes

```jsonc
// CF file dependencies array (input we read; CF API shape on each file object)
"dependencies": [
  { "modId": 306612, "relationType": 3 },   // 3 = RequiredDependency  -> collected
  { "modId": 419699, "relationType": 2 }    // 2 = OptionalDependency  -> ignored
]
```

```jsonc
// Auto-dep -> AddSpec in POST /api/generate "adds"  (unchanged shape; platform now varies)
{ "platform": "curseforge",         // was hardcoded "modrinth"; now dep.platform
  "module_id": "<dep.slug>",        // CF mod slug, used exactly like a manual CF add
  "name": "<dep.name>", "version": "<dep.version>",
  "url": "<dep.download_url>",       // CF file downloadUrl (absent => not addable)
  "side": "BOTH", "required": true }
```

`resolve_dependencies` return (both platforms), extended with a `requires` edge
list so the fixpoint can recurse:

```jsonc
// { <dep_id>: { ...add-spec fields..., "requires": [<same-platform dep id>, …] } }
{ "306612": { "name": "Cloth Config API", "slug": "cloth-config", "side": "BOTH",
              "version": "15.0.140", "download_url": "https://edge.forgecdn.net/…",
              "size": 512000, "addable": true, "requires": ["319057"] } }
```

`requires` is a resolution-time detail used to build the closure; it is **not**
stored on `AddedDependency` (the closure is already flattened onto the candidate).

## 7. Backend details

### 7.1 `curseforge.resolve_dependencies(dep_mod_ids, mc_version, loader, api_key)`

Mirror of the Modrinth resolver's three phases, using CF's bulk endpoints and
`_chunk(…, 50)` ([curseforge.py:158](../../../ModpackManager/modpack_manager/sources/curseforge.py:158)):

1. **Bulk mod meta** — one `POST /mods` (reusing
   [`_bulk_mods`](../../../ModpackManager/modpack_manager/sources/curseforge.py:176)):
   per modId take `name`, `slug`, `links.websiteUrl` (the "open" url),
   `allowModDistribution`, and `latestFilesIndexes` →
   [`_latest_compatible_file_id`](../../../ModpackManager/modpack_manager/sources/curseforge.py:187)
   for our `mc_version`/loader.
2. **Bulk file details** — one `POST /mods/files` (reusing the shape in
   [`_bulk_file_to_mod`](../../../ModpackManager/modpack_manager/sources/curseforge.py:164))
   over the fileIds from step 1: per file take `downloadUrl`, `fileLength` → size,
   `displayName`/`fileName` → [`_clean_version`](../../../ModpackManager/modpack_manager/sources/curseforge.py:25),
   and the file's own `dependencies` (`relationType == 3`) → `requires`.
3. **Combine.** `side = "BOTH"` (§3). `addable = allowModDistribution and
   bool(downloadUrl) and bool(slug)`. A blocked or fileless dep resolves with
   `addable=False` and whatever meta did resolve (name still shown in the banner).

Two bulk calls per platform per fixpoint iteration — no per-dep fan-out at all
(CF's bulk endpoints are richer than Modrinth's, which still needs the concurrent
per-dep version fetch at [modrinth.py:180-193](../../../ModpackManager/modpack_manager/sources/modrinth.py:180)).
Failure isolation matches the Modrinth resolver: wrap each bulk call; a dep that
fails any phase stays `addable=False`.

### 7.2 `curseforge.build_candidate` — detection

After `latest = files[0]` ([curseforge.py:111](../../../ModpackManager/modpack_manager/sources/curseforge.py:111)),
collect required deps exactly as Modrinth does at
[modrinth.py:67-73](../../../ModpackManager/modpack_manager/sources/modrinth.py:67):

```python
added = []
for dep in latest.get("dependencies", []):
    if dep.get("relationType") == 3 and dep.get("modId"):
        mod_id = dep["modId"]
        if mod_id not in installed_cf_mod_ids:
            added.append(AddedDependency(id=str(mod_id), satisfied=False,
                                         platform="curseforge"))
```

`installed_cf_mod_ids` is the CF analogue of `current_project_ids` (§7.4). At this
stage the entries carry only `id`/`platform`; the fixpoint fills the rest.

### 7.3 `modrinth.resolve_dependencies` — surface the edges for recursion

The Modrinth resolver already fetches the dep's latest version
([modrinth.py:180-188](../../../ModpackManager/modpack_manager/sources/modrinth.py:180))
but ignores that version's own `dependencies`. Recursion needs them: read
`versions[0].get("dependencies")`, keep `dependency_type == "required"` with a
`project_id`, and return them as `requires`. This is the only change to the
Modrinth resolver — no new request, just reading a field already in hand. CF gets
the same edge list from step 2 above.

### 7.4 `updates._resolve_dependencies` — the bounded fixpoint

Today: gather Modrinth dep ids, one bulk pass, copy fields back
([updates.py:100-121](../../../ModpackManager/modpack_manager/updates.py:100)).
New shape:

1. **Installed sets.** `current_project_ids` (Modrinth, already computed at
   [updates.py:66](../../../ModpackManager/modpack_manager/updates.py:66)) plus a new
   `installed_cf_mod_ids` threaded from the CF bulk prefilter (§7.5).
2. **Seed frontier** = every candidate's direct `added_dependencies` ids, tagged
   by `(platform, id)`, minus the installed sets.
3. **Fixpoint** (shared memo `resolved: {(platform, id): spec}`, `seen` set,
   `depth` counter to `MAX_DEPTH`):
   - Partition the pending frontier by platform; call the platform resolver **in
     bulk** for all pending ids of that platform (reuse the two-worker executor
     pattern already in [`scan`](../../../ModpackManager/modpack_manager/updates.py:73)
     to run the two platforms concurrently).
   - Record specs in the memo. For each resolved dep, its `requires` ids that are
     **not installed** and **not in `seen`** become the next frontier.
   - Stop when the frontier is empty or `depth == MAX_DEPTH`.
4. **Attach closures.** For each candidate, walk its direct dep ids through the
   memo's `requires` edges (same `seen`/installed guards) to collect its transitive
   closure, and set `candidate.added_dependencies` to the corresponding flattened
   list of enriched `AddedDependency` objects (dedup within a candidate by
   `(platform, id)`).

`MAX_DEPTH` is a small constant (**recommend 4**: direct + 3 hops). Minecraft
dependency chains are shallow (mod → lib → maybe a second lib); the cap plus the
`seen` set are belt-and-suspenders against cycles and pathological graphs. A dep
discovered *beyond* the cap is left unresolved and surfaced as
`addable=False`-style "resolve manually" so nothing is silently dropped (§9).

Best-effort throughout: any resolver exception aborts *that platform's* pass and
leaves its deps `addable=False`, exactly as the current single pass does
([updates.py:107-108](../../../ModpackManager/modpack_manager/updates.py:107)).

### 7.5 Threading `installed_cf_mod_ids` from the bulk prefilter

The CF bulk prefilter already resolves **every** installed CF file to its modId:
`_bulk_file_to_mod(session, file_ids)` over all CF modules
([curseforge.py:212-213](../../../ModpackManager/modpack_manager/sources/curseforge.py:212)),
then discards the map (only per-updated-mod `contexts` survive). The set
`set(file_to_mod.values())` is precisely the installed-CF-modId set we need, already
fetched — no extra requests.

Design: have
[`find_updated_mod_ids`](../../../ModpackManager/modpack_manager/sources/curseforge.py:200)
also return that set (or have
[`_curseforge_to_check`](../../../ModpackManager/modpack_manager/updates.py:51)
surface it), and thread it into `scan` alongside `current_project_ids`. Note CF
`build_candidate` already *accepts* `current_project_ids` today but never uses it
(only Modrinth does, at [modrinth.py:71](../../../ModpackManager/modpack_manager/sources/modrinth.py:71));
`_check` ([updates.py:20-28](../../../ModpackManager/modpack_manager/updates.py:20))
should pass each builder its platform-appropriate installed set. A CF pack mod the
bulk pass fails to resolve simply isn't in the set — a rare, self-correcting false
"missing" (the dep just gets surfaced), acceptable for v1.

## 8. Frontend details

Small, surgical — the model already supports everything; three spots hardcode
Modrinth and must read `dep.platform`:

- **`computeAutoDeps`** ([app.js:151](../../../ModpackManager/modpack_manager/web/app.js:151))
  — dedup key becomes `` `${d.platform}:${d.slug}` `` instead of `d.slug` alone, so
  a Modrinth slug and an (unlikely) identical CF slug don't collide, and the
  manual-add skip check ([app.js:157](../../../ModpackManager/modpack_manager/web/app.js:157))
  compares platform+module_id. No other change — transitive entries already look
  like direct ones because they live in `added_dependencies`.
- **`renderQueue`** ([app.js:171](../../../ModpackManager/modpack_manager/web/app.js:171))
  — the pill becomes `dep.platform === "curseforge" ? "CF" : "MR"` (matching the
  updates-row pill logic at [app.js:49](../../../ModpackManager/modpack_manager/web/app.js:49)).
- **`generate`** ([app.js:258-260](../../../ModpackManager/modpack_manager/web/app.js:258))
  — the auto-add spec's `platform: "modrinth"` becomes `platform: dep.platform`.
  This is the load-bearing fix: without it a CF dep would be written with the wrong
  platform tag (the URL still downloads, but the pill and any platform-aware logic
  are wrong).

`renderReader` ([app.js:66-72](../../../ModpackManager/modpack_manager/web/app.js:66))
needs **no change** — it renders `added_dependencies` generically, so CF deps and
transitive deps light up the banner as soon as the backend populates them.

## 9. Error handling / edge cases

- **Cross-platform "already installed" duplicate** (§2.1) — the headline hazard.
  **Recommended v1 stance:** resolve within-platform (as designed) and add a
  **cheap name/slug guard in `computeAutoDeps`**: skip an auto-dep whose resolved
  `name`/`slug` case-insensitively matches a `state.pack` entry
  (`state.pack` is already loaded eagerly for the Add tab,
  [app.js:414](../../../ModpackManager/modpack_manager/web/app.js:414)). This catches
  the Architectury-from-CF case in the common instance (same display name) without
  pretending to solve cross-registry identity. Residual mismatches (different names
  for the same mod) fall through and get queued — the maintainer sees the row and
  can drop it, and MCUpdater tolerates a duplicate module id far better than a
  missing dependency. **Alternative considered:** a backend cross-platform name
  index — rejected for v1 as over-built for a rare case (§11).
- **Distribution-blocked CF dep** → detected, `addable=False`, banner says "add it
  manually", never queued (§7.1/§7.2). Mirrors how CF candidates already blocked
  themselves ([curseforge.py:138-149](../../../ModpackManager/modpack_manager/sources/curseforge.py:138)).
- **Dependency cycle** (A needs B needs A) → the `seen` set stops re-resolution;
  each is resolved once and attached once. The depth cap is the second guard.
- **Chain deeper than `MAX_DEPTH`** → the over-cap dep is surfaced (banner) but
  left `addable=False` with a note, so it is visible and manually addable rather
  than silently missing. (Expected to be effectively never hit at depth 4.)
- **Same dep reached via two paths / two updates** → resolved once (memo), attached
  to each requiring candidate; `computeAutoDeps` dedupes to one row with a chip per
  requiring root update — unchanged behavior.
- **CF bulk resolver fails mid-scan** → that platform's deps stay `addable=False`
  (banner still shows); Modrinth deps unaffected (independent passes).
- **Dep already queued manually** → `computeAutoDeps` still skips it by
  platform+module_id; the user's chosen version wins.
- **Scan finds no new deps** → fixpoint seed is empty, whole pass is a no-op
  (unchanged from [updates.py:102-103](../../../ModpackManager/modpack_manager/updates.py:102)).

## 10. Testing

Backend unit tests (mocked HTTP via `responses`, matching
[test_curseforge.py](../../../ModpackManager/tests/test_curseforge.py) and
[test_modrinth.py](../../../ModpackManager/tests/test_modrinth.py)):

- **`curseforge.build_candidate` detection** — latest file with a `relationType==3`
  dep whose modId is **not** in `installed_cf_mod_ids` → one `AddedDependency`
  (`platform="curseforge"`, `satisfied=False`); an installed modId and a
  `relationType==2` optional → both excluded. Mirrors the Modrinth detection tests
  at [test_modrinth.py:55](../../../ModpackManager/tests/test_modrinth.py:55).
- **`curseforge.resolve_dependencies` happy path** — bulk `/mods` + `/mods/files`
  → fields populated, `addable=True`, `requires` carries the file's own
  `relationType==3` modIds.
- **`resolve_dependencies` blocked dep** — `allowModDistribution=False` or null
  `downloadUrl` → `addable=False`, name still resolved. Parallels
  [test_curseforge.py:93](../../../ModpackManager/tests/test_curseforge.py:93).
- **`modrinth.resolve_dependencies` now returns `requires`** — a version whose
  `dependencies` include a required project id surfaces it; optional/absent → empty.
- **`updates._resolve_dependencies` transitivity** — candidate → dep A → dep B
  (A `requires` B, B not installed) → candidate's `added_dependencies` closure
  contains both A and B; a mocked resolver asserts B is fetched exactly once even
  when two candidates share it (memo). Extends
  [test_updates.py:70](../../../ModpackManager/tests/test_updates.py:70).
- **Cycle + depth cap** — A `requires` B, B `requires` A → terminates, each
  attached once; a chain longer than `MAX_DEPTH` stops at the cap with the over-cap
  dep left `addable=False`.
- **Installed-CF-modId threading** — a CF dep whose modId is in the installed set
  is not collected (the cross-platform-adjacent within-platform guard).

Frontend has no JS runner; verify by running the app (`run.bat` / `run.ps1`):
trigger a scan
where a CF update introduces a new required library and a Modrinth update introduces
a two-level chain; confirm both appear in "Queued to add" with correct **CF/MR**
pills and requiring-mod chips, that a distribution-blocked CF dep shows the "add it
manually" banner and is **not** queued, that deselecting the root update drops its
whole subtree and re-selecting restores it with no network call, and that Generate
writes every queued dep into the dated update file.

## 11. Deferred (v2)

- **True cross-platform identity resolution** — a real index (hash/name/known-alias
  map) that proves a Modrinth dep equals a CF pack entry, replacing the §9 name
  heuristic. The correct long-term fix for §2.1.
- **Optional-dependency prompts** — offer `relationType==2` deps as opt-in rather
  than ignoring them.
- **CF side detection** — derive client/server side for CF deps if a reliable
  signal emerges, replacing the `BOTH` default.
- **Dependency-chain chips / tree view** — show `dep of A → B` provenance for
  transitive deps instead of naming only the root update.
- **Per-row version override** on an auto-dep without dropping to manual search
  (carried over from the predecessor's §11).
