# Modpack Pack Manager (Add & Remove) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the update picker into a pack manager — add tabs to add new mods (paste or search, both platforms, with platform + release-type filters and open-page links) and remove existing mods, all funnelling into one bundled `updates-DATE.xml`.

**Architecture:** New source functions (`search`/`resolve`/`project_versions`) for Modrinth and CurseForge; `generate` refactored to write a batch of update/add/removal module entries; `service` gains real collaborators for the new endpoints and an op-aware `real_generate`; `webapp` exposes `/api/pack`, `/api/search`, `/api/resolve`, `/api/project-versions` and an extended `/api/generate`; the frontend becomes a three-tab UI with a shared batch + review panel.

**Tech Stack:** Python 3.12, Flask, requests; pytest + responses; vanilla HTML/CSS/JS.

**Reference spec:** `docs/superpowers/specs/2026-07-18-modpack-pack-manager-design.md`

**Conventions:** run from `ModpackManager/` with the venv (`.venv/Scripts/python`). Tests mock all HTTP with `responses`. Commits are deferred to the user (YubiKey-signed) — end each task at the "run tests, green" step; skip the commit steps.

---

## File Structure

```
modpack_manager/
  sources/base.py        MODIFY  + SearchHit dataclass
  sources/modrinth.py    MODIFY  + search, resolve, project_versions
  sources/curseforge.py  MODIFY  + search, resolve, project_versions
  generate.py            MODIFY  write_update_xml -> write_batch_xml (update/add/removal)
  service.py             MODIFY  + real_pack/search/resolve/project_versions; op-aware real_generate
  webapp.py              MODIFY  + 4 routes; extended generate route; wider create_app()
  __main__.py            MODIFY  pass the new collaborators
  web/index.html         MODIFY  three-tab layout
  web/app.js             MODIFY  tabs, add/remove, batch + review
  web/style.css          MODIFY  tab/add/remove/review styles
tests/
  test_sources_base.py   MODIFY  SearchHit
  test_modrinth.py       MODIFY  search/resolve/project_versions
  test_curseforge.py     MODIFY  search/resolve/project_versions
  test_generate.py       MODIFY  write_batch_xml (mixed batch)
  test_webapp.py         MODIFY  new routes + extended generate
```

---

## Task 1: SearchHit type

**Files:**
- Modify: `modpack_manager/sources/base.py`
- Test: `tests/test_sources_base.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_sources_base.py`:

```python
def test_search_hit_to_dict():
    from modpack_manager.sources.base import SearchHit
    h = SearchHit(platform="modrinth", id="AAB", slug="sodium", name="Sodium",
                  summary="fast", icon_url="i.png", page_url="https://modrinth.com/mod/sodium")
    d = h.to_dict()
    assert d["platform"] == "modrinth"
    assert d["slug"] == "sodium"
    assert d["page_url"].endswith("/sodium")
```

- [ ] **Step 2: Run it — expect FAIL** (`ImportError: SearchHit`)

Run: `.venv/Scripts/python -m pytest tests/test_sources_base.py::test_search_hit_to_dict -v`

- [ ] **Step 3: Implement** — append to `modpack_manager/sources/base.py`:

```python
@dataclass
class SearchHit:
    platform: str
    id: str
    slug: str
    name: str
    summary: str
    icon_url: str
    page_url: str

    def to_dict(self) -> dict:
        return asdict(self)
```

- [ ] **Step 4: Run it — expect PASS**

Run: `.venv/Scripts/python -m pytest tests/test_sources_base.py -v`

---

## Task 2: Modrinth search

**Files:**
- Modify: `modpack_manager/sources/modrinth.py`
- Test: `tests/test_modrinth.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_modrinth.py`:

```python
@responses.activate
def test_search_returns_hits():
    responses.add(responses.GET, f"{API}/search", json={"hits": [
        {"project_id": "AAB", "slug": "sodium", "title": "Sodium",
         "description": "fast", "icon_url": "https://i/s.png"},
    ]}, status=200)
    hits = modrinth.search("sodium", "1.21.1", "neoforge")
    assert len(hits) == 1
    assert hits[0].platform == "modrinth"
    assert hits[0].id == "AAB"
    assert hits[0].name == "Sodium"
    assert hits[0].page_url == "https://modrinth.com/mod/sodium"
```

- [ ] **Step 2: Run it — expect FAIL** (`AttributeError: search`)

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py::test_search_returns_hits -v`

- [ ] **Step 3: Implement** — add to `modpack_manager/sources/modrinth.py` (import `SearchHit` in the existing `from .base import ...` line, and add the function):

```python
from .base import Candidate, ChangelogEntry, AddedDependency, SearchHit
```

```python
def search(query, mc_version, loader, api_key=""):
    session = _session(api_key)
    facets = f'[["project_type:mod"],["categories:{loader}"],["versions:{mc_version}"]]'
    r = session.get(f"{API}/search",
                    params={"query": query, "facets": facets, "limit": 20}, timeout=30)
    r.raise_for_status()
    hits = []
    for h in r.json().get("hits", []):
        slug = h.get("slug", "")
        hits.append(SearchHit(
            platform="modrinth", id=h.get("project_id", ""), slug=slug,
            name=h.get("title", ""), summary=h.get("description", "") or "",
            icon_url=h.get("icon_url", "") or "",
            page_url=f"https://modrinth.com/mod/{slug}"))
    return hits
```

- [ ] **Step 4: Run it — expect PASS**

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py -v`

---

## Task 3: Modrinth resolve + project_versions

**Files:**
- Modify: `modpack_manager/sources/modrinth.py`
- Test: `tests/test_modrinth.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_modrinth.py`:

```python
@responses.activate
def test_resolve_link_to_project():
    responses.add(responses.GET, f"{API}/project/sodium", json={
        "id": "AAB", "slug": "sodium", "title": "Sodium", "description": "fast",
        "icon_url": "i.png"}, status=200)
    hit = modrinth.resolve("https://modrinth.com/mod/sodium")
    assert hit.id == "AAB"
    assert hit.name == "Sodium"


@responses.activate
def test_project_versions_side_and_types():
    responses.add(responses.GET, f"{API}/project/AAB", json={
        "id": "AAB", "slug": "sodium", "title": "Sodium",
        "client_side": "required", "server_side": "unsupported"}, status=200)
    responses.add(responses.GET, f"{API}/project/AAB/version", json=[
        {"id": "V2", "version_number": "0.6.0", "version_type": "beta",
         "date_published": "2026-07-10T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/0.6.0.jar"}]},
        {"id": "V1", "version_number": "0.5.8", "version_type": "release",
         "date_published": "2026-06-01T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/0.5.8.jar"}]},
    ], status=200)
    out = modrinth.project_versions("AAB", "1.21.1", "neoforge")
    assert out["side"] == "CLIENT"
    assert [v["type"] for v in out["versions"]] == ["beta", "release"]
    assert out["versions"][0]["url"] == "https://cdn/0.6.0.jar"
    assert out["versions"][1]["ref"] == "V1"
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: resolve`)

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py -k "resolve or project_versions" -v`

- [ ] **Step 3: Implement** — add to `modpack_manager/sources/modrinth.py`:

```python
_LINK = re.compile(r"modrinth\.com/(?:mod|plugin|datapack|project)/([^/?#]+)")


def _project_hit(p):
    slug = p.get("slug", "")
    return SearchHit(platform="modrinth", id=p.get("id", ""), slug=slug,
                     name=p.get("title", ""), summary=p.get("description", "") or "",
                     icon_url=p.get("icon_url", "") or "",
                     page_url=f"https://modrinth.com/mod/{slug}")


def resolve(ref, api_key=""):
    ref = (ref or "").strip()
    m = _LINK.search(ref) or _MODRINTH.search(ref)
    slug = m.group(1) if m else ref
    session = _session(api_key)
    r = session.get(f"{API}/project/{slug}", timeout=30)
    if r.status_code != 200:
        return None
    return _project_hit(r.json())


def _detect_side(project):
    cs = project.get("client_side", "required")
    ss = project.get("server_side", "required")
    if ss == "unsupported" and cs != "unsupported":
        return "CLIENT"
    if cs == "unsupported" and ss != "unsupported":
        return "SERVER"
    return "BOTH"


def project_versions(project_id, mc_version, loader, api_key=""):
    session = _session(api_key)
    pr = session.get(f"{API}/project/{project_id}", timeout=30)
    pr.raise_for_status()
    side = _detect_side(pr.json())
    versions = _fetch_versions(session, project_id, mc_version, loader)
    versions.sort(key=lambda v: v.get("date_published", ""), reverse=True)
    opts = [{"ref": v.get("id"), "name": v.get("version_number", "?"),
             "type": v.get("version_type", "release"),
             "url": _primary_file(v).get("url", "")} for v in versions]
    return {"side": side, "versions": opts}
```

Note: `re` and `_MODRINTH` are already imported/defined in this module.

- [ ] **Step 4: Run — expect PASS**

Run: `.venv/Scripts/python -m pytest tests/test_modrinth.py -v`

---

## Task 4: CurseForge search

**Files:**
- Modify: `modpack_manager/sources/curseforge.py`
- Test: `tests/test_curseforge.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_curseforge.py`:

```python
@responses.activate
def test_search_returns_hits():
    responses.add(responses.GET, f"{API}/mods/search", json={"data": [
        {"id": 238222, "slug": "jei", "name": "JEI", "summary": "items",
         "logo": {"url": "https://l/jei.png"}, "links": {"websiteUrl": "https://cf/jei"}},
    ]}, status=200)
    hits = curseforge.search("jei", "1.21.1", "neoforge", api_key="CF")
    assert hits[0].platform == "curseforge"
    assert hits[0].id == "238222"
    assert hits[0].page_url == "https://cf/jei"


def test_search_no_key_returns_empty():
    assert curseforge.search("jei", "1.21.1", "neoforge", api_key="") == []
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: search`)

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py -k search -v`

- [ ] **Step 3: Implement** — in `modpack_manager/sources/curseforge.py` add `SearchHit` to the base import and add the function:

```python
from .base import Candidate, ChangelogEntry, SearchHit
```

```python
def search(query, mc_version, loader, api_key=""):
    if not api_key:
        return []
    session = _session(api_key)
    r = session.get(f"{API}/mods/search", params={
        "gameId": 432, "searchFilter": query, "gameVersion": mc_version,
        "modLoaderType": _LOADER_ID.get(loader, 6), "pageSize": 20}, timeout=30)
    r.raise_for_status()
    hits = []
    for m in r.json().get("data", []):
        hits.append(SearchHit(
            platform="curseforge", id=str(m.get("id", "")), slug=m.get("slug", ""),
            name=m.get("name", ""), summary=m.get("summary", "") or "",
            icon_url=(m.get("logo") or {}).get("url", "") or "",
            page_url=(m.get("links") or {}).get("websiteUrl", "") or ""))
    return hits
```

- [ ] **Step 4: Run — expect PASS**

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py -v`

---

## Task 5: CurseForge resolve + project_versions

**Files:**
- Modify: `modpack_manager/sources/curseforge.py`
- Test: `tests/test_curseforge.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_curseforge.py`:

```python
@responses.activate
def test_resolve_link_via_slug():
    responses.add(responses.GET, f"{API}/mods/search", json={"data": [
        {"id": 238222, "slug": "jei", "name": "JEI", "summary": "items",
         "logo": {"url": "l.png"}, "links": {"websiteUrl": "https://cf/jei"}}]}, status=200)
    hit = curseforge.resolve("https://www.curseforge.com/minecraft/mc-mods/jei", api_key="CF")
    assert hit.id == "238222"
    assert hit.name == "JEI"


@responses.activate
def test_project_versions_maps_release_types_and_skips_blocked():
    responses.add(responses.GET, f"{API}/mods/77/files", json={"data": [
        {"id": 9002, "displayName": "1.2.0", "fileName": "m-1.2.0.jar",
         "fileDate": "2026-07-10T00:00:00Z", "releaseType": 2,
         "downloadUrl": "https://edge/9002/m.jar"},
        {"id": 9001, "displayName": "1.1.0", "fileName": "m-1.1.0.jar",
         "fileDate": "2026-06-01T00:00:00Z", "releaseType": 1, "downloadUrl": None},
    ]}, status=200)
    out = curseforge.project_versions("77", "1.21.1", "neoforge", api_key="CF")
    assert out["side"] == "BOTH"
    assert len(out["versions"]) == 1               # blocked (null url) skipped
    assert out["versions"][0]["type"] == "beta"
    assert out["versions"][0]["ref"] == "9002"
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: resolve`)

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py -k "resolve or project_versions" -v`

- [ ] **Step 3: Implement** — add to `modpack_manager/sources/curseforge.py`:

```python
_LINK = re.compile(r"curseforge\.com/minecraft/mc-mods/([^/?#]+)")
_RELEASE_TYPE = {1: "release", 2: "beta", 3: "alpha"}


def _mod_hit(m):
    return SearchHit(platform="curseforge", id=str(m.get("id", "")), slug=m.get("slug", ""),
                     name=m.get("name", ""), summary=m.get("summary", "") or "",
                     icon_url=(m.get("logo") or {}).get("url", "") or "",
                     page_url=(m.get("links") or {}).get("websiteUrl", "") or "")


def resolve(ref, api_key=""):
    if not api_key:
        return None
    ref = (ref or "").strip()
    session = _session(api_key)
    link = _LINK.search(ref)
    if link:
        r = session.get(f"{API}/mods/search",
                        params={"gameId": 432, "slug": link.group(1), "pageSize": 1}, timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        return _mod_hit(data[0]) if data else None
    if ref.isdigit():
        r = session.get(f"{API}/mods/{ref}", timeout=30)
        if r.status_code != 200:
            return None
        mod = r.json().get("data")
        return _mod_hit(mod) if mod else None
    return None


def project_versions(mod_id, mc_version, loader, api_key=""):
    session = _session(api_key)
    files, _ = _list_files(session, int(mod_id), mc_version, loader)
    files.sort(key=lambda f: f.get("fileDate", ""), reverse=True)
    opts = []
    for f in files:
        url = f.get("downloadUrl")
        if not url:
            continue  # distribution-blocked file can't be added (no jar to hash)
        opts.append({"ref": str(f.get("id")),
                     "name": _clean_version(f.get("displayName"), f.get("fileName"), mc_version),
                     "type": _RELEASE_TYPE.get(f.get("releaseType"), "release"), "url": url})
    return {"side": "BOTH", "versions": opts}
```

Note: `re` is already imported in this module.

- [ ] **Step 4: Run — expect PASS**

Run: `.venv/Scripts/python -m pytest tests/test_curseforge.py -v`

---

## Task 6: Generate — op-aware batch writer

**Files:**
- Modify: `modpack_manager/generate.py`
- Test: `tests/test_generate.py`

Replace `write_update_xml` with `write_batch_xml(entries, out_path, mc_version)`, where
`entries` is a list of dicts already carrying md5/size (hashing happens in the
service). Two kinds: `regular` (update or add) and `removal`.

- [ ] **Step 1: Rewrite the generate test** — replace the body of
`test_write_update_xml_has_correct_hash_and_preserved_attrs` in
`tests/test_generate.py` with a mixed-batch test (keep the two `wire_into_preview`
tests unchanged):

```python
def test_write_batch_xml_regular_and_removal(tmp_path):
    out = tmp_path / "updates-2026-07-18.xml"
    entries = [
        {"kind": "regular", "op": "add", "name": "Sodium", "id": "sodium",
         "side": "CLIENT", "required": True, "mod_type": "Regular", "depends": "",
         "mod_path": None, "url": "https://cdn/sodium-0.5.8.jar",
         "md5": "d41d8cd98f00b204e9800998ecf8427e", "size": 1234, "version": "0.5.8"},
        {"kind": "removal", "name": "Farsight", "id": "farsight", "side": "BOTH"},
    ]
    summary = generate.write_batch_xml(entries, out, mc_version="1.21.1")
    root = ET.parse(out).getroot()
    mods = root.findall(".//m:Module", NS)
    assert {m.get("id") for m in mods} == {"sodium", "farsight"}
    sod = root.find(".//m:Module[@id='sodium']", NS)
    assert sod.get("side") == "CLIENT"
    assert sod.find("m:MD5", NS).text == "d41d8cd98f00b204e9800998ecf8427e"
    assert sod.find("m:Size", NS).text == "1234"
    assert sod.find("m:Meta/m:version", NS).text == "0.5.8"
    far = root.find(".//m:Module[@id='farsight']", NS)
    assert far.find("m:ModType", NS).text == "Removal"
    assert far.find("m:URL", NS) is None                # removal has no URL
    assert [s["id"] for s in summary] == ["sodium", "farsight"]
```

Delete the now-obsolete `_module()`/`_candidate()` helpers and the old test body they served (keep imports and the `PREVIEW`/`wire_into_preview` tests).

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: write_batch_xml`)

Run: `.venv/Scripts/python -m pytest tests/test_generate.py -v`

- [ ] **Step 3: Implement** — in `modpack_manager/generate.py`, replace the whole
`write_update_xml` function with:

```python
def _server_element(root, mc_version):
    today = date.today().isoformat()
    return ET.SubElement(root, f"{{{MCU_NS}}}Server", {
        "id": f"update-{today}", "abstract": "false", "name": f"Update {today}",
        "newsUrl": "about:blank", "version": mc_version, "generateList": "true",
        "autoConnect": "false", "revision": "",
        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher", "launcherType": "Vanilla",
    })


def _write_module(server, e):
    if e["kind"] == "removal":
        el = ET.SubElement(server, f"{{{MCU_NS}}}Module",
                           {"name": e["name"], "id": e["id"], "depends": "", "side": e["side"]})
        _sub(el, f"{{{MCU_NS}}}ModType", "Removal")
        return
    el = ET.SubElement(server, f"{{{MCU_NS}}}Module", {
        "name": e["name"], "id": e["id"], "depends": e.get("depends") or "", "side": e["side"]})
    url_el = _sub(el, f"{{{MCU_NS}}}URL", e["url"])
    url_el.set("priority", "1")
    if e.get("mod_path"):
        _sub(el, f"{{{MCU_NS}}}ModPath", e["mod_path"])
    _sub(el, f"{{{MCU_NS}}}Size", e["size"])
    _sub(el, f"{{{MCU_NS}}}Required", "true" if e["required"] else "false")
    _sub(el, f"{{{MCU_NS}}}ModType", e.get("mod_type") or "Regular")
    _sub(el, f"{{{MCU_NS}}}MD5", e["md5"])
    meta = ET.SubElement(el, f"{{{MCU_NS}}}Meta")
    _sub(meta, f"{{{MCU_NS}}}version", e["version"])


def write_batch_xml(entries, out_path, mc_version):
    """entries: list of {kind:'regular'|'removal', ...}. Regular entries already
    carry md5+size (the service downloads/hashes before calling this)."""
    ET.register_namespace("", MCU_NS)
    root = ET.Element(f"{{{MCU_NS}}}ServerPack", {"version": "4.1"})
    server = _server_element(root, mc_version)
    summary = []
    for e in entries:
        _write_module(server, e)
        if e["kind"] == "removal":
            summary.append({"id": e["id"], "op": "removal"})
        else:
            summary.append({"id": e["id"], "op": e.get("op", "update"),
                            "md5": e["md5"], "size": e["size"]})
    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return summary
```

- [ ] **Step 4: Run — expect PASS**

Run: `.venv/Scripts/python -m pytest tests/test_generate.py -v`

---

## Task 7: Service — new collaborators + op-aware generate

**Files:**
- Modify: `modpack_manager/service.py`

- [ ] **Step 1: Add the read collaborators** — in `modpack_manager/service.py`, update
the imports and add functions:

```python
from . import generate as gen
from . import updates as upd
from .config import load_config
from .hashing import HashCache, compute
from .paths import pack_paths
from .sources import modrinth, curseforge
from .xml_model import NS, parse_packs
```

```python
def real_pack():
    paths = pack_paths()
    modules = parse_packs(_pack_layer_paths(paths))
    out = [{"mod_id": m.mod_id, "name": m.name, "version": m.version or "unknown",
            "platform": m.platform, "side": m.side}
           for m in modules.values()
           if m.mod_type != "Removal" and m.platform in ("modrinth", "curseforge")]
    out.sort(key=lambda x: x["name"].lower())
    return out


def real_search(query, platform="both"):
    paths = pack_paths()
    config = load_config(paths.config_ini)
    hits = []
    if platform in ("both", "modrinth"):
        try:
            hits += modrinth.search(query, config.mc_version, config.loader, config.modrinth_api_key)
        except Exception:  # noqa: BLE001
            pass
    if platform in ("both", "curseforge"):
        try:
            hits += curseforge.search(query, config.mc_version, config.loader, config.curseforge_api_key)
        except Exception:  # noqa: BLE001
            pass
    return hits


def real_resolve(ref):
    paths = pack_paths()
    config = load_config(paths.config_ini)
    ref = (ref or "").strip()
    if "curseforge.com" in ref or ref.isdigit():
        hit = curseforge.resolve(ref, config.curseforge_api_key)
        if hit:
            return hit
    return modrinth.resolve(ref, config.modrinth_api_key)


def real_project_versions(platform, project_id):
    paths = pack_paths()
    config = load_config(paths.config_ini)
    if platform == "curseforge":
        return curseforge.project_versions(project_id, config.mc_version, config.loader,
                                           config.curseforge_api_key)
    return modrinth.project_versions(project_id, config.mc_version, config.loader,
                                     config.modrinth_api_key)
```

- [ ] **Step 2: Replace `real_generate`** — swap the existing `real_generate` for the
op-aware version:

```python
def real_generate(payload, candidates=None):
    """payload: {updates:[mod_id], adds:[AddSpec], removals:[mod_id]}."""
    paths = pack_paths()
    config = load_config(paths.config_ini)
    modules = parse_packs(_pack_layer_paths(paths))
    if candidates is None:
        candidates = real_scan()
    cand_by_id = {c.mod_id: c for c in candidates}
    cache = HashCache(paths.cache_dir / "hashes.json")

    entries, failures = [], []

    def add_regular(op, name, mod_id, side, required, mod_type, depends, mod_path, url, version):
        try:
            md5, size = compute(url, cache=cache)
        except Exception as e:  # noqa: BLE001
            failures.append({"id": mod_id, "error": str(e)})
            return
        entries.append({"kind": "regular", "op": op, "name": name, "id": mod_id,
                        "side": side, "required": required, "mod_type": mod_type,
                        "depends": depends, "mod_path": mod_path, "url": url,
                        "md5": md5, "size": size, "version": version})

    for mid in payload.get("updates", []):
        c = cand_by_id.get(mid)
        if not c or c.status != "ok":
            continue
        m = modules.get(mid)
        add_regular("update", c.name, mid, c.side, c.required, c.mod_type,
                    m.depends if m else "", m.mod_path if m else None,
                    c.source_url, c.latest_version)

    for spec in payload.get("adds", []):
        add_regular("add", spec["name"], spec["module_id"], spec.get("side", "BOTH"),
                    bool(spec.get("required", True)), "Regular", "", None,
                    spec["url"], spec.get("version", ""))

    for mid in payload.get("removals", []):
        m = modules.get(mid)
        if m:
            entries.append({"kind": "removal", "name": m.name, "id": mid, "side": m.side})

    if failures:
        return {"written_file": None, "new_revision": None, "mods": [], "failures": failures}
    if not entries:
        return {"written_file": None, "new_revision": None, "mods": [], "failures": [],
                "note": "Nothing queued — nothing written."}

    today = date.today().isoformat()
    out_path = paths.updates_dir / f"updates-{today}.xml"
    summary = gen.write_batch_xml(entries, out_path, config.mc_version)
    new_rev = gen.wire_into_preview(paths.preview_pack, f"{_GITHUB_RAW}updates-{today}.xml")
    return {"written_file": f"updates/updates-{today}.xml", "new_revision": new_rev,
            "mods": summary, "failures": []}
```

- [ ] **Step 3: Run the suite** (service has no unit tests; confirm nothing else broke)

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS (webapp tests will fail until Task 8 — that's expected; note them).

---

## Task 8: Webapp — new routes + extended generate

**Files:**
- Modify: `modpack_manager/webapp.py`, `modpack_manager/__main__.py`
- Test: `tests/test_webapp.py`

- [ ] **Step 1: Rewrite the webapp tests** — replace `tests/test_webapp.py` with:

```python
from modpack_manager.sources.base import Candidate, SearchHit
from modpack_manager import webapp


def _cand(mod_id="appleskin"):
    return Candidate(mod_id=mod_id, name="AppleSkin", platform="modrinth",
                     source_url="https://x/new.jar", current_version="3.0.5",
                     latest_version="3.1.0", severity="minor", side="CLIENT",
                     required=True, mod_type="Regular", status="ok", latest_size=10)


def _client(calls):
    app = webapp.create_app(
        scan_fn=lambda: (calls.setdefault("scan", 0), calls.update(scan=calls["scan"] + 1),
                         [_cand()])[-1],
        generate_fn=lambda payload, candidates=None: (calls.__setitem__("gen", payload),
                                                      {"written_file": "updates/u.xml",
                                                       "new_revision": "5", "mods": [], "failures": []})[-1],
        pack_fn=lambda: [{"mod_id": "farsight", "name": "Farsight", "version": "1.2",
                          "platform": "modrinth", "side": "BOTH"}],
        search_fn=lambda q, platform: [SearchHit("modrinth", "AAB", "sodium", "Sodium", "", "", "p")],
        resolve_fn=lambda ref: SearchHit("modrinth", "AAB", "sodium", "Sodium", "", "", "p"),
        versions_fn=lambda platform, pid: {"side": "CLIENT",
                                           "versions": [{"ref": "V1", "name": "0.5.8",
                                                         "type": "release", "url": "u"}]})
    app.config["TESTING"] = True
    return app.test_client()


def test_pack_route():
    c = _client({})
    assert c.get("/api/pack").get_json()["mods"][0]["mod_id"] == "farsight"


def test_search_route():
    c = _client({})
    data = c.get("/api/search?q=sodium&platform=both").get_json()
    assert data["hits"][0]["id"] == "AAB"


def test_resolve_route():
    c = _client({})
    assert c.get("/api/resolve?ref=sodium").get_json()["hit"]["slug"] == "sodium"


def test_versions_route():
    c = _client({})
    data = c.get("/api/project-versions?platform=modrinth&id=AAB").get_json()
    assert data["side"] == "CLIENT"
    assert data["versions"][0]["ref"] == "V1"


def test_generate_passes_full_payload():
    calls = {}
    c = _client(calls)
    body = {"updates": ["appleskin"], "adds": [], "removals": ["farsight"]}
    resp = c.post("/api/generate", json=body)
    assert resp.get_json()["new_revision"] == "5"
    assert calls["gen"] == body


def test_index_served():
    c = _client({})
    assert c.get("/").status_code == 200
```

- [ ] **Step 2: Run — expect FAIL** (`create_app` signature mismatch)

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v`

- [ ] **Step 3: Implement** — replace `modpack_manager/webapp.py` with:

```python
"""Flask app: serve the picker UI and the scan/search/generate JSON API."""

from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

_WEB_DIR = Path(__file__).parent / "web"


def create_app(scan_fn, generate_fn, pack_fn, search_fn, resolve_fn, versions_fn) -> Flask:
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

    @app.get("/api/pack")
    def pack():
        return jsonify({"mods": pack_fn()})

    @app.get("/api/search")
    def search():
        hits = search_fn(request.args.get("q", ""), request.args.get("platform", "both"))
        return jsonify({"hits": [h.to_dict() for h in hits]})

    @app.get("/api/resolve")
    def resolve():
        hit = resolve_fn(request.args.get("ref", ""))
        return jsonify({"hit": hit.to_dict() if hit else None})

    @app.get("/api/project-versions")
    def project_versions():
        return jsonify(versions_fn(request.args.get("platform", "modrinth"),
                                   request.args.get("id", "")))

    @app.post("/api/generate")
    def generate():
        payload = request.get_json(silent=True) or {}
        return jsonify(generate_fn(payload, cache["candidates"]))

    return app
```

- [ ] **Step 4: Update `__main__.py`** — replace the `create_app(...)` call:

```python
from .service import (real_scan, real_generate, real_pack, real_search,
                      real_resolve, real_project_versions)
from .webapp import create_app

HOST, PORT = "127.0.0.1", 5178


def main():
    app = create_app(scan_fn=real_scan, generate_fn=real_generate, pack_fn=real_pack,
                     search_fn=real_search, resolve_fn=real_resolve,
                     versions_fn=real_project_versions)
    ...
```

(Leave the rest of `main()` unchanged.)

- [ ] **Step 5: Run — expect PASS**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all PASS.

---

## Task 9: Frontend — three-tab layout (index.html + style.css)

**Files:**
- Modify: `modpack_manager/web/index.html`, `modpack_manager/web/style.css`

- [ ] **Step 1: Replace `web/index.html`** with the tabbed shell:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gears &amp; Frontiers — Pack Manager</title>
  <link rel="stylesheet" href="/web/style.css">
</head>
<body>
  <nav class="tabs">
    <button class="tab active" data-tab="updates" type="button">Updates</button>
    <button class="tab" data-tab="add" type="button">Add</button>
    <button class="tab" data-tab="remove" type="button">Remove</button>
  </nav>

  <section id="tab-updates" class="tab-panel">
    <div class="toolbar">
      <div class="counts"><span id="update-count">0 updates</span> · <span id="selected-count">0 selected</span></div>
      <select id="filter-severity"><option value="">All severity</option><option>major</option><option>minor</option><option>patch</option></select>
      <select id="filter-source"><option value="">All sources</option><option value="modrinth">Modrinth</option><option value="curseforge">CurseForge</option></select>
      <button id="select-all" type="button">Select all</button>
    </div>
    <div class="panes">
      <section id="mod-list" class="list"></section>
      <section id="reader" class="reader"><p class="muted">Select a mod to read its changelog.</p></section>
      <div id="loading" class="loading">
        <div class="spinner"></div>
        <p id="loading-text">Scanning for updates…</p>
        <p class="muted small">Checking Modrinth &amp; CurseForge — this can take ~30&nbsp;seconds.</p>
        <button id="loading-retry" type="button" hidden>Retry</button>
      </div>
    </div>
  </section>

  <section id="tab-add" class="tab-panel" hidden>
    <div class="add-search">
      <input id="add-query" placeholder="Paste a Modrinth or CurseForge link, or search by name">
      <select id="add-platform"><option value="both">Both platforms</option><option value="modrinth">Modrinth</option><option value="curseforge">CurseForge</option></select>
      <select id="add-release"><option value="">All release types</option><option value="release">Stable only</option><option value="beta">Beta</option><option value="alpha">Alpha</option></select>
      <button id="add-search-btn" type="button">Search</button>
    </div>
    <div id="add-results" class="add-results"></div>
    <div class="label">Queued to add (<span id="add-queue-count">0</span>)</div>
    <div id="add-queue" class="add-queue"></div>
  </section>

  <section id="tab-remove" class="tab-panel" hidden>
    <div class="toolbar">
      <input id="remove-filter" placeholder="Filter your pack…" style="flex:1">
      <select id="remove-platform"><option value="">All sources</option><option value="modrinth">Modrinth</option><option value="curseforge">CurseForge</option></select>
    </div>
    <div id="remove-list" class="list"></div>
  </section>

  <footer class="batchbar">
    <button id="review-btn" type="button" class="review">Review batch · <span id="batch-summary">0 updates · 0 adds · 0 removals</span> ›</button>
    <button id="generate" type="button" class="primary">Generate preview →</button>
  </footer>

  <div id="review" class="review-overlay" hidden>
    <div class="review-panel">
      <div class="review-head"><b>Review batch</b><button id="review-close" type="button" aria-label="Close">✕</button></div>
      <div id="review-body"></div>
      <div class="review-foot"><button id="review-generate" type="button" class="primary">Generate preview →</button></div>
    </div>
  </div>
  <div id="status" class="status" hidden></div>
  <script src="/web/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Append the new styles** to `web/style.css`:

```css
.tabs { display:flex; gap:2px; background:var(--panel); border-bottom:1px solid var(--border); padding:0 .5rem; }
.tab { background:transparent; border:none; color:var(--muted); padding:.6rem 1rem; font-size:.85rem; cursor:pointer; border-bottom:2px solid transparent; }
.tab.active { color:var(--text); border-bottom-color:var(--accent); font-weight:600; }
.tab-panel { flex:1; display:flex; flex-direction:column; overflow:hidden; }
.tab-panel[hidden] { display:none; }
.add-search { display:flex; gap:.6rem; padding:.7rem .9rem; }
.add-search #add-query { flex:1; }
.add-search input, .add-search select, .add-search button, .toolbar input { background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:.4rem .6rem; font-size:.82rem; }
.add-results, .add-queue { padding:0 .9rem; display:flex; flex-direction:column; gap:6px; overflow-y:auto; }
.add-row { display:flex; align-items:center; gap:9px; padding:8px 10px; background:var(--panel); border:1px solid var(--border); border-radius:8px; }
.add-row .main { flex:1; min-width:0; }
.add-row .name { font-weight:600; font-size:.85rem; }
.add-row .sum { font-size:.72rem; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.add-row select { max-width:150px; }
.add-row a.open, .add-queue a.open { color:var(--accent); text-decoration:none; padding:2px 5px; }
.add-queue { padding:6px .9rem; }
.batchbar { display:flex; align-items:center; gap:.6rem; padding:.6rem .9rem; background:var(--panel); border-top:1px solid var(--border); }
.batchbar .review { background:transparent; border:none; color:var(--muted); font-size:.82rem; cursor:pointer; margin-right:auto; }
.batchbar .primary, .review-foot .primary { background:var(--accent); color:#fff; border:none; border-radius:6px; padding:.4rem .9rem; font-size:.82rem; font-weight:600; cursor:pointer; }
.review-overlay { position:absolute; inset:0; background:rgba(0,0,0,.5); display:flex; align-items:center; justify-content:center; z-index:10; }
.review-overlay[hidden] { display:none; }
.review-panel { background:var(--bg); border:1px solid var(--border); border-radius:12px; width:min(560px,92%); max-height:80vh; display:flex; flex-direction:column; }
.review-head, .review-foot { display:flex; align-items:center; padding:.7rem .9rem; border-bottom:1px solid var(--border); }
.review-foot { border-bottom:none; border-top:1px solid var(--border); justify-content:flex-end; }
.review-head button { margin-left:auto; background:transparent; border:none; color:var(--muted); cursor:pointer; font-size:.9rem; }
#review-body { overflow-y:auto; padding:.4rem .9rem; }
.review-sec { font-size:.72rem; color:var(--muted); text-transform:uppercase; margin:.7rem 0 .3rem; }
.review-item { display:flex; align-items:center; gap:8px; padding:5px 0; font-size:.83rem; border-bottom:1px solid var(--border); }
.review-item button { margin-left:auto; background:transparent; border:1px solid var(--border); border-radius:5px; color:var(--muted); cursor:pointer; padding:1px 7px; font-size:.72rem; }
```

- [ ] **Step 3: Verify markup is served** (JS added next task)

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py::test_index_served -v`
Expected: PASS.

---

## Task 10: Frontend — app.js (tabs, add, remove, batch, review)

**Files:**
- Modify: `modpack_manager/web/app.js`

- [ ] **Step 1: Replace `web/app.js`** with the full manager UI:

```javascript
const state = {
  candidates: [], selected: new Set(), active: null,
  filters: { severity: "", source: "" },
  adds: [], removals: new Set(), pack: [], packLoaded: false,
  releaseFilter: "",
};
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const openLink = (u) => (u && /^https?:\/\//i.test(u))
  ? `<a class="open" href="${esc(u)}" target="_blank" rel="noopener" aria-label="Open page">↗</a>` : "";

// ---- tabs ----
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
  const name = t.dataset.tab;
  document.querySelectorAll(".tab-panel").forEach((p) => { p.hidden = p.id !== "tab-" + name; });
  if (name === "remove" && !state.packLoaded) loadPack();
}));

// ---- updates tab (existing behaviour) ----
async function load(refresh = false) {
  showLoading();
  try {
    const res = await fetch("/api/updates" + (refresh ? "?refresh=1" : ""));
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    state.candidates = data.candidates || [];
    state.selected = new Set(state.candidates.filter((c) => c.status === "ok").map((c) => c.mod_id));
    hideLoading(); renderUpdates(); updateBatch();
  } catch (e) { loadingError("Couldn't load updates: " + e.message); }
}
function visible() {
  return state.candidates.filter((c) =>
    (!state.filters.severity || c.severity === state.filters.severity) &&
    (!state.filters.source || c.platform === state.filters.source));
}
function renderUpdates() {
  const list = $("#mod-list"); list.innerHTML = "";
  for (const c of visible()) {
    const row = document.createElement("div");
    row.className = "row " + (c.status !== "ok" ? c.status : "") + (state.active === c.mod_id ? " active" : "");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = state.selected.has(c.mod_id); cb.disabled = c.status !== "ok";
    cb.addEventListener("click", (e) => { e.stopPropagation(); toggleUpdate(c.mod_id); });
    const main = document.createElement("div"); main.className = "main";
    main.innerHTML = `<div class="name">${esc(c.name)}</div><div class="ver">${esc(c.current_version)} → <b>${esc(c.latest_version)}</b></div>`;
    row.append(cb, main);
    if (c.platform === "curseforge") { const t = document.createElement("span"); t.className = "tag"; t.textContent = "CF"; row.append(t); }
    const b = document.createElement("span"); b.className = "badge " + c.severity; b.textContent = c.severity; row.append(b);
    row.addEventListener("click", () => { state.active = c.mod_id; renderUpdates(); });
    list.append(row);
  }
  $("#update-count").textContent = `${state.candidates.length} updates`;
  $("#selected-count").textContent = `${state.selected.size} selected`;
  renderReader();
}
function renderReader() {
  const c = state.candidates.find((x) => x.mod_id === state.active); const r = $("#reader");
  if (!c) { r.innerHTML = '<p class="muted">Select a mod to read its changelog.</p>'; return; }
  const link = c.platform === "modrinth" ? "Open on Modrinth ↗" : "Open on CurseForge ↗";
  let h = `<h2>${esc(c.name)} <span class="ver">${esc(c.current_version)} → <b>${esc(c.latest_version)}</b></span></h2>`;
  if (c.project_url && /^https?:\/\//i.test(c.project_url)) h += `<a class="open" href="${esc(c.project_url)}" target="_blank" rel="noopener">${link}</a>`;
  if (c.note) h += `<div class="dep">${esc(c.note)}</div>`;
  for (const e of c.changelogs) { h += `<div class="cl-ver">${esc(e.version)}<span class="cl-date">${esc(e.date)}</span></div><div class="cl-body">${e.body_html || '<span class="muted">No changelog provided.</span>'}</div>`; }
  for (const d of c.added_dependencies) { h += `<div class="dep">⚠ New required dependency: <b>${esc(d.name || d.id)}</b>${d.satisfied ? "" : " — not in your pack"}</div>`; }
  r.innerHTML = h;
}
function toggleUpdate(id) { state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id); renderUpdates(); updateBatch(); }
$("#filter-severity").addEventListener("change", (e) => { state.filters.severity = e.target.value; renderUpdates(); });
$("#filter-source").addEventListener("change", (e) => { state.filters.source = e.target.value; renderUpdates(); });
$("#select-all").addEventListener("click", () => {
  const vis = visible().filter((c) => c.status === "ok");
  const all = vis.every((c) => state.selected.has(c.mod_id));
  vis.forEach((c) => all ? state.selected.delete(c.mod_id) : state.selected.add(c.mod_id));
  renderUpdates(); updateBatch();
});

// ---- add tab ----
async function runSearch() {
  const q = $("#add-query").value.trim(); if (!q) return;
  const platform = $("#add-platform").value;
  $("#add-results").innerHTML = '<p class="muted" style="padding:.5rem">Searching…</p>';
  try {
    const looksLink = /https?:\/\//i.test(q) || /^\d+$/.test(q);
    const url = looksLink ? "/api/resolve?ref=" + encodeURIComponent(q)
                          : `/api/search?q=${encodeURIComponent(q)}&platform=${platform}`;
    const res = await fetch(url); if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const hits = looksLink ? (data.hit ? [data.hit] : []) : data.hits;
    renderResults(hits);
  } catch (e) { $("#add-results").innerHTML = `<p class="muted" style="padding:.5rem">Search failed: ${esc(e.message)}</p>`; }
}
async function renderResults(hits) {
  const box = $("#add-results"); box.innerHTML = "";
  if (!hits.length) { box.innerHTML = '<p class="muted" style="padding:.5rem">No results. Try a link or id.</p>'; return; }
  for (const hit of hits) {
    const row = document.createElement("div"); row.className = "add-row";
    const inPack = state.pack.some((m) => m.name.toLowerCase() === hit.name.toLowerCase());
    row.innerHTML = `<div class="main"><div class="name">${esc(hit.name)}</div><div class="sum">${esc(hit.summary)}</div></div>
      <span class="tag">${hit.platform === "curseforge" ? "CF" : "MR"}</span>${openLink(hit.page_url)}
      <select class="ver-sel"><option>loading…</option></select>
      <button class="add-btn">${inPack ? "In pack" : "Add"}</button>`;
    box.append(row);
    const sel = row.querySelector(".ver-sel");
    const versions = await fetchVersions(hit);
    populateVersions(sel, versions);
    const btn = row.querySelector(".add-btn");
    btn.disabled = inPack;
    btn.addEventListener("click", () => {
      const opt = versions.find((v) => v.ref === sel.value);
      if (opt) queueAdd(hit, opt, versions.side);
    });
  }
}
async function fetchVersions(hit) {
  const res = await fetch(`/api/project-versions?platform=${hit.platform}&id=${encodeURIComponent(hit.id)}`);
  if (!res.ok) return Object.assign([], { side: "BOTH" });
  const data = await res.json();
  const arr = data.versions || []; arr.side = data.side || "BOTH"; return arr;
}
function populateVersions(sel, versions) {
  const rf = state.releaseFilter;
  const shown = versions.filter((v) => !rf || v.type === rf);
  sel.innerHTML = (shown.length ? shown : versions)
    .map((v) => `<option value="${esc(v.ref)}">${esc(v.name)} (${esc(v.type)})</option>`).join("");
}
function queueAdd(hit, opt, side) {
  if (state.adds.some((a) => a.module_id === hit.slug)) return;
  state.adds.push({ platform: hit.platform, module_id: hit.slug, name: hit.name,
    version: opt.name, url: opt.url, side: side || "BOTH", required: true, page_url: hit.page_url });
  renderQueue(); updateBatch();
}
function renderQueue() {
  const box = $("#add-queue"); box.innerHTML = "";
  for (const a of state.adds) {
    const row = document.createElement("div"); row.className = "add-row";
    row.innerHTML = `<span class="tag">${a.platform === "curseforge" ? "CF" : "MR"}</span>
      <div class="main"><div class="name">${esc(a.name)}</div></div>
      <span class="ver">${esc(a.version)}</span>${openLink(a.page_url)}
      <button class="rm-btn">✕</button>`;
    row.querySelector(".rm-btn").addEventListener("click", () => {
      state.adds = state.adds.filter((x) => x !== a); renderQueue(); updateBatch();
    });
    box.append(row);
  }
  $("#add-queue-count").textContent = state.adds.length;
}
$("#add-search-btn").addEventListener("click", runSearch);
$("#add-query").addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(); });
$("#add-release").addEventListener("change", (e) => { state.releaseFilter = e.target.value; runSearch(); });

// ---- remove tab ----
async function loadPack() {
  try {
    const res = await fetch("/api/pack"); if (!res.ok) throw new Error("HTTP " + res.status);
    state.pack = (await res.json()).mods || []; state.packLoaded = true; renderRemove();
  } catch (e) { $("#remove-list").innerHTML = `<p class="muted" style="padding:.5rem">Couldn't load pack: ${esc(e.message)}</p>`; }
}
function renderRemove() {
  const q = ($("#remove-filter").value || "").toLowerCase();
  const plat = $("#remove-platform").value;
  const list = $("#remove-list"); list.innerHTML = "";
  for (const m of state.pack) {
    if (q && !m.name.toLowerCase().includes(q)) continue;
    if (plat && m.platform !== plat) continue;
    const row = document.createElement("div"); row.className = "row";
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = state.removals.has(m.mod_id);
    cb.addEventListener("click", () => { cb.checked ? state.removals.add(m.mod_id) : state.removals.delete(m.mod_id); updateBatch(); });
    const main = document.createElement("div"); main.className = "main";
    main.innerHTML = `<div class="name">${esc(m.name)}</div><div class="ver">${esc(m.version)}</div>`;
    row.append(cb, main);
    if (m.platform === "curseforge") { const t = document.createElement("span"); t.className = "tag"; t.textContent = "CF"; row.append(t); }
    list.append(row);
  }
}
$("#remove-filter").addEventListener("input", renderRemove);
$("#remove-platform").addEventListener("change", renderRemove);

// ---- batch + review + generate ----
function batchCounts() { return { u: state.selected.size, a: state.adds.length, r: state.removals.size }; }
function updateBatch() {
  const b = batchCounts();
  $("#batch-summary").textContent = `${b.u} updates · ${b.a} adds · ${b.r} removals`;
}
function openReview() {
  const body = $("#review-body");
  const upd = [...state.selected].map((id) => state.candidates.find((c) => c.mod_id === id)).filter(Boolean);
  const rem = [...state.removals].map((id) => state.pack.find((m) => m.mod_id === id) || { mod_id: id, name: id });
  const sec = (title, items, render) => items.length
    ? `<div class="review-sec">${title} (${items.length})</div>` + items.map(render).join("") : "";
  body.innerHTML =
    sec("Updates", upd, (c) => `<div class="review-item">${esc(c.name)} <span class="muted">${esc(c.current_version)} → ${esc(c.latest_version)}</span><button data-t="u" data-id="${esc(c.mod_id)}">remove</button></div>`) +
    sec("Adds", state.adds, (a) => `<div class="review-item">+ ${esc(a.name)} <span class="muted">${esc(a.version)}</span><button data-t="a" data-id="${esc(a.module_id)}">remove</button></div>`) +
    sec("Removals", rem, (m) => `<div class="review-item">− ${esc(m.name)}<button data-t="r" data-id="${esc(m.mod_id)}">keep</button></div>`) ||
    '<p class="muted">Nothing queued yet.</p>';
  body.querySelectorAll("button").forEach((btn) => btn.addEventListener("click", () => {
    const { t, id } = btn.dataset;
    if (t === "u") state.selected.delete(id);
    else if (t === "a") state.adds = state.adds.filter((x) => x.module_id !== id);
    else state.removals.delete(id);
    renderUpdates(); renderQueue(); if (state.packLoaded) renderRemove(); updateBatch(); openReview();
  }));
  $("#review").hidden = false;
}
$("#review-btn").addEventListener("click", openReview);
$("#review-close").addEventListener("click", () => { $("#review").hidden = true; });
async function generate() {
  const payload = { updates: [...state.selected], adds: state.adds.map(({ page_url, ...a }) => a), removals: [...state.removals] };
  if (!payload.updates.length && !payload.adds.length && !payload.removals.length) { setStatus("Nothing queued.", true); return; }
  $("#review").hidden = true;
  setStatus(`Downloading and hashing ${payload.updates.length + payload.adds.length} jar(s)…`);
  try {
    const res = await fetch("/api/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (data.failures && data.failures.length) setStatus(`Wrote nothing — failures: ${data.failures.map((f) => f.id).join(", ")}`, true);
    else if (!data.written_file) setStatus(data.note || "Nothing to generate.", true);
    else setStatus(`Wrote ${data.written_file}, bumped preview revision to ${data.new_revision}. Review the git diff, then commit & push.`);
  } catch (e) { setStatus("Generate failed: " + e.message, true); }
}
$("#generate").addEventListener("click", generate);
$("#review-generate").addEventListener("click", generate);

// ---- shared helpers ----
function setStatus(msg, isError = false) { const el = $("#status"); el.textContent = msg; el.className = "status" + (isError ? " error" : ""); el.hidden = false; }
function showLoading() { const el = $("#loading"); el.hidden = false; el.classList.remove("error"); $("#loading-text").textContent = "Scanning for updates…"; $("#loading-retry").hidden = true; }
function hideLoading() { $("#loading").hidden = true; }
function loadingError(msg) { const el = $("#loading"); el.hidden = false; el.classList.add("error"); $("#loading-text").textContent = msg; $("#loading-retry").hidden = false; }
$("#loading-retry").addEventListener("click", () => load(true));
load();
```

- [ ] **Step 2: Run the full suite** (JS isn't unit-tested; confirm backend still green)

Run: `.venv/Scripts/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 3: Node syntax check**

Run: `node --check modpack_manager/web/app.js`
Expected: no output (valid).

---

## Task 11: End-to-end verification

**Files:** none (manual verification)

- [ ] **Step 1: Full suite green**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 2: Live backend smoke** — confirm the new read endpoints work against the real pack without the browser:

```bash
.venv/Scripts/python -c "from modpack_manager import service as s; \
print('pack:', len(s.real_pack())); \
print('search:', [(h.platform, h.name) for h in s.real_search('sodium','both')][:3]); \
print('resolve:', getattr(s.real_resolve('https://modrinth.com/mod/sodium'), 'name', None)); \
r=s.real_resolve('https://modrinth.com/mod/sodium'); print('versions:', s.real_project_versions(r.platform, r.id)['side'], len(s.real_project_versions(r.platform, r.id)['versions']))"
```
Expected: a pack count, a few search hits, a resolved name, and a side + version count.

- [ ] **Step 3: Real generate over a mixed batch, then revert** — queue one cheap add + one removal + skip updates, generate, inspect, revert:

```bash
.venv/Scripts/python -c "from modpack_manager import service as s; \
r=s.real_resolve('https://modrinth.com/mod/appleskin'); v=s.real_project_versions(r.platform,r.id)['versions'][0]; \
res=s.real_generate({'updates':[], 'adds':[{'platform':r.platform,'module_id':r.slug,'name':r.name,'version':v['name'],'url':v['url'],'side':'CLIENT','required':True}], 'removals':[]}, candidates=[]); \
print(res)"
cat updates/updates-*.xml | tail -20   # inspect the add module
git checkout -- GearsAndFrontiers_Preview.xml && rm -f updates/updates-2026-*.xml   # revert (check the date)
```
Expected: `written_file` set, a full add `<Module>` with a real MD5/Size in the XML; then reverted.

- [ ] **Step 4: Browser smoke (optional)** — `.venv/Scripts/python -m modpack_manager`, click through Updates / Add (search + queue) / Remove, open Review, Generate, and revert the test output.

---

## Self-review (checked against the spec)

- **Three tabs + shared batch + one bundled generate** → Tasks 9, 10; `real_generate` (7) writes one file. ✓
- **Add: paste + search, both platforms** → Modrinth (2,3) + CurseForge (4,5) search/resolve; app.js link-vs-search detection (10). ✓
- **Platform filter** → `/api/search?platform=` (8), `real_search` merge (7), UI select (9,10). ✓
- **Release-type filter** → version `type` (3,5), UI filter (10). ✓
- **Open-page per result and per queued item** → `openLink()` used in both (10). ✓
- **Version dropdown, default latest** → sorted desc (3,5), first option default (10). ✓
- **side auto-detect (Modrinth), default BOTH** → `_detect_side` (3); CF BOTH (5). ✓
- **Queued-to-add list + Review batch panel** → app.js (10), markup (9). ✓
- **Remove: current pack minus config/removals** → `real_pack` (7), Remove tab (10). ✓
- **Generate op-aware (update/add/removal), transactional** → `write_batch_xml` (6), `real_generate` pre-hash (7). ✓
- **New endpoints** → webapp (8). ✓
- **Testing** → source unit tests (2–5), generate golden (6), webapp routes (8). ✓
- **Non-goal: no dep auto-add; no ModPath/depends editing on adds** → adds write empty depends/mod_path (6,7). ✓
```
