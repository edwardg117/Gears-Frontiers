# Reliability & Error Surfacing (Design)

- **Date:** 2026-07-19
- **Status:** Draft for review
- **Builds on / relates to:** [2026-07-19-close-the-loop-design.md](2026-07-19-close-the-loop-design.md) (§11 named "retry/backoff + 429 handling" as the reliability track — this is it), [2026-07-18-dependency-auto-add-design.md](2026-07-18-dependency-auto-add-design.md) (the dependency resolution whose silent failure §2·KD2 surfaces)
- **Repo:** Gears & Frontiers (MCUpdater modpack, NeoForge 1.21.1)

## 1. Problem / goal

Three reliability gaps in the source layer, all currently **invisible** to the maintainer:

1. **No resilience to transient failures.** Every API call builds a throwaway
   `requests.Session` with a fixed timeout and **no retry, backoff, or 429
   handling** anywhere — confirmed across the source layer
   ([modrinth.py:17](../../../ModpackManager/modpack_manager/sources/modrinth.py:17),
   [curseforge.py:39](../../../ModpackManager/modpack_manager/sources/curseforge.py:39),
   [hashing.py:35](../../../ModpackManager/modpack_manager/hashing.py:35)). A single
   connection reset, a `503`, or — most likely — a CurseForge `429` from the
   **per-file changelog fan-out**
   ([curseforge.py:83](../../../ModpackManager/modpack_manager/sources/curseforge.py:83),
   called once per newer file at
   [curseforge.py:124](../../../ModpackManager/modpack_manager/sources/curseforge.py:124))
   turns a mod into a `status="error"` row, or drops a whole platform from search.

2. **Failures are swallowed.** `real_search` bare-`except`s each platform and
   returns partial results with no signal
   ([service.py:65](../../../ModpackManager/modpack_manager/service.py:65),
   [service.py:70](../../../ModpackManager/modpack_manager/service.py:70));
   `_resolve_dependencies` silently `return`s on any error, so new required
   dependencies quietly aren't auto-queued
   ([updates.py:107](../../../ModpackManager/modpack_manager/updates.py:107)); and the
   two bulk prefilters fall back to the slow per-mod path with no notice
   ([updates.py:47](../../../ModpackManager/modpack_manager/updates.py:47),
   [updates.py:61](../../../ModpackManager/modpack_manager/updates.py:61)). The
   maintainer sees a plausible-looking partial result and can't tell something degraded.

3. **The generated server template is loader-wrong.** `_server_element` hardcodes
   NeoForge/Forge launch attributes
   (`mainClass="cpw.mods.bootstraplauncher.BootstrapLauncher"`, `launcherType="Vanilla"`)
   regardless of `config.loader`
   ([generate.py:24](../../../ModpackManager/modpack_manager/generate.py:24),
   [config.py:13](../../../ModpackManager/modpack_manager/config.py:13)).

Goal: **make the source layer resilient to transient failures, make the failures
that remain visible, and make the generated template loader-correct** — three
cohesive changes shipped as one effort, each small and independently testable.

## 2. Key decisions

- **KD1 — One shared, retrying session factory.** Add
  `sources/http.py::build_session()` that mounts a `requests.adapters.HTTPAdapter`
  carrying a `urllib3.util.retry.Retry` on both `http://` and `https://`, and route
  both platform `_session()` builders
  ([modrinth.py:17](../../../ModpackManager/modpack_manager/sources/modrinth.py:17),
  [curseforge.py:39](../../../ModpackManager/modpack_manager/sources/curseforge.py:39))
  and the download session
  ([hashing.py:35](../../../ModpackManager/modpack_manager/hashing.py:35)) through it.
  Retry connection/read errors and `status_forcelist={429,500,502,503,504}` with
  exponential backoff, honoring `Retry-After` (`respect_retry_after_header`, on by
  default). **POST must be opted into `allowed_methods`** — both platforms' bulk
  checks are POSTs
  ([modrinth.py:115](../../../ModpackManager/modpack_manager/sources/modrinth.py:115),
  [curseforge.py:168](../../../ModpackManager/modpack_manager/sources/curseforge.py:168),
  [curseforge.py:180](../../../ModpackManager/modpack_manager/sources/curseforge.py:180))
  and they are **read-only lookups** despite the verb, so retrying them is safe. This
  is a **pure infrastructure swap**: no API-function call site changes beyond which
  builder they call.

- **KD2 — Failure isolation is preserved; retries fail *closed* into it.** With
  `raise_on_status=True` (the default), exhausted retries raise, and the existing
  per-mod isolation already catches it — the `_check` wrapper
  ([updates.py:29](../../../ModpackManager/modpack_manager/updates.py:29)) and
  `build_candidate`'s `except requests.RequestException`
  ([curseforge.py:152](../../../ModpackManager/modpack_manager/sources/curseforge.py:152))
  both turn it into a single `status="error"` candidate. **A mod that still fails
  after retries is one error row, not a crashed scan** — unchanged behavior, just
  reached far less often.

- **KD3 — A `warnings` channel makes swallowed failures visible.** `scan()` returns a
  `ScanResult(candidates, warnings)` and `real_search` returns `(hits, warnings)`; the
  three silent `except` sites each record a structured `Notice` instead of vanishing.
  `GET /api/updates` → `{candidates, warnings}` and `GET /api/search` →
  `{hits, warnings}` (both additive — existing keys unchanged). The frontend renders a
  **dismissible banner** on the Updates tab and a note above search results. This is
  how `real_search`'s per-platform `except` and `_resolve_dependencies`'s silent
  `return` become things the maintainer can *see*.

- **KD4 — Two notice severities, so we don't cry wolf.** `warn` (amber, *data may be
  incomplete* — e.g. a platform dropped from search, dependencies not auto-queued) vs
  `info` (muted, *complete but slower* — e.g. a bulk prefilter fell back to per-mod).
  The bulk-prefilter fallbacks still produce **correct, complete** candidate lists
  ([updates.py:47](../../../ModpackManager/modpack_manager/updates.py:47),
  [updates.py:61](../../../ModpackManager/modpack_manager/updates.py:61)), so they are
  `info`, not `warn`.

- **KD5 — Loader-aware template, NeoForge as the safe default.** Map `config.loader` →
  `(mainClass, launcherType)` in `_server_element`
  ([generate.py:18](../../../ModpackManager/modpack_manager/generate.py:18)), defaulting
  to today's NeoForge pair for any unknown loader so **this pack never regresses**.
  See §7.4 for the map and the important caveat that these per-update attributes are
  **effectively inert** in the current import-based pack (investigated in §7.4 /
  Open questions) — this is correctness hygiene and future-proofing, not a live
  launch-bug fix.

**Open decisions flagged for review** (detail in [Open questions](#open-questions)):
exact `Retry` parameters (attempts / backoff); the precise Fabric/Quilt `mainClass`
strings and whether `launcherType` should ever differ from `"Vanilla"`; and whether the
per-update `<Server>` should carry launch attributes at all given they're inert.

## 3. Non-goals (v1)

- **No change to the concurrency model.** The scan stays `ThreadPoolExecutor`
  (`max_workers=5`, [updates.py:81](../../../ModpackManager/modpack_manager/updates.py:81))
  and downloads stay **serial**
  ([service.py:126](../../../ModpackManager/modpack_manager/service.py:126)) — parallel
  downloads remain the close-the-loop spec's deferred item.
- **No global rate limiter / token bucket.** We rely on `Retry-After` + backoff, not a
  client-side scheduler. (Noted as a v2 escalation in §11 if 429s persist.)
- **No retry of non-transient 4xx.** A `404`/`400`/`401` is not retried — only the
  `status_forcelist` codes and transport errors are.
- **No changelog-response caching.** The on-disk cache stays jar-hash-only
  ([hashing.py:10](../../../ModpackManager/modpack_manager/hashing.py:10)); reducing the
  changelog fan-out by caching is deferred (§11).
- **No new CurseForge dependency detection.** Unchanged; that is the dependency-auto-add
  spec's deferred item.
- **No new persistence.** Warnings are per-scan, held in the same in-memory `cache`
  the candidates already live in
  ([webapp.py:14](../../../ModpackManager/modpack_manager/webapp.py:14)).

## 4. UX

### 4.1 Updates tab — scan warnings banner
A new dismissible banner sits at the top of the Updates panel (above `.panes`,
[index.html:23](../../../ModpackManager/modpack_manager/web/index.html:23)), rendered by
`load()` from `data.warnings`
([app.js:22](../../../ModpackManager/modpack_manager/web/app.js:22)). One line per
notice, styled by severity, reusing the existing amber `.dep` note look
([style.css:42](../../../ModpackManager/modpack_manager/web/style.css:42)) for `warn`
and a muted variant for `info`. Each row has an ✕ that hides it for the session
(dismissal keyed by `code`, §8). Examples:

- `warn` → `⚠ CurseForge was unavailable — showing Modrinth results only.`
- `warn` → `⚠ Dependency resolution failed — new required dependencies were not auto-queued. Check the changelog banners and add them manually.`
- `info` → `ⓘ Modrinth bulk update-check was slow and fell back to per-mod checks — results are complete.`

Per-row `status="error"` mods are **unchanged** — they still render as error rows
([app.js:41](../../../ModpackManager/modpack_manager/web/app.js:41)); the banner is for
*scan-level* degradation the rows can't express.

### 4.2 Add tab — search warnings note
`runSearch()` ([app.js:89](../../../ModpackManager/modpack_manager/web/app.js:89)) reads
`data.warnings` and renders a single muted/amber note above `#add-results`
([index.html:42](../../../ModpackManager/modpack_manager/web/index.html:42)), e.g.
`⚠ CurseForge search failed — showing Modrinth results only.` It clears on the next search.

### 4.3 Retries are invisible
No new UI for retries — their entire purpose is that transient blips **stop** producing
error rows and dropped platforms. The one visible effect is latency: a scan hitting
backoff is slower, which the existing loading copy ("this can take ~30 seconds",
[index.html:29](../../../ModpackManager/modpack_manager/web/index.html:29)) already
absorbs. Worst-case added latency is bounded by the backoff cap (§7.1).

## 5. Architecture

### 5.1 New `sources/http.py`
A tiny module with one public function and the shared `Retry` policy:

```
build_session(headers: dict | None = None) -> requests.Session
```

It constructs a `requests.Session`, builds one `HTTPAdapter(max_retries=_RETRY)`, mounts
it on `"http://"` and `"https://"`, applies any `headers`, and returns it. `_RETRY` (the
`urllib3` `Retry`) is a module constant (§7.1). No Flask imports; pure and unit-testable.

### 5.2 Source wiring (no signature changes)
- `modrinth._session()`
  ([modrinth.py:17](../../../ModpackManager/modpack_manager/sources/modrinth.py:17)) →
  `s = build_session()`, then set `User-Agent` / `Authorization` as today.
- `curseforge._session()`
  ([curseforge.py:39](../../../ModpackManager/modpack_manager/sources/curseforge.py:39)) →
  `s = build_session()`, then set `x-api-key` / `Accept` as today.
- `hashing.compute()`
  ([hashing.py:30](../../../ModpackManager/modpack_manager/hashing.py:30)) — when no
  session is injected, build one via `build_session()` instead of a bare
  `requests.Session()`
  ([hashing.py:35](../../../ModpackManager/modpack_manager/hashing.py:35)), so a flaky
  connect/DNS blip on a jar download is retried before the whole generate aborts. (Caveat:
  a *mid-stream* read failure on a large streamed jar still raises — retries re-request
  from the start; this is acceptable and already surfaced as a generate failure at
  [service.py:130](../../../ModpackManager/modpack_manager/service.py:130).)

### 5.3 Warnings in the service / updates layer
- `sources/base.py` gains a `Notice` dataclass (§6) — named `Notice` to avoid shadowing
  the builtin `Warning`; it serializes under the JSON key `warnings`.
- `updates.scan()`
  ([updates.py:65](../../../ModpackManager/modpack_manager/updates.py:65)) returns a
  `ScanResult(candidates, warnings)`. The two bulk-prefilter helpers
  ([updates.py:38](../../../ModpackManager/modpack_manager/updates.py:38),
  [updates.py:51](../../../ModpackManager/modpack_manager/updates.py:51)) and
  `_resolve_dependencies`
  ([updates.py:94](../../../ModpackManager/modpack_manager/updates.py:94)) return an
  optional `Notice` alongside their result; `scan()` aggregates the non-`None` ones.
- `service.real_scan()`
  ([service.py:40](../../../ModpackManager/modpack_manager/service.py:40)) returns the
  `ScanResult` unchanged. `generate_events` reads `.candidates` at its self-scan
  fallback ([service.py:104](../../../ModpackManager/modpack_manager/service.py:104)).
- `service.real_search()`
  ([service.py:58](../../../ModpackManager/modpack_manager/service.py:58)) returns
  `(hits, warnings)`; each platform `except`
  ([service.py:65](../../../ModpackManager/modpack_manager/service.py:65),
  [service.py:70](../../../ModpackManager/modpack_manager/service.py:70)) appends a `Notice`.

### 5.4 Webapp routes
[webapp.py](../../../ModpackManager/modpack_manager/webapp.py) `create_app` keeps its DI
signature; only the payload shapes and the cache key change:
- `cache` holds `{"scan": None, "last_touched": []}` (was `"candidates"`).
- `GET /api/updates`
  ([webapp.py:24](../../../ModpackManager/modpack_manager/webapp.py:24)) stores
  `cache["scan"] = scan_fn()` (a `ScanResult`) on cold/`refresh`, and returns
  `{"candidates": [c.to_dict() …], "warnings": [w.to_dict() …]}`.
- `POST /api/generate`
  ([webapp.py:49](../../../ModpackManager/modpack_manager/webapp.py:49)) passes
  `cache["scan"].candidates if cache["scan"] else None` to `generate_fn` (was
  `cache["candidates"]`).
- `GET /api/search`
  ([webapp.py:34](../../../ModpackManager/modpack_manager/webapp.py:34)) unpacks
  `hits, warnings = search_fn(...)` and returns `{"hits": [...], "warnings": [...]}`.

### 5.5 Loader map in generate
`_server_element` gains a `loader` parameter and looks up a module-level
`(mainClass, launcherType)` map (§7.4); `write_batch_xml`
([generate.py:52](../../../ModpackManager/modpack_manager/generate.py:52)) threads
`config.loader` through from its one caller
([service.py:158](../../../ModpackManager/modpack_manager/service.py:158)).

### 5.6 Frontend
No new persistent state beyond a `state.dismissed` set (notice `code`s hidden this
session). New `renderWarnings(list, container)` helper; `load()` and `runSearch()` call
it. A `#scan-warnings` container is added to `index.html`.

## 6. Data shapes

```python
# sources/base.py — new; serialized under the "warnings" JSON key
@dataclass
class Notice:
    level: str          # "warn" | "info"
    code: str           # stable id for dedup/dismissal/tests, e.g. "curseforge_search_failed"
    message: str        # human text for the banner
    def to_dict(self) -> dict: ...   # asdict(self), matching Candidate/SearchHit

# updates.py — scan() return type (a light container, not a dataclass is fine too)
@dataclass
class ScanResult:
    candidates: list[Candidate]
    warnings: list[Notice]
```

```jsonc
// GET /api/updates — additive; existing "candidates" unchanged
{ "candidates": [ /* Candidate.to_dict(), unchanged */ ],
  "warnings": [ { "level": "warn", "code": "deps_unresolved",
                  "message": "Dependency resolution failed — …" } ] }

// GET /api/search — additive; existing "hits" unchanged
{ "hits": [ /* SearchHit.to_dict() */ ],
  "warnings": [ { "level": "warn", "code": "curseforge_search_failed",
                  "message": "CurseForge search failed — showing Modrinth results only." } ] }
```

Stable `code`s (the full set this spec introduces):

| code | level | raised at |
|---|---|---|
| `modrinth_search_failed` | warn | [service.py:65](../../../ModpackManager/modpack_manager/service.py:65) |
| `curseforge_search_failed` | warn | [service.py:70](../../../ModpackManager/modpack_manager/service.py:70) |
| `deps_unresolved` | warn | [updates.py:107](../../../ModpackManager/modpack_manager/updates.py:107) |
| `modrinth_bulk_fallback` | info | [updates.py:47](../../../ModpackManager/modpack_manager/updates.py:47) |
| `curseforge_bulk_fallback` | info | [updates.py:61](../../../ModpackManager/modpack_manager/updates.py:61) |

## 7. Backend details

### 7.1 The `Retry` policy (`sources/http.py`)
Proposed constant (numbers are the tunable open question — §Open questions):

```python
_RETRY = Retry(
    total=3, connect=3, read=3, status=3,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET", "POST"}),   # POST opted in: bulk lookups are read-only
    backoff_factor=0.5,            # sleeps ~0.5s, 1s, 2s between attempts
    backoff_max=30,                # cap a single backoff (also caps a huge Retry-After via backoff, see note)
    respect_retry_after_header=True,
    raise_on_status=True,          # exhausted -> raise, caught by existing per-mod isolation (KD2)
)
```

Notes that matter:
- `allowed_methods` is the current name (urllib3 ≥1.26 / v2); it replaces the deprecated
  `method_whitelist`. Verify the installed urllib3 major version and use the right kwarg.
- With `respect_retry_after_header=True`, a `429`/`503` carrying `Retry-After` is honored
  automatically. A hostile/huge `Retry-After` is a theoretical hang risk; keep the overall
  scan bounded by the fact that the scan already runs under a thread pool and each request
  keeps its `timeout=`. (If needed, cap via `backoff_max` and treat `Retry-After` beyond
  it as the cap — decide during implementation.)
- Retries are **per-request**, so the concurrent scan
  ([updates.py:81](../../../ModpackManager/modpack_manager/updates.py:81)) still overlaps
  waits across mods.

### 7.2 CurseForge changelog fan-out (the 429 hotspot)
`build_candidate` fetches one changelog per newer file, in a comprehension over `newer`
([curseforge.py:124](../../../ModpackManager/modpack_manager/sources/curseforge.py:124)),
each a `GET …/files/{id}/changelog`
([curseforge.py:83](../../../ModpackManager/modpack_manager/sources/curseforge.py:83)).
Across CF mods built concurrently, this is the burstiest call pattern and the most likely
429 source. Two facts make the shared adapter the right fix:
- `_changelog` returns `""` on any non-`200`
  ([curseforge.py:85](../../../ModpackManager/modpack_manager/sources/curseforge.py:85)) —
  so **without** retries a rate-limited changelog silently becomes a blank changelog. With
  the adapter, the `429` is retried and `Retry-After`-honored *before* that check, so the
  changelog actually arrives.
- No code change to `_changelog` is required; it inherits resilience from the session.

If 429s still bite after retries, the escalation (deferred, §11) is to cap the changelog
range or cache changelog bodies — not to widen the retry.

### 7.3 Where warnings are recorded
- **Search** ([service.py:58](../../../ModpackManager/modpack_manager/service.py:58)):
  keep the two `try/except` blocks; in each `except`, append
  `Notice("warn", "<platform>_search_failed", "<Platform> search failed — showing <other> results only.")`.
  Tailor the message to which platform(s) were requested (if only CurseForge was
  requested and it failed, say so plainly rather than "showing Modrinth only").
- **Dependencies**
  ([updates.py:94](../../../ModpackManager/modpack_manager/updates.py:94)): the `except`
  that currently bare-`return`s
  ([updates.py:107](../../../ModpackManager/modpack_manager/updates.py:107)) returns
  `Notice("warn", "deps_unresolved", …)`; the happy path returns `None`. Behavior on
  failure is otherwise unchanged (deps stay `addable=False`, banners still show per the
  dependency-auto-add spec).
- **Bulk prefilters** ([updates.py:38](../../../ModpackManager/modpack_manager/updates.py:38),
  [updates.py:51](../../../ModpackManager/modpack_manager/updates.py:51)): the `except`
  that falls back to per-mod also returns `Notice("info", "<platform>_bulk_fallback", …)`.
  These are **info**, because the fallback path still yields complete results (KD4).

`scan()` collects whatever notices come back and returns
`ScanResult(sorted_candidates, warnings)`.

### 7.4 Loader map + the inertness caveat (KD5)
```python
# generate.py
_LAUNCH = {   # loader -> (mainClass, launcherType)
    "neoforge": ("cpw.mods.bootstraplauncher.BootstrapLauncher", "Vanilla"),
    "forge":    ("cpw.mods.bootstraplauncher.BootstrapLauncher", "Vanilla"),  # modern Forge (1.17+) also BootstrapLauncher
    "fabric":   ("net.fabricmc.loader.impl.launch.knot.KnotClient", "Vanilla"),   # VERIFY (§Open questions)
    "quilt":    ("org.quiltmc.loader.impl.launch.knot.KnotClient", "Vanilla"),    # VERIFY (§Open questions)
}
_DEFAULT_LAUNCH = _LAUNCH["neoforge"]   # unknown loader -> today's values; this pack never regresses
```
`_server_element(root, mc_version, loader)` sets
`main_class, launcher_type = _LAUNCH.get((loader or "").lower(), _DEFAULT_LAUNCH)`.

**Investigation — does this per-update `mainClass` even matter?** No, not for launching
this pack, and the design is honest about that:
- A generated update file carries `mainClass`/`launcherType` on its own `<Server>` but
  **no `<Loader>` element** — only `<Module>`s (see
  [updates/updates-2026-05-01.xml:3](../../../updates/updates-2026-05-01.xml:3)). Same for
  the base layer ([updates/base.xml:3](../../../updates/base.xml:3)).
- The pack the maintainer actually selects in MCUpdater is the **entry** pack —
  `GearsAndFrontiers_Preview.xml` — whose `<Server>` supplies the authoritative
  `mainClass` *and* the launch-critical `<Loader type="NeoForge" …>`
  ([GearsAndFrontiers_Preview.xml:3](../../../GearsAndFrontiers_Preview.xml:3),
  [GearsAndFrontiers_Preview.xml:14](../../../GearsAndFrontiers_Preview.xml:14)), and
  pulls the update files in via `<Import>`
  ([GearsAndFrontiers_Preview.xml:6](../../../GearsAndFrontiers_Preview.xml:6)) purely for
  their `<Module>`s.
- Therefore the imported update `<Server>`'s launch attributes are **not consulted at
  launch**. Fixing the map is (a) correctness hygiene — generated files stop asserting a
  loader that contradicts `config.loader`; (b) future-proofing a Fabric/Quilt fork; and
  (c) a two-line change. It is **not** a live launch-bug fix, and the spec says so rather
  than overclaiming. The NeoForge default guarantees the current pack's output is byte-for-byte
  unchanged.

## 8. Frontend details

- **`renderWarnings(warnings, container)`** (new, pure) — clears `container`; for each
  notice not in `state.dismissed`, appends a row: severity class (`warn` → the amber
  `.dep` look, [style.css:42](../../../ModpackManager/modpack_manager/web/style.css:42);
  `info` → a muted variant), the `message` (escaped via `esc`,
  [app.js:8](../../../ModpackManager/modpack_manager/web/app.js:8)), and an ✕ that adds
  `code` to `state.dismissed` and re-renders. Hidden entirely when the list is empty.
- **`load()`** ([app.js:22](../../../ModpackManager/modpack_manager/web/app.js:22)) — after
  `state.candidates = data.candidates`, call
  `renderWarnings(data.warnings || [], $("#scan-warnings"))`. A `refresh` load clears
  `state.dismissed` first (a fresh scan re-earns the right to warn).
- **`runSearch()`** ([app.js:89](../../../ModpackManager/modpack_manager/web/app.js:89)) —
  render `data.warnings` into a note element above `#add-results` before rendering hits;
  clear it at the top of each search.
- **`index.html`** — add `<div id="scan-warnings"></div>` at the top of the Updates panel
  ([index.html:23](../../../ModpackManager/modpack_manager/web/index.html:23)) and a note
  slot in the Add panel.
- **Styling** — reuse `.dep`
  ([style.css:42](../../../ModpackManager/modpack_manager/web/style.css:42)) for `warn`;
  add a `.notice.info` muted variant (grey border/text on `--panel`) and a small ✕ button.
  No new palette.

## 9. Error handling / edge cases

- **Transient blip during scan** → retried transparently; the mod appears normally instead
  of as an error row. No warning (it succeeded).
- **Hard failure after retries** (mod) → one `status="error"` candidate, exactly as today
  ([updates.py:29](../../../ModpackManager/modpack_manager/updates.py:29)); no scan-level
  warning (the row is the signal).
- **A whole platform's search fails** → its `Notice` is emitted and the *other* platform's
  hits still render (partial results, now labeled).
- **Both search platforms fail** → two notices; empty results. (Distinguish from "no
  matches", which stays the existing empty-state copy,
  [app.js:105](../../../ModpackManager/modpack_manager/web/app.js:105).)
- **CurseForge has no API key** → unchanged: `search` returns `[]` with no exception
  ([curseforge.py:238](../../../ModpackManager/modpack_manager/sources/curseforge.py:238))
  so **no** search warning; the scan still emits per-mod "No CurseForge API key configured"
  error rows ([curseforge.py:92](../../../ModpackManager/modpack_manager/sources/curseforge.py:92)).
  (An optional derived roll-up notice is noted in §11, not built here.)
- **Dependency resolution fails** → `deps_unresolved` warn; deps stay un-queued and the
  per-mod changelog banners still advise manual add (dependency-auto-add spec §4.2).
- **Bulk prefilter fails** → `info` fallback notice; results complete, just slower.
- **`Retry-After` present** → honored automatically; the scan is slower but correct.
- **urllib3 version mismatch** (`allowed_methods` vs `method_whitelist`) → caught at
  implementation time by the unit test in §10 that asserts POST is retried.
- **Generate download blip** → connect/DNS retried; a mid-stream failure still raises and
  becomes a generate failure with the failed id
  ([service.py:130](../../../ModpackManager/modpack_manager/service.py:130)), unchanged.
- **Unknown / future loader in config** → falls back to the NeoForge pair (KD5); output
  unchanged for this pack.

## 10. Testing

`pytest`, mocking HTTP with `responses` exactly as the existing source tests do
([test_modrinth.py](../../../ModpackManager/tests/test_modrinth.py)).

**`sources/http.py` (the risky core):**
- `build_session` mounts an adapter whose `max_retries` has the expected
  `status_forcelist`, `backoff_factor`, and **includes POST** in `allowed_methods` (guards
  the urllib3-kwarg-name pitfall).
- A `responses`-registered endpoint returning `503` then `200` is fetched through a
  `build_session()` session and yields the `200` (retry actually fires). `responses`
  supports sequential responses for one URL, so this is expressible without real sleeps
  (assert on the recorded call count; keep `backoff_factor` overridable or patched to `0`
  in the test to avoid wall-clock delay).
- A `429` with `Retry-After: 0` is retried and then succeeds.
- Non-transient `404` is **not** retried (single call recorded).

**Warnings plumbing:**
- `real_search`: monkeypatch `curseforge.search` to raise → returns
  `(modrinth_hits, [Notice(code="curseforge_search_failed", level="warn")])`; Modrinth hits
  still present. Symmetric test for Modrinth failing.
- `updates.scan`: force `_resolve_dependencies` to raise → `ScanResult.warnings` contains
  `deps_unresolved`; candidates still returned and sorted. Force a bulk prefilter to raise
  → an `info` `*_bulk_fallback` notice, and the per-mod fallback still produces candidates.
- No failures → `ScanResult.warnings == []`.

**Webapp** (injected fakes, matching the existing DI in
[test_webapp.py](../../../ModpackManager/tests/test_webapp.py) — the `scan_fn` fake now
returns a `ScanResult`, and `search_fn` returns `(hits, warnings)`):
- `GET /api/updates` returns both `candidates` and `warnings`; the generate path still
  receives `cache["scan"].candidates` (extend the existing
  `test_generate_streams_progress_then_result`).
- `GET /api/search` returns `hits` + `warnings`.

**Generate loader map** (extends
[test_generate.py](../../../ModpackManager/tests/test_generate.py)):
- `write_batch_xml(..., loader="neoforge")` → `<Server>` has the BootstrapLauncher
  `mainClass` + `launcherType="Vanilla"` (output identical to today — regression guard).
- `loader="fabric"` → the mapped Fabric `mainClass`.
- `loader="somethingelse"` → falls back to the NeoForge pair.

**Frontend** has no JS runner (vanilla JS), so verify by running the app via the
`ModpackManager:verify` skill / `run.ps1`: with CurseForge's key temporarily blanked or a
platform forced to fail, confirm the Updates banner and the search note appear, are
dismissible, and don't reappear until a refresh; confirm a clean scan shows no banner.

## Open questions

1. **Retry parameters.** `total=3`, `backoff_factor=0.5`, `backoff_max=30`,
   `status_forcelist={429,500,502,503,504}` are proposed defaults. Worth a quick check of
   real CurseForge/Modrinth 429 behavior (do they send `Retry-After`? how long?) to tune
   attempts vs. total scan latency. Also decide the policy for an absurd `Retry-After`
   (cap at `backoff_max` vs. honor verbatim).
2. **Fabric/Quilt `mainClass` + `launcherType`.** The NeoForge/Forge pair is
   high-confidence (matches [updates/base.xml:3](../../../updates/base.xml:3)). The
   Fabric/Quilt `KnotClient` strings and the assumption that `launcherType` stays
   `"Vanilla"` for them are **unverified** against MCUpdater's `ServerPackv2.xsd` / source
   — this repo is NeoForge-only, so there's no in-repo evidence. Verify before relying on a
   Fabric fork; the NeoForge default means shipping the map now is safe regardless.
3. **Should the per-update `<Server>` carry launch attributes at all?** Since they're inert
   under `<Import>` (§7.4), the most minimal "correct" option is to *omit*
   `mainClass`/`launcherType` from generated update files. We chose to keep + fix them
   (matches the base/preview convention and avoids tripping a strict schema validator), but
   dropping them is a legitimate alternative to weigh in review.
4. **Warning-surfacing UX granularity.** A single dismissible banner is proposed. Open:
   whether `info`-level fallbacks deserve surfacing at all (they're purely performance) or
   should be logged-only, leaving the banner for `warn` and above.

## 11. Deferred (v2)

- **Client-side rate limiting** (token bucket / concurrency cap for CurseForge) if
  `Retry-After` backoff proves insufficient under real load.
- **Changelog reduction**: cache changelog bodies, or cap the fetched `newer` range, to cut
  the CF fan-out ([curseforge.py:124](../../../ModpackManager/modpack_manager/sources/curseforge.py:124))
  at the source rather than absorbing 429s.
- **Derived config notices** (e.g. a single "CurseForge API key not configured — N mods
  skipped" roll-up from the error rows) instead of only per-mod error rows.
- **Parallel downloads + thread-safe `HashCache`** during generate — carried over from the
  close-the-loop spec's deferred list, and now sharing this spec's retrying download session.
- **Structured retry/telemetry logging** (how often retries fire, which hosts 429) to inform
  the v2 rate-limit decision.
