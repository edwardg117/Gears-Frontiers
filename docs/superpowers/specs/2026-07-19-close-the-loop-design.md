# Close the Loop — Preview Diff & Local Commit (Design)

- **Date:** 2026-07-19
- **Status:** Approved for planning
- **Builds on:** [2026-07-18-modpack-pack-manager-design.md](2026-07-18-modpack-pack-manager-design.md), [2026-07-17-modpack-update-picker-design.md](2026-07-17-modpack-update-picker-design.md)
- **Repo:** Gears & Frontiers (MCUpdater modpack, NeoForge 1.21.1)

## 1. Problem / goal

Today the generate step ends at the working-tree boundary. `generate()`
([app.js:257](../../../ModpackManager/modpack_manager/web/app.js:257)) fires one
POST, shows a static "Downloading and hashing N jar(s)…" line while the backend
downloads + hashes jars **serially**
([service.py:107](../../../ModpackManager/modpack_manager/service.py:107)), then
prints a one-line "Wrote the file — review the git diff, then commit & push."
The maintainer must then leave for a terminal to (a) see what actually changed,
and (b) commit it.

Goal: **close that loop inside the app** — make generation observable and let the
maintainer review the exact diff and commit the Preview changes without a terminal
trip, while preserving the tool's core safety stance: **it never edits the `main`
pack and never pushes.**

## 2. Key decisions

- **Commit the Preview, never `main`; never push.** The tool already fully owns
  the two files it writes (the dated update file + the Preview pack). It may stage
  and commit *exactly those two paths* locally. Promoting to the `main` pack and
  `git push` stay manual. (Chosen scope over "observe-only" and "full promote".)
- **Streaming generate.** `POST /api/generate` becomes an **NDJSON stream**: one
  progress line per jar, then a terminal result line. One request, POST-friendly
  (the payload is a JSON body, so `EventSource`/GET is unsuitable). Downloads stay
  **serial** — parallelizing them is the separate reliability track (§11).
- **Server-held touched paths — the client never names files to stage.** After a
  successful stream the route records the exact repo-relative paths written in the
  same in-memory `cache` the candidates already live in
  ([webapp.py:11](../../../ModpackManager/modpack_manager/webapp.py:11)).
  `/api/commit` and `/api/discard` act on `cache["last_touched"]` only. No
  client-supplied path ever reaches git — staging is provably limited to the two
  files the tool just wrote.
- **Isolated `git_ops.py`.** All subprocess/git logic lives in one small module
  with the "only these paths, never `-A`" discipline baked in, so it's unit-tested
  against a temp repo independently of Flask.
- **YubiKey-aware commit.** Commits are signed and block on a physical touch; the
  UI surfaces a "touch your key" state and tolerates a timeout without losing work
  (files stay staged).
- **Discard safety valve.** Generate mutates the working tree *before* any commit;
  a Discard action reverts exactly the two touched files so "generate then change
  my mind" no longer leaves a dirty tree to clean by hand.
- **The tool's commits are the maintainer's own.** Auto-message is a conventional
  `chore(preview): …`, editable before commit. **No `Co-Authored-By: Claude`
  trailer** — these commits are authored under the user's identity.

## 3. Non-goals (v1)

- **No promote-to-`main`.** The tool never reads, writes, or commits the main pack.
- **No push.** Local commit only; the user pushes when ready.
- **No download parallelization or retry/backoff.** Serial download is unchanged;
  reliability hardening is a separate track (§11).
- **No multi-batch / cross-day staging.** Commit/discard operate on the single most
  recent generate in this session.
- **No commit amend / history UI.** One forward commit per generate.

## 4. UX

The `Generate preview →` button
([index.html:57](../../../ModpackManager/modpack_manager/web/index.html:57))
keeps its trigger. The `#status` bar is replaced as the primary feedback surface by
a **Result modal** reusing the existing `.review-overlay` styling
([style.css:67](../../../ModpackManager/modpack_manager/web/style.css:67)). The
modal moves through states:

### 4.1 Progress (while streaming)
Spinner + live readout `Hashing 3 / 12 · SomeMod…` driven by the NDJSON stream, so
a large batch never looks frozen. Cancel isn't offered in v1 (downloads are short
and serial; closing the tab aborts).

### 4.2 Result (stream complete, files written)
- **Summary** (top, the star): `Updates (5)`, `Adds (2)`, `Removals (1)` with
  version transitions — the same shape the Review panel already renders
  ([app.js:230](../../../ModpackManager/modpack_manager/web/app.js:230)) — plus,
  when relevant, a muted line `⚠ N mods in this scan need manual updating`
  (CurseForge distribution-blocked candidates, `status === "manual"`), so the
  maintainer can see what generation *couldn't* include.
- **Diff** (below, shown by default, scrollable): the actual unified `git diff` of
  the two touched files, `+`/`−` line coloring, monospaced, **no external library**
  (parse unified-diff lines, class by leading char). Large but fine for localhost.
- **Actions**: `Commit preview` (primary) with an **editable commit-message input**
  prefilled per §6; `Discard changes` (destructive, confirm first); `Close`.

### 4.3 Committing
Message box + buttons disabled; spinner with **"Touch your YubiKey to sign the
commit…"**. This request can take many seconds.

### 4.4 Committed
`Committed a1b2c3d ✓ — run \`git push\` when ready.` + `Close`. The push hint is
copy-selectable. Re-opening generate starts a fresh cycle.

### 4.5 Error surfaces
- **Generate failures** (some jars failed to download → nothing written,
  [service.py:138](../../../ModpackManager/modpack_manager/service.py:138)): the
  result state lists the failed ids and shows **no Commit option** (there is nothing
  to commit); `Close` only.
- **Commit timeout / signing error**: clear message ("Key touch timed out — files
  are staged; retry or commit from a terminal."); files remain staged; `Retry` and
  `Close` offered.
- **Discard error**: message + the tree is left as-is (no partial revert beyond what
  git already did).

## 5. Architecture

### 5.1 Backend — new `git_ops.py`
A thin wrapper over `git` via `subprocess.run(["git", "-C", str(root), …])`. Pure
functions, no Flask imports, each limited to an explicit pathspec:

- `diff(root, paths) -> str` — **read-only** (no git state mutation, so closing the
  modal without acting leaves the tree exactly as generate left it). Per path: a
  tracked+modified file → `git diff -- <path>`; an untracked new file →
  `git diff --no-index -- /dev/null <path>` (git special-cases `/dev/null`
  cross-platform; it **exits 1 when differences exist**, which the wrapper must
  treat as success, not error). Concatenate and return the unified text.
- `commit(root, paths, message) -> CommitResult` — `git add -- <paths>` (stages the
  two files, including the new update file), then
  `git commit -m <message> -- <paths>`. The **commit pathspec** guarantees other
  pre-staged, unrelated working-tree changes are excluded from the commit. Returns
  the new short SHA (`git rev-parse --short HEAD`) on success. Runs with a generous
  timeout (≈120 s) to allow the YubiKey touch; on `TimeoutExpired` the process is
  killed and a timeout error is returned with files left staged.
- `discard(root, paths)` — per path, read `git status --porcelain -- <path>`:
  tracked+modified → `git restore -- <path>` (revert to HEAD); untracked → delete
  the file from disk. (No intent-to-add to unwind, since `diff` is read-only.)
- Small helpers: `_status(root, path)`, `_is_untracked(root, path)`.

**Discipline (load-bearing):** every call passes an explicit pathspec of the two
known files. There is no code path that runs `git add -A`/`git add .` or commits
the whole index. This is what keeps the maintainer's unrelated dirty files
(`mod_update_automation.py`, `configs/ftbquests/*`, `updates/local.xml` at the time
of writing) untouched. It is covered by a dedicated test (§10).

### 5.2 Backend — service becomes a generator
`real_generate`
([service.py:95](../../../ModpackManager/modpack_manager/service.py:95)) is split:

- `generate_events(payload, candidates)` — a **generator**. It performs the same
  parse → build entries → serial download/hash → write XML → wire preview logic,
  but `yield`s a `{"type": "progress", "i", "n", "name"}` event before each jar's
  `compute(...)`, and finally `yield`s `{"type": "result", …}` (the current result
  dict, extended per §6 with `touched_files`). The `candidates is None → real_scan()`
  fallback ([service.py:100](../../../ModpackManager/modpack_manager/service.py:100))
  is preserved (emitted as an initial `{"type": "progress", "phase": "scanning"}`).
- `real_generate(payload, candidates)` is kept as a thin drain of `generate_events`
  returning the final result dict, so any non-streaming caller/test path is
  unchanged.
- `real_commit()` / `real_discard()` — new service fns that resolve `pack_paths()`
  and delegate to `git_ops` with the repo root
  ([paths.py](../../../ModpackManager/modpack_manager/paths.py) `root`) and the two
  touched paths handed in by the route.

### 5.3 Backend — webapp routes
[webapp.py](../../../ModpackManager/modpack_manager/webapp.py) `create_app` gains
two injected fns (`commit_fn`, `discard_fn`) and `generate_fn` becomes the
**event generator**:

- `POST /api/generate` → `Response(stream_with_context(_ndjson(generate_fn(payload,
  cache["candidates"]))), mimetype="application/x-ndjson")`. `_ndjson` serializes
  each event as `json.dumps(evt) + "\n"`. On the terminal `result` event the route
  stores `cache["last_touched"] = result["touched_files"]` before yielding it.
- `POST /api/commit` `{message}` → `commit_fn(cache["last_touched"], message)`; 400
  if `last_touched` is empty (no prior generate this session) or message blank.
- `POST /api/discard` → `discard_fn(cache["last_touched"])`; clears
  `cache["last_touched"]` on success.

`__main__.py`
([__main__.py:14](../../../ModpackManager/modpack_manager/__main__.py:14)) wiring
adds `commit_fn=real_commit, discard_fn=real_discard` and passes the generator
`generate_fn=generate_events`.

### 5.4 Frontend
No new persistent state beyond a transient `state.lastResult` (summary + diff for
the open modal) and the message-box value. The Result modal is a new block in
[index.html](../../../ModpackManager/modpack_manager/web/index.html) parallel to
`#review`. `generate()`
([app.js:257](../../../ModpackManager/modpack_manager/web/app.js:257)) is rewritten
to consume the stream (§8).

## 6. Data shapes

```jsonc
// NDJSON stream from POST /api/generate — one object per line
{ "type": "progress", "phase": "scanning" }              // optional, if re-scanning
{ "type": "progress", "i": 1, "n": 12, "name": "SomeMod" } // before each jar hash
// … more progress …
{ "type": "result",
  "written_file": "updates/updates-2026-07-19.xml",       // or null
  "new_revision": "43",                                    // or null
  "mods": [ /* existing summary entries */ ],
  "failures": [ { "id": "...", "error": "..." } ],
  "note": "…",                                             // when nothing written
  "touched_files": [                                       // NEW — repo-root-relative
    "updates/updates-2026-07-19.xml",
    "GearsAndFrontiers_Preview.xml"
  ],
  "diff": "diff --git a/…",                                // NEW — unified diff text
  "manual_count": 2                                        // NEW — status=="manual" in scan
}
```

```jsonc
// POST /api/commit request
{ "message": "chore(preview): update 2026-07-19 — 5 updates, 2 adds, 1 removal" }
// response
{ "ok": true, "sha": "a1b2c3d" }
// or
{ "ok": false, "error": "Key touch timed out — files are staged.", "timeout": true }
```

Default commit message (frontend-built from the batch summary, backend accepts as
given): `chore(preview): update <YYYY-MM-DD> — <u> updates, <a> adds, <r> removals`
(pluralization handled; zero-count segments dropped). Single line, no trailer.

`touched_files` are the only two paths that exist: the dated update file (from
`written_file`) and the Preview pack basename
(`GearsAndFrontiers_Preview.xml`, resolved from
[paths.py](../../../ModpackManager/modpack_manager/paths.py) `preview_pack`
relative to `root`). Both are computed server-side; the client sends neither.

## 7. Backend details

### 7.1 Streaming + touched paths
`generate_events` yields the same final result `real_generate` produces today, plus
`touched_files`, `diff`, and `manual_count`:
- `touched_files`: `[written_file, <preview rel path>]` — only when `written_file`
  is set (a real write happened). Empty on failures/nothing-written, so the route
  leaves `cache["last_touched"]` empty and Commit stays unavailable.
- `diff`: `git_ops.diff(root, touched_files)` computed **after** the write. Skipped
  (empty) when nothing was written.
- `manual_count`: count of `candidates` with `status == "manual"` — surfaced in the
  summary (§4.2). Derived from the same `candidates` the generate used.

### 7.2 Commit
`real_commit(touched, message)` → `git_ops.commit(root, touched, message)`. Guards:
non-empty `touched`, non-blank `message`. The `git add -- <paths>` + `git commit -m
<message> -- <paths>` sequence commits **only** those paths even if the user has
other staged changes. Signing (YubiKey) happens transparently inside `git commit`;
the ≈120 s timeout accommodates the touch. Success returns the short SHA.

### 7.3 Discard
`real_discard(touched)` → `git_ops.discard(root, touched)`. The Preview pack (always
tracked) is `git restore`d to HEAD; the update file is deleted if it was newly
created this generate, or `git restore`d if regenerating an existing dated file.
Clears `cache["last_touched"]`.

## 8. Frontend details

- **`generate()`** — POSTs the payload, then reads the response body as a stream
  (`res.body.getReader()` + `TextDecoder`), splitting on `\n` and `JSON.parse`-ing
  each line. `progress` events update the modal's readout; the `result` event stores
  `state.lastResult` and renders the Result state (§4.2). A fetch/stream error shows
  the error state. The pre-generate empty-batch guard
  ([app.js:264](../../../ModpackManager/modpack_manager/web/app.js:264)) is kept.
- **`renderResult(result)`** — builds the summary (reusing the Review render helpers)
  + the `manual_count` line + the diff view, wires the three action buttons and the
  message input (prefilled per §6).
- **`renderDiff(text)`** — splits `text` on newlines; each line → a `<div>` with a
  class by leading char (`+` add, `-` del, `@` hunk, else context). Escaped via the
  existing `esc()` ([app.js:8](../../../ModpackManager/modpack_manager/web/app.js:8)).
- **`commitPreview()`** — POST `/api/commit` `{message}`; show Committing state;
  on `{ok:true}` → Committed state with the SHA; on `{ok:false}` → error state
  (Retry re-POSTs). 
- **`discardChanges()`** — `confirm()` first; POST `/api/discard`; on success close
  the modal and reset the batch feedback; on error show the message.
- The old `#status` bar is retained only as a thin fallback for pre-generate guards
  (e.g. "Nothing queued.").

### Styling
Reuse `.review-overlay` / `.review-panel` / `.review-foot`
([style.css:67](../../../ModpackManager/modpack_manager/web/style.css:67)). Add:
`.diff` (monospace, `overflow:auto`, small font); `.diff .add` (green, `--patch`
tint), `.diff .del` (red, `--major` tint), `.diff .hunk` (muted/accent), matching
the existing severity palette
([style.css:1](../../../ModpackManager/modpack_manager/web/style.css:1)). A
destructive `.btn-danger` for Discard (red border/text). Commit-message `<input>`
reuses the `.add-search input` styling.

## 9. Error handling / edge cases

- **Nothing queued** → existing guard; no request sent.
- **Some jars fail to download** → result has `failures`, no `written_file`, empty
  `touched_files`; modal shows failures, Commit unavailable.
- **Commit with no prior generate this session** (`last_touched` empty) → 400; the
  UI only enables Commit after a successful result, so this is defense-in-depth.
- **YubiKey touch times out** → `{ok:false, timeout:true}`; files stay staged; Retry
  available; the user can also finish in a terminal.
- **Unrelated dirty files present** → never staged or committed (pathspec discipline,
  §5.1); verified by test.
- **Regenerate same day** → the dated update file already exists and is tracked-or-
  modified; `diff` shows its modifications, commit re-commits it, discard restores it
  (not delete). `wire_into_preview` is idempotent for the Import line
  ([generate.py:92](../../../ModpackManager/modpack_manager/generate.py:92)) but
  bumps the revision each run — the diff makes that visible before commit.
- **Not a git repo / git missing** → `git_ops` surfaces the stderr; Commit/Discard
  show the error, generate + diff still work (diff falls back to empty with a note).
- **Stream interrupted** (tab closed mid-generate) → the backend may still finish
  writing; on next open the user can regenerate. No partial-commit risk (commit is a
  separate explicit action).

## 10. Testing

`git_ops.py` unit tests against a **temp git repo** (`git init`, seed a commit),
the risky core:
- `commit` stages + commits **only** the two named paths; a separately-modified
  unrelated file is **absent** from the commit and still dirty afterward (the
  load-bearing guarantee).
- `commit` of a batch that includes a **new untracked** update file adds + commits
  it; returns a SHA.
- `discard` deletes a newly-created update file and restores a modified tracked
  Preview file to HEAD, leaving unrelated dirty files alone.
- `diff` includes both a modified tracked file and a new untracked file (via
  `git add -N`).
- Commit **timeout** path (monkeypatch a slow/blocking `git commit`) → returns
  `timeout=True`, files remain staged.

Webapp tests (injected fakes, matching the existing `create_app` DI):
- `POST /api/generate` streams `progress`… then `result`; the route stores
  `last_touched` from the result.
- `POST /api/commit` calls `commit_fn` with the **stored** `last_touched` (not any
  client value) and the message; 400 when `last_touched` empty.
- `POST /api/discard` calls `discard_fn` with the stored paths and clears them.

`service` test: `generate_events` yields a progress event per jar and a terminal
result carrying `touched_files` + `diff`; `real_generate` still returns the final
dict unchanged (existing generate/write tests keep passing —
[generate.py](../../../ModpackManager/modpack_manager/generate.py) is untouched).

Frontend has no JS runner (vanilla JS), so the modal is verified by running the app
(`run.bat` / `run.ps1`): queue a small batch, watch per-jar progress, confirm the
diff matches `git diff`, commit (touch the key) and see the SHA, then in a fresh run
Discard and confirm `git status` returns to its prior state with unrelated dirty
files intact.

## 11. Deferred (v2)

- **Promote-to-`main`** as a separate, explicitly-confirmed guided action.
- **Push** after commit (single confirm, outward-facing).
- **Parallel downloads** during generate (thread pool + thread-safe `HashCache`),
  and **retry/backoff + 429 handling** on the API scans — the reliability track.
- **Amend / undo last commit** from the app.
- **Rich diff** (side-by-side, syntax-aware) over the raw unified view.
