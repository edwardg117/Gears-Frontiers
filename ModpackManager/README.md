# Modpack Manager — Update Picker

Local web app to review mod changelogs and pick which updates to apply to the
Gears & Frontiers pack. Reads the pack XML at the repo root and writes a filtered
`updates/updates-YYYY-MM-DD.xml`, wiring it into `GearsAndFrontiers_Preview.xml`.

## Run (easiest)

Double-click **`run.bat`** (or from a terminal: `.\run.bat`). On the first run it
creates a local virtual environment and installs dependencies, then launches the
app; every run after that just launches it. PowerShell users can run **`run.ps1`**
instead (`powershell -ExecutionPolicy Bypass -File .\run.ps1` if it's blocked).

Your browser opens at http://127.0.0.1:5178/. Pick mods, read changelogs, and
click **Generate preview**. Then review the git diff, test the Preview pack in
MCUpdater, and promote to the main pack manually. Press **Ctrl+C** to stop.

## Run (manual)

```bash
cd ModpackManager
python -m venv .venv                                    # first time only
.venv/Scripts/python -m pip install -r requirements.txt # first time only
.venv/Scripts/python -m pip install -e .                # first time only
.venv/Scripts/python -m modpack_manager                 # launch
```

## How it works

- **Scan** parses the pack layers (in the Preview pack's `<Import>` order) into
  the current mod state, then queries Modrinth + CurseForge for newer versions
  and the changelogs in between.
- **Generate** downloads only the jars you selected, computes the real
  lowercase-hex **MD5** and exact byte size MCUpdater expects, writes the dated
  update file, and adds its `<Import>` + a revision bump to the Preview pack.
- The tool performs **no git actions** and never edits the main pack.

## Test

```bash
cd ModpackManager
.venv/Scripts/python -m pytest -v
```
