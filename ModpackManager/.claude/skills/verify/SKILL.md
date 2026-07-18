---
name: verify
description: Launch and drive the ModpackManager update-picker (Flask app in modpack_manager/) to verify a change works end-to-end at its real surface. Use when verifying runtime behavior of ModpackManager changes.
---

# Verify — ModpackManager update picker

Local Flask app (`modpack_manager/`) that scans Modrinth/CurseForge for mod
updates and serves a browser UI at http://127.0.0.1:5178/. Verify by launching
it and driving the real surface — not by running tests (those are CI's job;
`pytest` here proves the suite runs, not that the app works).

## Launch

From `ModpackManager/` (the venv already exists; `run.ps1` / `run.bat`
bootstraps it on a cold machine):

```bash
.venv/Scripts/python -m modpack_manager   # serves 127.0.0.1:5178, BLOCKS — run in background
```

It auto-opens the system browser (harmless). The first `GET /api/updates` runs a
live scan (~30s) and caches it server-side, so later calls are instant until
`?refresh=1`.

Config: root `mod_update_config.ini`. Modrinth works anonymously (key may be
empty); CurseForge needs its key or CF candidates come back `status="error"`.

## Drive

The surface is the browser UI, but the update list is ~130 rows, so
`computer` / `screenshot` time out and `read_page` output is huge. Drive it two
ways instead:

- **API (fast backend check):** `GET /api/updates` returns the candidates JSON
  (names, versions, and `added_dependencies` with `addable` / `slug` /
  `download_url` / …). Also `/api/pack`, `/api/search?q=`,
  `/api/project-versions?platform=&id=`.
- **UI (real frontend behavior):** open the app in the browser pane
  (`preview_start` the URL), then use `javascript_tool` to read `state` and the
  rendered DOM (`#add-queue`, `#add-queue-count`, `#batch-summary`, `#reader`)
  and to invoke the app's own handlers — e.g. `computeAutoDeps()`,
  `toggleUpdate(id)`, `renderReader()` — observing the actual re-render. This
  beats pixel-clicking the long list.

## Gotchas

- **`POST /api/generate` is destructive:** it downloads jars, writes
  `updates/updates-YYYY-MM-DD.xml`, and bumps the Preview pack revision. Don't
  click **Generate** during verification. To check the payload safely, stub
  `window.fetch` to capture the `/api/generate` body and return a benign
  `{written_file:null}` response, then restore `fetch`.
- After verifying, kill the background server (it holds port 5178).
- `repo_root()` resolves from the package file path, so the launch cwd doesn't
  matter; but the app reads/writes pack files under the repo root.

## Tests (not runtime verification)

`.venv/Scripts/python -m pytest -q` runs the unit suite (mocked HTTP). Useful,
but it is not a substitute for launching the app.
