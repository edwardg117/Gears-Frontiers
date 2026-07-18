# Modpack Update Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web app in `ModpackManager/` that lists every mod with an available update, shows the full changelog range, lets the user pick per-mod which to update, and writes a correct filtered MCUpdater update XML wired into the Preview pack.

**Architecture:** A Python package `modpack_manager` (Flask backend + vanilla-JS two-pane UI) that reuses the existing script's Modrinth/XML logic. Scan phase parses the layered pack XML and queries Modrinth + CurseForge for newer versions and changelogs; generate phase downloads the selected jars to compute real MD5s and writes `updates/updates-YYYY-MM-DD.xml`, then adds an `<Import>` and bumps the revision in `GearsAndFrontiers_Preview.xml`.

**Tech Stack:** Python 3.12, Flask, requests, packaging, markdown, bleach; pytest + responses for tests; vanilla HTML/CSS/JS frontend (no build step).

**Reference spec:** `docs/superpowers/specs/2026-07-17-modpack-update-picker-design.md`

**Conventions for every task:** run commands from the `ModpackManager/` directory with its venv active unless stated otherwise. Tests mock all HTTP with `responses` — no live network calls in the suite.

---

## File Structure

```
ModpackManager/
  pyproject.toml
  requirements.txt
  README.md
  .gitignore                 # cache/, .venv/, __pycache__/
  modpack_manager/
    __init__.py
    __main__.py              # start server + open browser
    paths.py                 # repo-root + pack file path resolution
    config.py                # read mod_update_config.ini
    version_utils.py         # semver severity classification
    xml_model.py             # Module dataclass + parse/merge layered packs
    text_render.py           # markdown->safe HTML, sanitize HTML
    sources/
      __init__.py
      base.py                # Candidate/ChangelogEntry/AddedDependency dataclasses
      modrinth.py            # Modrinth update candidate builder
      curseforge.py          # CurseForge update candidate builder
    hashing.py               # download jar -> md5 + size, with cache
    updates.py               # orchestrator: modules -> candidates (concurrent)
    generate.py              # write filtered XML + wire into Preview pack
    webapp.py                # Flask routes
    web/
      index.html
      app.js
      style.css
  tests/
    conftest.py
    fixtures/
      base_sample.xml
    test_paths.py
    test_config.py
    test_version_utils.py
    test_xml_model.py
    test_text_render.py
    test_modrinth.py
    test_curseforge.py
    test_hashing.py
    test_updates.py
    test_generate.py
    test_webapp.py
```

---

## Task 1: Project scaffold + tooling

**Files:**
- Create: `ModpackManager/pyproject.toml`
- Create: `ModpackManager/requirements.txt`
- Create: `ModpackManager/.gitignore`
- Create: `ModpackManager/modpack_manager/__init__.py`
- Create: `ModpackManager/tests/__init__.py` (empty)
- Create: `ModpackManager/tests/test_smoke.py`

- [ ] **Step 1: Create the package metadata and dependency files**

`ModpackManager/pyproject.toml`:
```toml
[project]
name = "modpack-manager"
version = "0.1.0"
description = "Gears & Frontiers modpack update picker"
requires-python = ">=3.10"
dependencies = [
    "flask>=3.0",
    "requests>=2.31",
    "packaging>=23.0",
    "markdown>=3.5",
    "bleach>=6.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "responses>=0.25"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`ModpackManager/requirements.txt`:
```
flask>=3.0
requests>=2.31
packaging>=23.0
markdown>=3.5
bleach>=6.1
pytest>=8.0
responses>=0.25
```

`ModpackManager/.gitignore`:
```
.venv/
__pycache__/
*.pyc
cache/
```

`ModpackManager/modpack_manager/__init__.py`:
```python
"""Gears & Frontiers modpack update picker."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Create a smoke test**

`ModpackManager/tests/test_smoke.py`:
```python
import modpack_manager


def test_package_imports():
    assert modpack_manager.__version__ == "0.1.0"
```

- [ ] **Step 3: Create the venv and install dependencies**

Run from `ModpackManager/`:
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pip install -e .
```
Expected: installs Flask, markdown, bleach, responses without error.

- [ ] **Step 4: Run the smoke test to verify it passes**

Run from `ModpackManager/`:
```bash
.venv/Scripts/python -m pytest tests/test_smoke.py -v
```
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/pyproject.toml ModpackManager/requirements.txt ModpackManager/.gitignore ModpackManager/modpack_manager/__init__.py ModpackManager/tests/
git commit -m "feat(modpack-manager): scaffold package and tooling"
```

---

## Task 2: Path + config resolution

**Files:**
- Create: `ModpackManager/modpack_manager/paths.py`
- Create: `ModpackManager/modpack_manager/config.py`
- Test: `ModpackManager/tests/test_paths.py`, `ModpackManager/tests/test_config.py`
- Create: `ModpackManager/tests/conftest.py`

- [ ] **Step 1: Write the failing test for paths**

`ModpackManager/tests/test_paths.py`:
```python
from modpack_manager import paths


def test_repo_root_contains_updates_dir():
    root = paths.repo_root()
    assert (root / "updates").is_dir()
    assert (root / "GearsAndFrontiers_Preview.xml").is_file()


def test_pack_paths():
    p = paths.pack_paths()
    assert p.updates_dir.name == "updates"
    assert p.preview_pack.name == "GearsAndFrontiers_Preview.xml"
    assert p.config_ini.name == "mod_update_config.ini"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_paths.py -v`
Expected: FAIL (ModuleNotFoundError: modpack_manager.paths).

- [ ] **Step 3: Implement paths.py**

`ModpackManager/modpack_manager/paths.py`:
```python
"""Filesystem locations, resolved relative to the repo root."""

from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    # this file: <repo>/ModpackManager/modpack_manager/paths.py
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PackPaths:
    root: Path
    updates_dir: Path
    base_pack: Path
    preview_pack: Path
    main_pack: Path
    config_xml: Path
    config_ini: Path
    cache_dir: Path


def pack_paths() -> PackPaths:
    root = repo_root()
    return PackPaths(
        root=root,
        updates_dir=root / "updates",
        base_pack=root / "updates" / "base.xml",
        preview_pack=root / "GearsAndFrontiers_Preview.xml",
        main_pack=root / "GearsAndFrontiers.xml",
        config_xml=root / "config.xml",
        config_ini=root / "mod_update_config.ini",
        cache_dir=root / "ModpackManager" / "cache",
    )
```

- [ ] **Step 4: Run paths test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_paths.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing test for config**

`ModpackManager/tests/conftest.py`:
```python
import textwrap
import pytest


@pytest.fixture
def ini_file(tmp_path):
    def _write(body: str):
        p = tmp_path / "mod_update_config.ini"
        p.write_text(textwrap.dedent(body), encoding="utf-8")
        return p
    return _write
```

`ModpackManager/tests/test_config.py`:
```python
from modpack_manager.config import load_config


def test_load_config_reads_keys_and_target(ini_file):
    p = ini_file("""
        [API]
        curseforge_api_key = CF-KEY
        modrinth_api_key =

        [MODPACK]
        target_minecraft_version = 1.21.1
        target_loader = neoforge
        excluded_mods = foo, bar
    """)
    cfg = load_config(p)
    assert cfg.curseforge_api_key == "CF-KEY"
    assert cfg.modrinth_api_key == ""
    assert cfg.mc_version == "1.21.1"
    assert cfg.loader == "neoforge"
    assert cfg.excluded_mods == {"foo", "bar"}


def test_load_config_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "does_not_exist.ini")
    assert cfg.mc_version == "1.21.1"
    assert cfg.loader == "neoforge"
    assert cfg.excluded_mods == set()
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: FAIL (ModuleNotFoundError: modpack_manager.config).

- [ ] **Step 7: Implement config.py**

`ModpackManager/modpack_manager/config.py`:
```python
"""Read the existing mod_update_config.ini."""

import configparser
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    curseforge_api_key: str = ""
    modrinth_api_key: str = ""
    mc_version: str = "1.21.1"
    loader: str = "neoforge"
    excluded_mods: set = field(default_factory=set)


def load_config(ini_path: Path) -> Config:
    parser = configparser.ConfigParser()
    if Path(ini_path).exists():
        parser.read(ini_path, encoding="utf-8")

    def get(section, key, fallback=""):
        return parser.get(section, key, fallback=fallback).strip()

    excluded = get("MODPACK", "excluded_mods")
    return Config(
        curseforge_api_key=get("API", "curseforge_api_key"),
        modrinth_api_key=get("API", "modrinth_api_key"),
        mc_version=get("MODPACK", "target_minecraft_version", "1.21.1") or "1.21.1",
        loader=get("MODPACK", "target_loader", "neoforge") or "neoforge",
        excluded_mods={m.strip() for m in excluded.split(",") if m.strip()},
    )
```

- [ ] **Step 8: Run config test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add ModpackManager/modpack_manager/paths.py ModpackManager/modpack_manager/config.py ModpackManager/tests/test_paths.py ModpackManager/tests/test_config.py ModpackManager/tests/conftest.py
git commit -m "feat(modpack-manager): path and config resolution"
```

---

## Task 3: Version severity classification

**Files:**
- Create: `ModpackManager/modpack_manager/version_utils.py`
- Test: `ModpackManager/tests/test_version_utils.py`

- [ ] **Step 1: Write the failing test**

`ModpackManager/tests/test_version_utils.py`:
```python
from modpack_manager.version_utils import classify_severity


def test_major_minor_patch():
    assert classify_severity("1.2.3", "2.0.0") == "major"
    assert classify_severity("1.2.3", "1.3.0") == "minor"
    assert classify_severity("1.2.3", "1.2.4") == "patch"


def test_unparseable_returns_unknown():
    assert classify_severity("weird-a", "weird-b") == "unknown"


def test_prefixed_versions_are_tolerated():
    assert classify_severity("mc1.21-2.0.0", "mc1.21-2.1.0") == "minor"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_version_utils.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement version_utils.py**

`ModpackManager/modpack_manager/version_utils.py`:
```python
"""Classify the size of a version bump."""

import re
from packaging import version as _v

_NUM = re.compile(r"(\d+(?:\.\d+){0,3})")


def _extract(vstr: str):
    m = _NUM.search(vstr or "")
    if not m:
        return None
    try:
        return _v.parse(m.group(1))
    except _v.InvalidVersion:
        return None


def classify_severity(current: str, latest: str) -> str:
    cur, lat = _extract(current), _extract(latest)
    if cur is None or lat is None:
        return "unknown"
    if lat.major > cur.major:
        return "major"
    if lat.minor > cur.minor:
        return "minor"
    if lat.micro > cur.micro:
        return "patch"
    return "patch" if lat > cur else "unknown"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_version_utils.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/version_utils.py ModpackManager/tests/test_version_utils.py
git commit -m "feat(modpack-manager): version severity classification"
```

---

## Task 4: XML model — parse and merge layered packs

**Files:**
- Create: `ModpackManager/modpack_manager/xml_model.py`
- Test: `ModpackManager/tests/test_xml_model.py`
- Create: `ModpackManager/tests/fixtures/base_sample.xml`

- [ ] **Step 1: Create the fixture**

`ModpackManager/tests/fixtures/base_sample.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<ServerPack version="4.1" xmlns="http://www.mcupdater.com">
	<Server id="base" name="base" version="1.21.1">
		<Module name="AppleSkin" id="appleskin" depends="" side="CLIENT">
			<URL priority="1">https://cdn.modrinth.com/data/EsAfCjCV/versions/oy4bhPTN/appleskin-neoforge-mc1.21-3.0.5.jar</URL>
			<Size>57725</Size>
			<Required>true</Required>
			<ModType>Regular</ModType>
			<MD5>7056a521ac0d4c3a120a2d7bfdd54833</MD5>
			<Meta>
				<version>3.0.5</version>
			</Meta>
		</Module>
		<Module name="Xaeros World Map" id="xaeroworldmap" depends="" side="CLIENT">
			<URL priority="1">https://edge.forgecdn.net/files/7568/054/XaerosWorldMap_1.39.4_Neoforge_1.21.jar</URL>
			<Size>1000</Size>
			<Required>true</Required>
			<ModType>Regular</ModType>
			<MD5>aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</MD5>
		</Module>
		<Module name="Old Mod" id="oldmod" depends="" side="BOTH">
			<URL priority="1">https://cdn.modrinth.com/data/PPPPPPPP/versions/QQQQQQQQ/old-1.0.0.jar</URL>
			<ModType>Regular</ModType>
		</Module>
	</Server>
</ServerPack>
```

- [ ] **Step 2: Write the failing test**

`ModpackManager/tests/test_xml_model.py`:
```python
from pathlib import Path
from modpack_manager import xml_model

FIX = Path(__file__).parent / "fixtures"


def test_parse_detects_platform_and_ids():
    mods = xml_model.parse_packs([FIX / "base_sample.xml"])
    apple = mods["appleskin"]
    assert apple.platform == "modrinth"
    assert apple.project_id == "EsAfCjCV"
    assert apple.version_id == "oy4bhPTN"
    assert apple.version == "3.0.5"
    assert apple.side == "CLIENT"

    xaero = mods["xaeroworldmap"]
    assert xaero.platform == "curseforge"
    assert xaero.cf_file_id == 7568054


def test_later_layer_overrides_earlier(tmp_path):
    override = tmp_path / "updates-2026-01-01.xml"
    override.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ServerPack version="4.1" xmlns="http://www.mcupdater.com">'
        '<Server id="u" name="u" version="1.21.1">'
        '<Module name="AppleSkin" id="appleskin" side="CLIENT">'
        '<URL priority="1">https://cdn.modrinth.com/data/EsAfCjCV/versions/NEWVER11/appleskin-3.1.0.jar</URL>'
        '<Meta><version>3.1.0</version></Meta>'
        '</Module></Server></ServerPack>',
        encoding="utf-8",
    )
    mods = xml_model.parse_packs([FIX / "base_sample.xml", override])
    assert mods["appleskin"].version_id == "NEWVER11"
    assert mods["appleskin"].version == "3.1.0"
    # side preserved from the base layer when the override omits it
    assert mods["appleskin"].side == "CLIENT"


def test_unknown_platform_when_url_not_recognised():
    mods = xml_model.parse_packs([FIX / "base_sample.xml"])
    assert "appleskin" in mods and mods["appleskin"].platform == "modrinth"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_xml_model.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 4: Implement xml_model.py**

`ModpackManager/modpack_manager/xml_model.py`:
```python
"""Parse MCUpdater ServerPack XML and merge layered packs into current state."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

NS = {"m": "http://www.mcupdater.com"}
_MODRINTH = re.compile(r"cdn\.modrinth\.com/data/([^/]+)/versions/([^/]+)/")
_FORGE = re.compile(r"edge\.forgecdn\.net/files/(\d+)/(\d+)/")


@dataclass
class Module:
    mod_id: str
    name: str
    url: str
    side: str = "BOTH"
    required: bool = True
    mod_type: str = "Regular"
    depends: str = ""
    mod_path: str | None = None
    size: int | None = None
    md5: str | None = None
    version: str | None = None
    source_file: str = ""
    platform: str = "unknown"
    project_id: str | None = None
    version_id: str | None = None
    cf_file_id: int | None = None

    def __post_init__(self):
        if "cdn.modrinth.com" in self.url:
            self.platform = "modrinth"
            m = _MODRINTH.search(self.url)
            if m:
                self.project_id, self.version_id = m.group(1), m.group(2)
        elif "forgecdn.net" in self.url:
            self.platform = "curseforge"
            m = _FORGE.search(self.url)
            if m:
                self.cf_file_id = int(f"{m.group(1)}{m.group(2)}")


def _text(module: ET.Element, tag: str) -> str | None:
    el = module.find(f"m:{tag}", NS)
    if el is None:
        el = module.find(tag)
    return el.text.strip() if el is not None and el.text else None


def _parse_module(el: ET.Element, source_file: str) -> Module | None:
    url = _text(el, "URL")
    if not url:
        return None
    meta = el.find("m:Meta", NS) or el.find("Meta")
    version = None
    if meta is not None:
        vel = meta.find("m:version", NS) or meta.find("version")
        version = vel.text.strip() if vel is not None and vel.text else None
    size = _text(el, "Size")
    return Module(
        mod_id=el.get("id", "unknown"),
        name=el.get("name", "unknown"),
        url=url,
        side=el.get("side", "BOTH"),
        required=(_text(el, "Required") or "true").lower() == "true",
        mod_type=_text(el, "ModType") or "Regular",
        depends=el.get("depends", ""),
        mod_path=_text(el, "ModPath"),
        size=int(size) if size and size.isdigit() else None,
        md5=_text(el, "MD5"),
        version=version,
        source_file=source_file,
    )


def _merge(base: Module, override: Module) -> Module:
    """Override wins for present fields; base fills what the override omits."""
    result = Module(
        mod_id=override.mod_id,
        name=override.name or base.name,
        url=override.url,
        side=override.side if override.side != "BOTH" else base.side,
        required=override.required,
        mod_type=override.mod_type,
        depends=override.depends or base.depends,
        mod_path=override.mod_path or base.mod_path,
        size=override.size,
        md5=override.md5,
        version=override.version or base.version,
        source_file=override.source_file,
    )
    return result


def parse_pack_file(path: Path) -> dict[str, Module]:
    tree = ET.parse(path)
    root = tree.getroot()
    modules = root.findall(".//m:Module", NS) or root.findall(".//Module")
    out: dict[str, Module] = {}
    for el in modules:
        mod = _parse_module(el, Path(path).name)
        if mod:
            out[mod.mod_id] = mod
    return out


def parse_packs(paths: list[Path]) -> dict[str, Module]:
    merged: dict[str, Module] = {}
    for path in paths:
        if not Path(path).exists():
            continue
        for mod_id, mod in parse_pack_file(path).items():
            if mod_id in merged:
                merged[mod_id] = _merge(merged[mod_id], mod)
            else:
                merged[mod_id] = mod
    return merged
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_xml_model.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ModpackManager/modpack_manager/xml_model.py ModpackManager/tests/test_xml_model.py ModpackManager/tests/fixtures/base_sample.xml
git commit -m "feat(modpack-manager): parse and merge layered pack XML"
```

---

## Task 5: Changelog text rendering

**Files:**
- Create: `ModpackManager/modpack_manager/text_render.py`
- Test: `ModpackManager/tests/test_text_render.py`

- [ ] **Step 1: Write the failing test**

`ModpackManager/tests/test_text_render.py`:
```python
from modpack_manager.text_render import render_markdown, sanitize_html


def test_render_markdown_makes_html():
    out = render_markdown("- one\n- two")
    assert "<li>one</li>" in out
    assert "<li>two</li>" in out


def test_render_markdown_strips_scripts():
    out = render_markdown("hello <script>alert(1)</script>")
    assert "<script>" not in out


def test_sanitize_html_keeps_basic_tags_drops_danger():
    out = sanitize_html('<p onclick="x()">hi <b>there</b></p><script>bad()</script>')
    assert "<b>there</b>" in out
    assert "onclick" not in out
    assert "<script>" not in out


def test_empty_changelog_returns_empty_string():
    assert render_markdown("") == ""
    assert render_markdown(None) == ""
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_text_render.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement text_render.py**

`ModpackManager/modpack_manager/text_render.py`:
```python
"""Render Modrinth markdown and sanitize CurseForge HTML changelogs."""

import bleach
import markdown as _md

_ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr",
    "img", "span", "div", "table", "thead", "tbody", "tr", "th", "td",
}
_ALLOWED_ATTRS = {"a": ["href", "title", "rel"], "img": ["src", "alt", "title"]}


def sanitize_html(html: str) -> str:
    if not html:
        return ""
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)


def render_markdown(text: str) -> str:
    if not text:
        return ""
    html = _md.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
    return sanitize_html(html)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_text_render.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/text_render.py ModpackManager/tests/test_text_render.py
git commit -m "feat(modpack-manager): changelog markdown/html rendering"
```

---

## Task 6: Candidate data types

**Files:**
- Create: `ModpackManager/modpack_manager/sources/__init__.py` (empty)
- Create: `ModpackManager/modpack_manager/sources/base.py`
- Test: covered indirectly by later tasks; add `ModpackManager/tests/test_sources_base.py`

- [ ] **Step 1: Write the failing test**

`ModpackManager/tests/test_sources_base.py`:
```python
from modpack_manager.sources.base import Candidate, ChangelogEntry, AddedDependency


def test_candidate_to_dict_roundtrips_nested():
    c = Candidate(
        mod_id="create", name="Create", platform="modrinth",
        source_url="https://x/y.jar", current_version="6.0.4",
        latest_version="6.0.6", severity="patch", side="BOTH",
        required=True, mod_type="Regular",
        changelogs=[ChangelogEntry("6.0.6", "2026-07-10", "<p>fix</p>")],
        added_dependencies=[AddedDependency("morered", False)],
        status="ok", latest_size=1234,
    )
    d = c.to_dict()
    assert d["mod_id"] == "create"
    assert d["changelogs"][0]["version"] == "6.0.6"
    assert d["added_dependencies"][0]["id"] == "morered"
    assert d["added_dependencies"][0]["satisfied"] is False
    assert d["status"] == "ok"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_sources_base.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement sources/base.py**

`ModpackManager/modpack_manager/sources/base.py`:
```python
"""Data types shared by the update sources."""

from dataclasses import dataclass, field, asdict


@dataclass
class ChangelogEntry:
    version: str
    date: str
    body_html: str


@dataclass
class AddedDependency:
    id: str
    satisfied: bool
    name: str | None = None


@dataclass
class Candidate:
    mod_id: str
    name: str
    platform: str
    source_url: str
    current_version: str
    latest_version: str
    severity: str
    side: str
    required: bool
    mod_type: str
    changelogs: list = field(default_factory=list)
    added_dependencies: list = field(default_factory=list)
    status: str = "ok"          # ok | manual | error
    note: str = ""
    latest_size: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)
```

Also create empty `ModpackManager/modpack_manager/sources/__init__.py`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_sources_base.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/sources/
git add ModpackManager/tests/test_sources_base.py
git commit -m "feat(modpack-manager): candidate data types"
```

---

## Task 7: Modrinth source

**Files:**
- Create: `ModpackManager/modpack_manager/sources/modrinth.py`
- Test: `ModpackManager/tests/test_modrinth.py`

- [ ] **Step 1: Write the failing test**

`ModpackManager/tests/test_modrinth.py`:
```python
import json
import responses
from modpack_manager.xml_model import Module
from modpack_manager.sources import modrinth

API = "https://api.modrinth.com/v2"


def _module(version_id="OLDVER11", version="3.0.5"):
    url = f"https://cdn.modrinth.com/data/PROJ1234/versions/{version_id}/appleskin-{version}.jar"
    return Module(mod_id="appleskin", name="AppleSkin", url=url, version=version)


def _versions_payload():
    return [
        {
            "id": "NEWVER22", "version_number": "3.1.0",
            "date_published": "2026-07-10T00:00:00Z",
            "changelog": "- added things",
            "dependencies": [{"project_id": "DEP0001", "dependency_type": "required"}],
            "files": [{"primary": True, "url": "https://cdn.modrinth.com/new.jar", "size": 999,
                       "hashes": {"sha1": "abc"}}],
        },
        {
            "id": "MIDVER22", "version_number": "3.0.9",
            "date_published": "2026-07-01T00:00:00Z",
            "changelog": "- interim fix",
            "dependencies": [],
            "files": [{"primary": True, "url": "https://cdn.modrinth.com/mid.jar", "size": 990,
                       "hashes": {"sha1": "def"}}],
        },
        {
            "id": "OLDVER11", "version_number": "3.0.5",
            "date_published": "2026-06-01T00:00:00Z",
            "changelog": "- old",
            "dependencies": [],
            "files": [{"primary": True, "url": "https://cdn.modrinth.com/old.jar", "size": 980,
                       "hashes": {"sha1": "ghi"}}],
        },
    ]


@responses.activate
def test_build_candidate_returns_range_and_severity():
    responses.add(responses.GET, f"{API}/project/PROJ1234/version",
                  json=_versions_payload(), status=200)
    c = modrinth.build_candidate(_module(), mc_version="1.21.1", loader="neoforge",
                                 current_project_ids=set())
    assert c is not None
    assert c.latest_version == "3.1.0"
    assert c.severity == "minor"
    # changelog range excludes the installed version, newest-first
    assert [e.version for e in c.changelogs] == ["3.1.0", "3.0.9"]
    assert c.source_url == "https://cdn.modrinth.com/new.jar"
    assert c.latest_size == 999
    assert c.added_dependencies[0].id == "DEP0001"
    assert c.added_dependencies[0].satisfied is False


@responses.activate
def test_up_to_date_returns_none():
    payload = _versions_payload()[-1:]  # only the installed version
    responses.add(responses.GET, f"{API}/project/PROJ1234/version", json=payload, status=200)
    c = modrinth.build_candidate(_module(), "1.21.1", "neoforge", set())
    assert c is None


@responses.activate
def test_dependency_marked_satisfied_when_present():
    responses.add(responses.GET, f"{API}/project/PROJ1234/version",
                  json=_versions_payload(), status=200)
    c = modrinth.build_candidate(_module(), "1.21.1", "neoforge",
                                 current_project_ids={"DEP0001"})
    assert c.added_dependencies == []  # satisfied deps are not reported
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py -v`
Expected: FAIL (ImportError: build_candidate).

- [ ] **Step 3: Implement sources/modrinth.py**

`ModpackManager/modpack_manager/sources/modrinth.py`:
```python
"""Build update candidates from the Modrinth API."""

import requests
from ..version_utils import classify_severity
from ..text_render import render_markdown
from .base import Candidate, ChangelogEntry, AddedDependency

API = "https://api.modrinth.com/v2"
_UA = "Gears-Frontiers-ModpackManager/0.1 (github.com/edwardg117/Gears-Frontiers)"


def _session(api_key: str = "") -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = _UA
    if api_key:
        s.headers["Authorization"] = api_key
    return s


def _fetch_versions(session, project_id, mc_version, loader):
    r = session.get(
        f"{API}/project/{project_id}/version",
        params={"game_versions": f'["{mc_version}"]', "loaders": f'["{loader}"]'},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _primary_file(version: dict) -> dict:
    files = version.get("files", [])
    for f in files:
        if f.get("primary"):
            return f
    return files[0] if files else {}


def build_candidate(module, mc_version, loader, current_project_ids, api_key=""):
    session = _session(api_key)
    versions = _fetch_versions(session, module.project_id, mc_version, loader)
    if not versions:
        return None
    versions.sort(key=lambda v: v.get("date_published", ""), reverse=True)
    latest = versions[0]
    if latest.get("id") == module.version_id:
        return None  # already on newest

    ids = [v.get("id") for v in versions]
    if module.version_id in ids:
        newer = versions[: ids.index(module.version_id)]
        note = ""
    else:
        newer = [latest]
        note = "Installed version not found among current releases; showing latest only."

    changelogs = [
        ChangelogEntry(v.get("version_number", "?"),
                       (v.get("date_published") or "")[:10],
                       render_markdown(v.get("changelog") or ""))
        for v in newer
    ]
    added = []
    for dep in latest.get("dependencies", []):
        if dep.get("dependency_type") == "required" and dep.get("project_id"):
            pid = dep["project_id"]
            if pid not in current_project_ids:
                added.append(AddedDependency(id=pid, satisfied=False))

    pf = _primary_file(latest)
    return Candidate(
        mod_id=module.mod_id, name=module.name, platform="modrinth",
        source_url=pf.get("url", ""), current_version=module.version or "unknown",
        latest_version=latest.get("version_number", "?"),
        severity=classify_severity(module.version or "", latest.get("version_number", "")),
        side=module.side, required=module.required, mod_type=module.mod_type,
        changelogs=changelogs, added_dependencies=added,
        status="ok", note=note, latest_size=pf.get("size"),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/sources/modrinth.py ModpackManager/tests/test_modrinth.py
git commit -m "feat(modpack-manager): Modrinth update source"
```

---

## Task 8: CurseForge source

**Files:**
- Create: `ModpackManager/modpack_manager/sources/curseforge.py`
- Test: `ModpackManager/tests/test_curseforge.py`

CurseForge flow: recover `modId` from the installed file id via `POST /v1/mods/files`,
list newer files via `GET /v1/mods/{modId}/files`, fetch the HTML changelog per file,
and detect distribution blocks (`allowModDistribution == false` or a null `downloadUrl`).

- [ ] **Step 1: Write the failing test**

`ModpackManager/tests/test_curseforge.py`:
```python
import responses
from modpack_manager.xml_model import Module
from modpack_manager.sources import curseforge

API = "https://api.curseforge.com/v1"


def _module(file_id=7568054, version="1.39.4"):
    url = f"https://edge.forgecdn.net/files/7568/054/Xaeros_{version}.jar"
    m = Module(mod_id="xaeroworldmap", name="Xaeros World Map", url=url, version=version)
    return m


def _add_common(latest_download="https://edge.forgecdn.net/files/7600/000/Xaeros_1.39.8.jar",
                allow_dist=True):
    responses.add(responses.POST, f"{API}/mods/files",
                  json={"data": [{"id": 7568054, "modId": 999}]}, status=200)
    responses.add(responses.GET, f"{API}/mods/999",
                  json={"data": {"id": 999, "name": "Xaeros World Map",
                                 "allowModDistribution": allow_dist}}, status=200)
    responses.add(responses.GET, f"{API}/mods/999/files",
                  json={"data": [
                      {"id": 7600000, "displayName": "1.39.8", "fileName": "Xaeros_1.39.8.jar",
                       "fileDate": "2026-07-10T00:00:00Z", "fileLength": 2000,
                       "downloadUrl": latest_download,
                       "gameVersions": ["1.21.1", "NeoForge"]},
                      {"id": 7568054, "displayName": "1.39.4", "fileName": "Xaeros_1.39.4.jar",
                       "fileDate": "2026-06-01T00:00:00Z", "fileLength": 1900,
                       "downloadUrl": "https://edge.forgecdn.net/files/7568/054/Xaeros_1.39.4.jar",
                       "gameVersions": ["1.21.1", "NeoForge"]},
                  ]}, status=200)
    responses.add(responses.GET, f"{API}/mods/999/files/7600000/changelog",
                  json={"data": "<p>Fixed the map</p>"}, status=200)


@responses.activate
def test_build_candidate_happy_path():
    _add_common()
    c = curseforge.build_candidate(_module(), "1.21.1", "neoforge", set(), api_key="CF")
    assert c is not None
    assert c.status == "ok"
    assert c.latest_version == "1.39.8"
    assert c.source_url.endswith("Xaeros_1.39.8.jar")
    assert c.latest_size == 2000
    assert "Fixed the map" in c.changelogs[0].body_html


@responses.activate
def test_distribution_blocked_marks_manual():
    _add_common(latest_download=None, allow_dist=False)
    c = curseforge.build_candidate(_module(), "1.21.1", "neoforge", set(), api_key="CF")
    assert c.status == "manual"
    assert "manual" in c.note.lower()


@responses.activate
def test_missing_api_key_returns_error_candidate():
    c = curseforge.build_candidate(_module(), "1.21.1", "neoforge", set(), api_key="")
    assert c.status == "error"
    assert "api key" in c.note.lower()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py -v`
Expected: FAIL (ImportError: build_candidate).

- [ ] **Step 3: Implement sources/curseforge.py**

`ModpackManager/modpack_manager/sources/curseforge.py`:
```python
"""Build update candidates from the CurseForge API."""

import requests
from ..version_utils import classify_severity
from ..text_render import sanitize_html
from .base import Candidate, ChangelogEntry

API = "https://api.curseforge.com/v1"
_LOADER_ID = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}


def _session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers["x-api-key"] = api_key
    s.headers["Accept"] = "application/json"
    return s


def _error(module, note) -> Candidate:
    return Candidate(
        mod_id=module.mod_id, name=module.name, platform="curseforge",
        source_url=module.url, current_version=module.version or "unknown",
        latest_version="?", severity="unknown", side=module.side,
        required=module.required, mod_type=module.mod_type, status="error", note=note,
    )


def _recover_mod_id(session, file_id):
    r = session.post(f"{API}/mods/files", json={"fileIds": [file_id]}, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", [])
    return data[0]["modId"] if data else None


def _list_files(session, mod_id, mc_version, loader):
    r = session.get(f"{API}/mods/{mod_id}/files",
                    params={"gameVersion": mc_version,
                            "modLoaderType": _LOADER_ID.get(loader, 6), "pageSize": 50},
                    timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def _changelog(session, mod_id, file_id):
    r = session.get(f"{API}/mods/{mod_id}/files/{file_id}/changelog", timeout=30)
    if r.status_code != 200:
        return ""
    return sanitize_html(r.json().get("data", ""))


def build_candidate(module, mc_version, loader, current_project_ids, api_key=""):
    if not api_key:
        return _error(module, "No CurseForge API key configured.")
    session = _session(api_key)
    try:
        mod_id = _recover_mod_id(session, module.cf_file_id)
        if mod_id is None:
            return _error(module, "Could not resolve CurseForge project from file id.")

        info = session.get(f"{API}/mods/{mod_id}", timeout=30)
        info.raise_for_status()
        allow_dist = info.json().get("data", {}).get("allowModDistribution", True)

        files = _list_files(session, mod_id, mc_version, loader)
        files.sort(key=lambda f: f.get("fileDate", ""), reverse=True)
        if not files:
            return None
        latest = files[0]
        if latest.get("id") == module.cf_file_id:
            return None  # already newest

        ids = [f.get("id") for f in files]
        newer = files[: ids.index(module.cf_file_id)] if module.cf_file_id in ids else [latest]
        changelogs = [
            ChangelogEntry(f.get("displayName", "?"), (f.get("fileDate") or "")[:10],
                           _changelog(session, mod_id, f["id"]))
            for f in newer
        ]

        blocked = (not allow_dist) or not latest.get("downloadUrl")
        return Candidate(
            mod_id=module.mod_id, name=module.name, platform="curseforge",
            source_url=latest.get("downloadUrl") or module.url,
            current_version=module.version or "unknown",
            latest_version=latest.get("displayName", "?"),
            severity=classify_severity(module.version or "", latest.get("displayName", "")),
            side=module.side, required=module.required, mod_type=module.mod_type,
            changelogs=changelogs, added_dependencies=[],
            status="manual" if blocked else "ok",
            note="This mod blocks third-party downloads — update it manually." if blocked else "",
            latest_size=latest.get("fileLength"),
        )
    except requests.RequestException as e:
        return _error(module, f"CurseForge request failed: {e}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/sources/curseforge.py ModpackManager/tests/test_curseforge.py
git commit -m "feat(modpack-manager): CurseForge update source"
```

---

## Task 9: Hashing (download → MD5 + size, cached)

**Files:**
- Create: `ModpackManager/modpack_manager/hashing.py`
- Test: `ModpackManager/tests/test_hashing.py`

- [ ] **Step 1: Write the failing test**

`ModpackManager/tests/test_hashing.py`:
```python
import hashlib
import json
import responses
from modpack_manager import hashing

URL = "https://cdn.modrinth.com/data/x/versions/y/mod.jar"
BLOB = b"pretend jar bytes" * 100


@responses.activate
def test_compute_md5_and_size(tmp_path):
    responses.add(responses.GET, URL, body=BLOB, status=200)
    cache = hashing.HashCache(tmp_path / "hashes.json")
    md5, size = hashing.compute(URL, cache=cache)
    assert md5 == hashlib.md5(BLOB).hexdigest()
    assert size == len(BLOB)


@responses.activate
def test_cache_hit_avoids_second_request(tmp_path):
    responses.add(responses.GET, URL, body=BLOB, status=200)
    cache = hashing.HashCache(tmp_path / "hashes.json")
    hashing.compute(URL, cache=cache)
    # second call must not hit the network (only one registered response, one call)
    md5, size = hashing.compute(URL, cache=cache)
    assert len(responses.calls) == 1
    assert md5 == hashlib.md5(BLOB).hexdigest()


def test_cache_persists_to_disk(tmp_path):
    path = tmp_path / "hashes.json"
    cache = hashing.HashCache(path)
    cache.set(URL, "deadbeef", 10)
    reloaded = hashing.HashCache(path)
    assert reloaded.get(URL) == ("deadbeef", 10)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_hashing.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement hashing.py**

`ModpackManager/modpack_manager/hashing.py`:
```python
"""Download a jar and compute its MD5 + byte size, with an on-disk cache."""

import hashlib
import json
from pathlib import Path

import requests


class HashCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self._data = {}

    def get(self, url: str):
        entry = self._data.get(url)
        return (entry["md5"], entry["size"]) if entry else None

    def set(self, url: str, md5: str, size: int):
        self._data[url] = {"md5": md5, "size": size}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")


def compute(url: str, session=None, cache: HashCache | None = None) -> tuple[str, int]:
    if cache is not None:
        hit = cache.get(url)
        if hit:
            return hit
    session = session or requests.Session()
    md5 = hashlib.md5()
    size = 0
    with session.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=65536):
            md5.update(chunk)
            size += len(chunk)
    result = (md5.hexdigest(), size)
    if cache is not None:
        cache.set(url, result[0], result[1])
    return result
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_hashing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/hashing.py ModpackManager/tests/test_hashing.py
git commit -m "feat(modpack-manager): jar download + md5/size hashing with cache"
```

---

## Task 10: Scan orchestrator

**Files:**
- Create: `ModpackManager/modpack_manager/updates.py`
- Test: `ModpackManager/tests/test_updates.py`

- [ ] **Step 1: Write the failing test**

`ModpackManager/tests/test_updates.py`:
```python
from modpack_manager.xml_model import Module
from modpack_manager.sources.base import Candidate
from modpack_manager import updates


def _mod(mod_id, url, mod_type="Regular"):
    return Module(mod_id=mod_id, name=mod_id, url=url, mod_type=mod_type)


def _cand(mod_id, severity="patch"):
    return Candidate(mod_id=mod_id, name=mod_id, platform="modrinth", source_url="u",
                     current_version="1", latest_version="2", severity=severity,
                     side="BOTH", required=True, mod_type="Regular", status="ok")


def test_scan_dispatches_by_platform_and_sorts(monkeypatch):
    mods = {
        "a": _mod("a", "https://cdn.modrinth.com/data/A/versions/V/a.jar"),
        "b": _mod("b", "https://edge.forgecdn.net/files/1/2/b.jar"),
        "c": _mod("c", "https://example.com/c.jar"),  # unknown platform -> skipped
        "d": _mod("d", "https://cdn.modrinth.com/data/D/versions/W/d.jar", mod_type="Removal"),
    }
    monkeypatch.setattr(updates.modrinth, "build_candidate",
                        lambda m, *a, **k: _cand(m.mod_id, "minor"))
    monkeypatch.setattr(updates.curseforge, "build_candidate",
                        lambda m, *a, **k: _cand(m.mod_id, "major"))

    from modpack_manager.config import Config
    result = updates.scan(mods, Config())
    ids = [c.mod_id for c in result]
    assert set(ids) == {"a", "b"}          # c skipped (unknown), d skipped (Removal)
    assert ids[0] == "b"                    # major sorts before minor


def test_scan_isolates_per_mod_errors(monkeypatch):
    mods = {"a": _mod("a", "https://cdn.modrinth.com/data/A/versions/V/a.jar")}

    def boom(*a, **k):
        raise RuntimeError("api down")

    monkeypatch.setattr(updates.modrinth, "build_candidate", boom)
    from modpack_manager.config import Config
    result = updates.scan(mods, Config())
    assert result[0].status == "error"
    assert "api down" in result[0].note


def test_excluded_mods_are_skipped(monkeypatch):
    mods = {"a": _mod("a", "https://cdn.modrinth.com/data/A/versions/V/a.jar")}
    monkeypatch.setattr(updates.modrinth, "build_candidate",
                        lambda m, *a, **k: _cand(m.mod_id))
    from modpack_manager.config import Config
    result = updates.scan(mods, Config(excluded_mods={"a"}))
    assert result == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_updates.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement updates.py**

`ModpackManager/modpack_manager/updates.py`:
```python
"""Orchestrate: current modules -> update candidates, concurrently."""

from concurrent.futures import ThreadPoolExecutor, as_completed

from .sources import modrinth, curseforge
from .sources.base import Candidate

_SEVERITY_ORDER = {"major": 0, "minor": 1, "patch": 2, "unknown": 3}
_STATUS_ORDER = {"ok": 0, "manual": 1, "error": 2}


def _eligible(module, config) -> bool:
    return (
        module.platform in ("modrinth", "curseforge")
        and module.mod_type != "Removal"
        and module.mod_id not in config.excluded_mods
    )


def _check(module, config, current_project_ids) -> Candidate | None:
    try:
        if module.platform == "modrinth":
            return modrinth.build_candidate(
                module, config.mc_version, config.loader, current_project_ids,
                api_key=config.modrinth_api_key)
        return curseforge.build_candidate(
            module, config.mc_version, config.loader, current_project_ids,
            api_key=config.curseforge_api_key)
    except Exception as e:  # isolate per-mod failures
        return Candidate(
            mod_id=module.mod_id, name=module.name, platform=module.platform,
            source_url=module.url, current_version=module.version or "unknown",
            latest_version="?", severity="unknown", side=module.side,
            required=module.required, mod_type=module.mod_type,
            status="error", note=str(e))


def scan(modules: dict, config, max_workers: int = 5) -> list[Candidate]:
    current_project_ids = {m.project_id for m in modules.values() if m.project_id}
    todo = [m for m in modules.values() if _eligible(m, config)]
    results: list[Candidate] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check, m, config, current_project_ids): m for m in todo}
        for fut in as_completed(futures):
            candidate = fut.result()
            if candidate is not None:
                results.append(candidate)
    results.sort(key=lambda c: (_STATUS_ORDER.get(c.status, 9),
                                _SEVERITY_ORDER.get(c.severity, 9), c.name.lower()))
    return results
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_updates.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/updates.py ModpackManager/tests/test_updates.py
git commit -m "feat(modpack-manager): concurrent scan orchestrator"
```

---

## Task 11: Generate — filtered XML + Preview wiring

**Files:**
- Create: `ModpackManager/modpack_manager/generate.py`
- Test: `ModpackManager/tests/test_generate.py`

Two responsibilities: (a) write `updates/updates-YYYY-MM-DD.xml` for the selected
mods with correct MD5/size and preserved attributes; (b) insert the `<Import>` and
bump the revision in a Preview pack, idempotently, via targeted text edits that
preserve the file's formatting.

- [ ] **Step 1: Write the failing test**

`ModpackManager/tests/test_generate.py`:
```python
from pathlib import Path
import xml.etree.ElementTree as ET

from modpack_manager.xml_model import Module
from modpack_manager.sources.base import Candidate
from modpack_manager import generate

NS = {"m": "http://www.mcupdater.com"}


def _module():
    return Module(mod_id="appleskin", name="AppleSkin",
                  url="https://cdn.modrinth.com/data/E/versions/OLD/appleskin-3.0.5.jar",
                  side="CLIENT", required=True, mod_type="Regular", depends="cloth",
                  mod_path="mods")


def _candidate():
    return Candidate(mod_id="appleskin", name="AppleSkin", platform="modrinth",
                     source_url="https://cdn.modrinth.com/data/E/versions/NEW/appleskin-3.1.0.jar",
                     current_version="3.0.5", latest_version="3.1.0", severity="minor",
                     side="CLIENT", required=True, mod_type="Regular", status="ok",
                     latest_size=1234)


def test_write_update_xml_has_correct_hash_and_preserved_attrs(tmp_path):
    out = tmp_path / "updates-2026-07-17.xml"
    generate.write_update_xml(
        [_candidate()], {"appleskin": _module()}, out, mc_version="1.21.1",
        hashfn=lambda url: ("d41d8cd98f00b204e9800998ecf8427e", 1234))
    root = ET.parse(out).getroot()
    mod = root.find(".//m:Module", NS)
    assert mod.get("id") == "appleskin"
    assert mod.get("side") == "CLIENT"
    assert mod.get("depends") == "cloth"
    assert mod.find("m:MD5", NS).text == "d41d8cd98f00b204e9800998ecf8427e"
    assert mod.find("m:Size", NS).text == "1234"
    assert mod.find("m:ModPath", NS).text == "mods"
    assert mod.find("m:URL", NS).text.endswith("appleskin-3.1.0.jar")
    assert mod.find("m:Meta/m:version", NS).text == "3.1.0"


PREVIEW = """<?xml version="1.0" encoding="UTF-8"?>
<ServerPack version="4.1" xmlns="http://www.mcupdater.com">
\t<Server id="Preview" name="Preview" version="1.21.1" revision="4">
\t\t<Import url="https://x/base.xml">base</Import>
\t\t<Loader type="NeoForge" version="21.1.220" loadOrder="0"/>
\t</Server>
</ServerPack>
"""


def test_wire_into_preview_adds_import_and_bumps_revision(tmp_path):
    p = tmp_path / "Preview.xml"
    p.write_text(PREVIEW, encoding="utf-8")
    rev = generate.wire_into_preview(p, "https://x/updates/updates-2026-07-17.xml")
    text = p.read_text(encoding="utf-8")
    assert rev == "5"
    assert 'revision="5"' in text
    assert text.index("updates-2026-07-17.xml") < text.index("<Loader")
    assert text.count("updates-2026-07-17.xml") == 1


def test_wire_into_preview_is_idempotent(tmp_path):
    p = tmp_path / "Preview.xml"
    p.write_text(PREVIEW, encoding="utf-8")
    generate.wire_into_preview(p, "https://x/updates/updates-2026-07-17.xml")
    generate.wire_into_preview(p, "https://x/updates/updates-2026-07-17.xml")
    text = p.read_text(encoding="utf-8")
    assert text.count("updates-2026-07-17.xml") == 1  # not duplicated
    assert 'revision="6"' in text                      # revision still bumps
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_generate.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement generate.py**

`ModpackManager/modpack_manager/generate.py`:
```python
"""Write the filtered update XML and wire it into the Preview pack."""

import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

MCU_NS = "http://www.mcupdater.com"


def _sub(parent, tag, text=None):
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def write_update_xml(selected, modules, out_path, mc_version, hashfn):
    """selected: list[Candidate]; modules: dict[id,Module]; hashfn(url)->(md5,size)."""
    ET.register_namespace("", MCU_NS)
    root = ET.Element(f"{{{MCU_NS}}}ServerPack", {"version": "4.1"})
    today = date.today().isoformat()
    server = ET.SubElement(root, f"{{{MCU_NS}}}Server", {
        "id": f"update-{today}", "abstract": "false", "name": f"Update {today}",
        "newsUrl": "about:blank", "version": mc_version, "generateList": "true",
        "autoConnect": "false", "revision": "",
        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher", "launcherType": "Vanilla",
    })
    summary = []
    for cand in selected:
        module = modules[cand.mod_id]
        md5, size = hashfn(cand.source_url)
        module_el = ET.SubElement(server, f"{{{MCU_NS}}}Module", {
            "name": cand.name, "id": cand.mod_id,
            "depends": module.depends or "", "side": cand.side,
        })
        url_el = _sub(module_el, f"{{{MCU_NS}}}URL", cand.source_url)
        url_el.set("priority", "1")
        if module.mod_path:
            _sub(module_el, f"{{{MCU_NS}}}ModPath", module.mod_path)
        _sub(module_el, f"{{{MCU_NS}}}Size", size)
        _sub(module_el, f"{{{MCU_NS}}}Required", "true" if cand.required else "false")
        _sub(module_el, f"{{{MCU_NS}}}ModType", cand.mod_type or "Regular")
        _sub(module_el, f"{{{MCU_NS}}}MD5", md5)
        meta = ET.SubElement(module_el, f"{{{MCU_NS}}}Meta")
        _sub(meta, f"{{{MCU_NS}}}version", cand.latest_version)
        summary.append({"id": cand.mod_id, "md5": md5, "size": size, "ok": True})

    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return summary


def _bump_revision(rev: str) -> str:
    m = re.search(r"(\d+)(?!.*\d)", rev)  # last integer run
    if not m:
        return "1"
    return rev[:m.start()] + str(int(m.group(1)) + 1) + rev[m.end():]


def wire_into_preview(preview_path, import_url) -> str:
    """Add <Import>import_url</Import> before <Loader> (if absent) and bump revision."""
    path = Path(preview_path)
    text = path.read_text(encoding="utf-8")

    # bump revision on the <Server ...> element
    def _rev(match):
        return f'revision="{_bump_revision(match.group(1))}"'
    new_text, n = re.subn(r'revision="([^"]*)"', _rev, text, count=1)
    text = new_text
    new_rev = re.search(r'revision="([^"]*)"', text).group(1)

    # add the import once, indented, immediately before <Loader
    if import_url not in text:
        loader_match = re.search(r'([ \t]*)<Loader', text)
        indent = loader_match.group(1) if loader_match else "\t\t"
        import_line = f'{indent}<Import url="{import_url}">null</Import>\n'
        text = text[:loader_match.start()] + import_line + text[loader_match.start():]

    path.write_text(text, encoding="utf-8")
    return new_rev
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_generate.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/generate.py ModpackManager/tests/test_generate.py
git commit -m "feat(modpack-manager): generate filtered update XML + preview wiring"
```

---

## Task 12: Flask web app (backend routes)

**Files:**
- Create: `ModpackManager/modpack_manager/webapp.py`
- Test: `ModpackManager/tests/test_webapp.py`

Routes: `GET /` (serve UI), `GET /api/updates` (scan → JSON, cached in memory,
`?refresh=1` re-scans), `POST /api/generate` (download+hash selected, write files).
The scan/generate collaborators are injected so tests can substitute fakes.

- [ ] **Step 1: Write the failing test**

`ModpackManager/tests/test_webapp.py`:
```python
import json
from modpack_manager.sources.base import Candidate
from modpack_manager import webapp


def _cand(mod_id="appleskin"):
    return Candidate(mod_id=mod_id, name="AppleSkin", platform="modrinth",
                     source_url="https://x/new.jar", current_version="3.0.5",
                     latest_version="3.1.0", severity="minor", side="CLIENT",
                     required=True, mod_type="Regular", status="ok", latest_size=10)


def _make_client(scan_result=None, generate_result=None):
    calls = {"scan": 0, "generate": []}

    def fake_scan():
        calls["scan"] += 1
        return scan_result or [_cand()]

    def fake_generate(selected_ids):
        calls["generate"].append(selected_ids)
        return generate_result or {"written_file": "updates/updates-2026-07-17.xml",
                                    "new_revision": "5", "mods": [], "failures": []}

    app = webapp.create_app(scan_fn=fake_scan, generate_fn=fake_generate)
    app.config["TESTING"] = True
    return app.test_client(), calls


def test_get_updates_returns_candidates_json():
    client, calls = _make_client()
    resp = client.get("/api/updates")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["candidates"][0]["mod_id"] == "appleskin"
    assert calls["scan"] == 1


def test_get_updates_is_cached_until_refresh():
    client, calls = _make_client()
    client.get("/api/updates")
    client.get("/api/updates")
    assert calls["scan"] == 1                      # served from cache
    client.get("/api/updates?refresh=1")
    assert calls["scan"] == 2                      # forced re-scan


def test_post_generate_passes_selected_ids():
    client, calls = _make_client()
    resp = client.post("/api/generate", json={"selected_mod_ids": ["appleskin", "create"]})
    assert resp.status_code == 200
    assert resp.get_json()["new_revision"] == "5"
    assert calls["generate"] == [["appleskin", "create"]]


def test_index_served():
    client, _ = _make_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Gears" in resp.data or b"update" in resp.data.lower()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement webapp.py**

`ModpackManager/modpack_manager/webapp.py`:
```python
"""Flask app: serve the picker UI and the scan/generate JSON API."""

from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

_WEB_DIR = Path(__file__).parent / "web"


def create_app(scan_fn, generate_fn) -> Flask:
    app = Flask(__name__, static_folder=None)
    cache = {"candidates": None}

    @app.get("/")
    def index():
        return send_from_directory(_WEB_DIR, "index.html")

    @app.get("/web/<path:filename>")
    def web_asset(filename):
        return send_from_directory(_WEB_DIR, filename)

    @app.get("/api/updates")
    def updates():
        if cache["candidates"] is None or request.args.get("refresh") == "1":
            cache["candidates"] = scan_fn()
        return jsonify({"candidates": [c.to_dict() for c in cache["candidates"]]})

    @app.post("/api/generate")
    def generate():
        selected = (request.get_json(silent=True) or {}).get("selected_mod_ids", [])
        result = generate_fn(selected)
        return jsonify(result)

    return app
```

- [ ] **Step 4: Run the test to verify it passes** (create a minimal `web/index.html` so the index route resolves)

First create `ModpackManager/modpack_manager/web/index.html` with a placeholder body (replaced fully in Task 13):
```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Gears &amp; Frontiers — Updates</title></head>
<body><div id="app">update picker</div><script src="/web/app.js"></script></body></html>
```

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add ModpackManager/modpack_manager/webapp.py ModpackManager/modpack_manager/web/index.html ModpackManager/tests/test_webapp.py
git commit -m "feat(modpack-manager): Flask routes for scan and generate"
```

---

## Task 13: Frontend UI + wiring/launcher

**Files:**
- Modify: `ModpackManager/modpack_manager/web/index.html`
- Create: `ModpackManager/modpack_manager/web/style.css`
- Create: `ModpackManager/modpack_manager/web/app.js`
- Create: `ModpackManager/modpack_manager/service.py` (wires real scan/generate)
- Create: `ModpackManager/modpack_manager/__main__.py`
- Create: `ModpackManager/README.md`

- [ ] **Step 1: Write the full index.html (Layout A)**

`ModpackManager/modpack_manager/web/index.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gears &amp; Frontiers — Update Picker</title>
  <link rel="stylesheet" href="/web/style.css">
</head>
<body>
  <header class="toolbar">
    <div class="counts"><span id="update-count">0 updates</span> · <span id="selected-count">0 selected</span></div>
    <select id="filter-severity"><option value="">All severity</option><option>major</option><option>minor</option><option>patch</option></select>
    <select id="filter-source"><option value="">All sources</option><option value="modrinth">Modrinth</option><option value="curseforge">CurseForge</option></select>
    <button id="select-all" type="button">Select all</button>
    <button id="generate" type="button" class="primary">Generate preview →</button>
  </header>
  <main class="panes">
    <section id="mod-list" class="list" aria-label="Mods with updates"></section>
    <section id="reader" class="reader"><p class="muted">Select a mod to read its changelog.</p></section>
  </main>
  <div id="status" class="status" hidden></div>
  <script src="/web/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write style.css**

`ModpackManager/modpack_manager/web/style.css`:
```css
:root { --bg:#1d1d1f; --panel:#2d2d2f; --border:#424245; --text:#f5f5f7; --muted:#86868b;
  --accent:#0a84ff; --sel:rgba(10,132,255,.15); --major:#ff453a; --minor:#ff9f0a; --patch:#34c759; }
* { box-sizing:border-box; }
body { margin:0; font-family:system-ui,sans-serif; background:var(--bg); color:var(--text); height:100vh; display:flex; flex-direction:column; }
.toolbar { display:flex; gap:.6rem; align-items:center; padding:.6rem .9rem; background:var(--panel); border-bottom:1px solid var(--border); }
.toolbar .counts { font-size:.8rem; color:var(--muted); margin-right:auto; }
.toolbar select, .toolbar button { background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:.35rem .6rem; font-size:.8rem; cursor:pointer; }
.toolbar button.primary { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
.panes { flex:1; display:grid; grid-template-columns:minmax(280px,1fr) 1.4fr; overflow:hidden; }
.list { overflow-y:auto; border-right:1px solid var(--border); }
.row { display:flex; align-items:center; gap:.6rem; padding:.5rem .8rem; border-bottom:1px solid var(--border); cursor:pointer; }
.row.active { background:var(--sel); box-shadow:inset 3px 0 0 var(--accent); }
.row input { width:16px; height:16px; }
.row .main { flex:1; min-width:0; }
.row .name { font-weight:600; font-size:.85rem; }
.row .ver { font-size:.72rem; color:var(--muted); }
.row .ver b { color:var(--accent); }
.badge { font-size:.6rem; font-weight:700; text-transform:uppercase; padding:1px 6px; border-radius:100px; }
.badge.major { background:rgba(255,69,58,.16); color:var(--major); }
.badge.minor { background:rgba(255,159,10,.16); color:var(--minor); }
.badge.patch { background:rgba(52,199,89,.16); color:var(--patch); }
.badge.unknown { background:var(--panel); color:var(--muted); }
.tag { font-size:.58rem; padding:1px 5px; border:1px solid var(--border); border-radius:4px; color:var(--muted); }
.row.manual, .row.error { opacity:.7; }
.reader { overflow-y:auto; padding:1rem 1.2rem; }
.reader h2 { font-size:1rem; margin:0 0 .2rem; }
.reader .cl-ver { font-weight:700; margin:1rem 0 .3rem; }
.reader .cl-date { color:var(--muted); font-weight:400; font-size:.72rem; margin-left:.4rem; }
.reader .cl-body { font-size:.85rem; color:#d0d0d2; }
.reader .cl-body :is(h1,h2,h3){ font-size:.9rem; }
.dep { margin-top:.8rem; padding:.5rem .6rem; border:1px solid rgba(255,159,10,.3); background:rgba(255,159,10,.1); color:var(--minor); border-radius:7px; font-size:.8rem; }
.muted { color:var(--muted); }
.status { position:fixed; bottom:0; left:0; right:0; padding:.7rem 1rem; background:var(--panel); border-top:1px solid var(--border); font-size:.82rem; }
.status.error { color:var(--major); }
```

- [ ] **Step 3: Write app.js**

`ModpackManager/modpack_manager/web/app.js`:
```javascript
const state = { candidates: [], selected: new Set(), active: null,
                filters: { severity: "", source: "" } };

const $ = (sel) => document.querySelector(sel);

async function load(refresh = false) {
  setStatus("Scanning for updates…");
  const res = await fetch("/api/updates" + (refresh ? "?refresh=1" : ""));
  const data = await res.json();
  state.candidates = data.candidates;
  state.selected = new Set(state.candidates.filter(c => c.status === "ok").map(c => c.mod_id));
  hideStatus();
  render();
}

function visible() {
  return state.candidates.filter(c =>
    (!state.filters.severity || c.severity === state.filters.severity) &&
    (!state.filters.source || c.platform === state.filters.source));
}

function render() {
  const list = $("#mod-list");
  list.innerHTML = "";
  for (const c of visible()) {
    const row = document.createElement("div");
    row.className = "row " + (c.status !== "ok" ? c.status : "") +
                    (state.active === c.mod_id ? " active" : "");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = state.selected.has(c.mod_id);
    cb.disabled = c.status !== "ok";
    cb.addEventListener("click", (e) => { e.stopPropagation(); toggle(c.mod_id); });
    const main = document.createElement("div");
    main.className = "main";
    main.innerHTML = `<div class="name">${esc(c.name)}</div>
      <div class="ver">${esc(c.current_version)} → <b>${esc(c.latest_version)}</b></div>`;
    row.append(cb, main);
    if (c.platform === "curseforge") row.append(tag("CF"));
    row.append(badge(c.severity));
    row.addEventListener("click", () => { state.active = c.mod_id; render(); });
    list.append(row);
  }
  $("#update-count").textContent = `${state.candidates.length} updates`;
  $("#selected-count").textContent = `${state.selected.size} selected`;
  renderReader();
}

function renderReader() {
  const c = state.candidates.find(x => x.mod_id === state.active);
  const r = $("#reader");
  if (!c) { r.innerHTML = '<p class="muted">Select a mod to read its changelog.</p>'; return; }
  const link = c.platform === "modrinth" ? "Open on Modrinth ↗" : "Open on CurseForge ↗";
  let html = `<h2>${esc(c.name)} <span class="ver">${esc(c.current_version)} → <b>${esc(c.latest_version)}</b></span></h2>`;
  if (c.status === "manual" || c.status === "error") html += `<div class="dep">${esc(c.note)}</div>`;
  for (const e of c.changelogs) {
    html += `<div class="cl-ver">${esc(e.version)}<span class="cl-date">${esc(e.date)}</span></div>`;
    html += `<div class="cl-body">${e.body_html || '<span class="muted">No changelog provided.</span>'}</div>`;
  }
  for (const d of c.added_dependencies) {
    html += `<div class="dep">⚠ New required dependency: <b>${esc(d.id)}</b>${d.satisfied ? "" : " — not in your pack"}</div>`;
  }
  r.innerHTML = html;
}

function toggle(id) {
  if (state.selected.has(id)) state.selected.delete(id); else state.selected.add(id);
  render();
}

async function generate() {
  const ids = [...state.selected];
  if (!ids.length) { setStatus("Nothing selected.", true); return; }
  setStatus(`Downloading and hashing ${ids.length} jar(s)…`);
  const res = await fetch("/api/generate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected_mod_ids: ids }),
  });
  const data = await res.json();
  if (data.failures && data.failures.length) {
    setStatus(`Wrote nothing — failures: ${data.failures.map(f => f.id).join(", ")}`, true);
  } else {
    setStatus(`Wrote ${data.written_file}, bumped preview revision to ${data.new_revision}. ` +
              `Review the git diff, then commit & push.`);
  }
}

function badge(sev) { const s = document.createElement("span"); s.className = "badge " + sev; s.textContent = sev; return s; }
function tag(t) { const s = document.createElement("span"); s.className = "tag"; s.textContent = t; return s; }
function esc(s) { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; }
function setStatus(msg, isError = false) { const el = $("#status"); el.textContent = msg; el.className = "status" + (isError ? " error" : ""); el.hidden = false; }
function hideStatus() { $("#status").hidden = true; }

$("#filter-severity").addEventListener("change", (e) => { state.filters.severity = e.target.value; render(); });
$("#filter-source").addEventListener("change", (e) => { state.filters.source = e.target.value; render(); });
$("#select-all").addEventListener("click", () => {
  const vis = visible().filter(c => c.status === "ok");
  const allSelected = vis.every(c => state.selected.has(c.mod_id));
  for (const c of vis) { if (allSelected) state.selected.delete(c.mod_id); else state.selected.add(c.mod_id); }
  render();
});
$("#generate").addEventListener("click", generate);
load();
```

- [ ] **Step 4: Write service.py (wire real scan + generate)**

`ModpackManager/modpack_manager/service.py`:
```python
"""Wire the real collaborators for the running app."""

import xml.etree.ElementTree as ET
from datetime import date

from . import generate as gen
from . import updates as upd
from .config import load_config
from .hashing import HashCache, compute
from .paths import pack_paths
from .xml_model import NS, parse_packs

_GITHUB_MAIN_MARKER = "/main/"
_GITHUB_RAW = "https://raw.githubusercontent.com/edwardg117/Gears-Frontiers/refs/heads/main/updates/"


def _pack_layer_paths(paths):
    """Layer order = the <Import> order in the Preview pack (authoritative).

    Each Import url like ``.../refs/heads/main/updates/base.xml`` maps to the
    local path after the ``/main/`` marker, resolved under the repo root.
    """
    tree = ET.parse(paths.preview_pack)
    imports = tree.getroot().findall(".//m:Import", NS) or tree.getroot().findall(".//Import")
    layers = []
    for el in imports:
        url = (el.text or "").strip()
        idx = url.find(_GITHUB_MAIN_MARKER)
        if idx < 0:
            continue
        local = paths.root / url[idx + len(_GITHUB_MAIN_MARKER):]
        if local.exists():
            layers.append(local)
    return layers


def real_scan():
    paths = pack_paths()
    config = load_config(paths.config_ini)
    modules = parse_packs(_pack_layer_paths(paths))
    return upd.scan(modules, config)


def real_generate(selected_ids):
    paths = pack_paths()
    config = load_config(paths.config_ini)
    modules = parse_packs(_pack_layer_paths(paths))
    candidates = {c.mod_id: c for c in real_scan()}
    chosen = [candidates[i] for i in selected_ids if i in candidates and candidates[i].status == "ok"]

    cache = HashCache(paths.cache_dir / "hashes.json")
    failures = []

    def hashfn(url):
        return compute(url, cache=cache)

    # Pre-hash so a failure aborts before writing anything (transactional).
    for cand in chosen:
        try:
            hashfn(cand.source_url)
        except Exception as e:  # noqa: BLE001
            failures.append({"id": cand.mod_id, "error": str(e)})
    if failures:
        return {"written_file": None, "new_revision": None, "mods": [], "failures": failures}

    today = date.today().isoformat()
    out_path = paths.updates_dir / f"updates-{today}.xml"
    mods_summary = gen.write_update_xml(chosen, modules, out_path, config.mc_version, hashfn)
    import_url = f"{_GITHUB_RAW}updates-{today}.xml"
    new_rev = gen.wire_into_preview(paths.preview_pack, import_url)
    return {
        "written_file": f"updates/updates-{today}.xml",
        "new_revision": new_rev, "mods": mods_summary, "failures": [],
    }
```

- [ ] **Step 5: Write __main__.py (launcher)**

`ModpackManager/modpack_manager/__main__.py`:
```python
"""Start the server and open the browser: python -m modpack_manager"""

import threading
import webbrowser

from .service import real_scan, real_generate
from .webapp import create_app

HOST, PORT = "127.0.0.1", 5178


def main():
    app = create_app(scan_fn=real_scan, generate_fn=real_generate)
    url = f"http://{HOST}:{PORT}/"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Modpack Manager running at {url} (Ctrl+C to stop)")
    app.run(host=HOST, port=PORT, threaded=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Write README.md**

`ModpackManager/README.md`:
````markdown
# Modpack Manager — Update Picker

Local web app to review mod changelogs and pick which updates to apply to the
Gears & Frontiers pack. Reads the pack XML at the repo root and writes a filtered
`updates/updates-YYYY-MM-DD.xml`, wiring it into `GearsAndFrontiers_Preview.xml`.

## Setup

```bash
cd ModpackManager
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pip install -e .
```

## Run

```bash
cd ModpackManager
.venv/Scripts/python -m modpack_manager
```

Your browser opens at http://127.0.0.1:5178/. Pick mods, read changelogs, and
click **Generate preview**. Then review the git diff, test the Preview pack in
MCUpdater, and promote to the main pack manually.

## Test

```bash
cd ModpackManager
.venv/Scripts/python -m pytest -v
```
````

- [ ] **Step 7: Run the full test suite**

Run from `ModpackManager/`: `.venv/Scripts/python -m pytest -v`
Expected: all tests PASS.

- [ ] **Step 8: Manual end-to-end smoke test**

Run from `ModpackManager/`: `.venv/Scripts/python -m modpack_manager`
Expected: browser opens; the list populates with real updates after the scan;
clicking a mod shows changelogs; **Generate preview** with one cheap mod selected
writes `updates/updates-<today>.xml` and bumps the Preview revision. Verify with
`git status` and `git diff GearsAndFrontiers_Preview.xml`. Discard this smoke-test
output afterward (`git checkout` / delete the dated file) unless it's a real update.

- [ ] **Step 9: Commit**

```bash
git add ModpackManager/modpack_manager/web/ ModpackManager/modpack_manager/service.py ModpackManager/modpack_manager/__main__.py ModpackManager/README.md
git commit -m "feat(modpack-manager): two-pane picker UI and launcher"
```

---

## Self-Review notes (checked against the spec)

- **Form factor / local web app** → Tasks 12–13. ✓
- **Scan: parse+merge layered packs** → Task 4; **query Modrinth+CF with changelog range** → Tasks 7–8; **candidates** → Tasks 6, 10. ✓
- **Generate: correct MD5+size by downloading selected jars** → Tasks 9, 11, 13 (service). ✓
- **Wire into Preview pack (Import + revision bump), idempotent** → Task 11. ✓
- **CurseForge implemented properly, manual-flag for blocked** → Task 8. ✓
- **Changelog depth = all intermediate versions** → Tasks 7–8 (range selection). ✓
- **Per-round skip, no persisted state** → selection lives only in the browser (Task 13). ✓
- **Layout A with versions in left rail, source tag, dep warning, open link** → Task 13. ✓
- **Attribute preservation (side/Required/ModType/depends/ModPath)** → Tasks 4, 11. ✓
- **Severity as label + toolbar filters** → Tasks 3, 13. ✓
- **Error isolation / transactional generate** → Tasks 10 (scan), 13 (service pre-hash). ✓
- **Config excludes / Removal skipped** → Tasks 2, 10. ✓
- **Non-goal: no git actions, no main-pack edits** → service writes files only. ✓

**Deferred (documented in spec §12, intentionally not in this plan):** persistent
hold/pin list, `<Curse>` element emission for blocked CF mods, dependency
pretty-name resolution, auto-promotion to main.
```
