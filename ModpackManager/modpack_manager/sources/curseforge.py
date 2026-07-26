"""Build update candidates from the CurseForge API."""

import re

import requests
from ..version_utils import classify_severity
from ..text_render import sanitize_html
from . import http
from .base import Candidate, ChangelogEntry, SearchHit

API = "https://api.curseforge.com/v1"
_LOADER_ID = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
_VER = re.compile(r"v?(\d+\.\d+(?:\.\d+){0,2})")


def _mc_version_forms(mc_version):
    """The MC-version tokens to skip: the full version and its major.minor
    (e.g. {"1.21.1", "1.21"}) — NOT arbitrary prefixes like "1" or "1.2"."""
    parts = mc_version.split(".")
    forms = {mc_version}
    if len(parts) >= 2:
        forms.add(".".join(parts[:2]))
    return forms


def _clean_version(display, file_name, mc_version):
    """CF displayName is often a raw filename; pull the real mod version out,
    skipping the embedded Minecraft version (e.g. 1.21.1 / 1.21)."""
    mc_forms = _mc_version_forms(mc_version)
    for candidate in (display, file_name):
        if not candidate:
            continue
        s = candidate[:-4] if candidate.lower().endswith(".jar") else candidate
        toks = [t for t in _VER.findall(s) if t not in mc_forms]
        if toks:
            return toks[-1]
    return display or file_name or "?"


def _session(api_key: str) -> requests.Session:
    return http.build_session({"x-api-key": api_key, "Accept": "application/json"})


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


def _list_files(session, mod_id, mc_version, loader, max_pages=4):
    """Paginate GET /mods/{id}/files (CF caps a page at 50). Returns
    (files, hit_cap) where hit_cap is True if we stopped at the page cap and
    more files may exist beyond it."""
    all_files, hit_cap = [], False
    for page in range(max_pages):
        r = session.get(f"{API}/mods/{mod_id}/files",
                        params={"gameVersion": mc_version,
                                "modLoaderType": _LOADER_ID.get(loader, 6),
                                "index": page * 50, "pageSize": 50},
                        timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        all_files.extend(data)
        if len(data) < 50:
            break
    else:
        hit_cap = True
    return all_files, hit_cap


def _changelog(session, mod_id, file_id):
    r = session.get(f"{API}/mods/{mod_id}/files/{file_id}/changelog", timeout=30)
    if r.status_code != 200:
        return ""
    return sanitize_html(r.json().get("data", ""))


def build_candidate(module, mc_version, loader, current_project_ids, api_key="", ctx=None):
    if not api_key:
        return _error(module, "No CurseForge API key configured.")
    session = _session(api_key)
    try:
        if ctx is not None:  # bulk-resolved -> skip the per-mod recover + info calls
            mod_id, allow_dist, website = ctx["cf_mod_id"], ctx["allow_dist"], ctx["website"]
        else:
            mod_id = _recover_mod_id(session, module.cf_file_id)
            if mod_id is None:
                return _error(module, "Could not resolve CurseForge project from file id.")
            info = session.get(f"{API}/mods/{mod_id}", timeout=30)
            info.raise_for_status()
            info_data = info.json().get("data", {})
            allow_dist = info_data.get("allowModDistribution", True)
            website = (info_data.get("links") or {}).get("websiteUrl", "") or ""

        files, hit_cap = _list_files(session, mod_id, mc_version, loader)
        files.sort(key=lambda f: f.get("fileDate", ""), reverse=True)
        if not files:
            return None
        latest = files[0]
        if latest.get("id") == module.cf_file_id:
            return None  # already newest

        ids = [f.get("id") for f in files]
        if module.cf_file_id in ids:
            newer = files[: ids.index(module.cf_file_id)]
            range_note = ""
        else:
            newer = [latest]
            range_note = ("Older files are beyond the fetch limit — showing the latest changelog only."
                          if hit_cap else
                          "Installed version not found among current files; showing latest only.")
        changelogs = [
            ChangelogEntry(_clean_version(f.get("displayName"), f.get("fileName"), mc_version),
                           (f.get("fileDate") or "")[:10], _changelog(session, mod_id, f["id"]))
            for f in newer
        ]

        latest_ver = _clean_version(latest.get("displayName"), latest.get("fileName"), mc_version)
        installed = next((f for f in files if f.get("id") == module.cf_file_id), None)
        # trust the pack's Meta version only if it actually looks like a version
        has_meta_version = module.version and any(ch.isdigit() for ch in module.version)
        current_ver = module.version if has_meta_version else (
            _clean_version(installed.get("displayName"), installed.get("fileName"), mc_version)
            if installed else "unknown")

        blocked = (not allow_dist) or not latest.get("downloadUrl")
        return Candidate(
            mod_id=module.mod_id, name=module.name, platform="curseforge",
            source_url=latest.get("downloadUrl") or module.url,
            current_version=current_ver,
            latest_version=latest_ver,
            severity=classify_severity(current_ver, latest_ver),
            side=module.side, required=module.required, mod_type=module.mod_type,
            changelogs=changelogs, added_dependencies=[],
            status="manual" if blocked else "ok",
            note=("This mod blocks third-party downloads — update it manually."
                  if blocked else range_note),
            latest_size=latest.get("fileLength"), project_url=website,
        )
    except requests.RequestException as e:
        return _error(module, f"CurseForge request failed: {e}")


# --- Bulk update check (few calls for the whole pack) --------------------------

def _chunk(seq, n=50):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _bulk_file_to_mod(session, file_ids):
    """installed fileId -> modId, via POST /mods/files."""
    out = {}
    for chunk in _chunk(file_ids):
        r = session.post(f"{API}/mods/files", json={"fileIds": chunk}, timeout=30)
        r.raise_for_status()
        for f in r.json().get("data", []):
            if f.get("id") is not None and f.get("modId") is not None:
                out[f["id"]] = f["modId"]
    return out


def _bulk_mods(session, mod_ids):
    """modId -> mod object, via POST /mods."""
    out = {}
    for chunk in _chunk(mod_ids):
        r = session.post(f"{API}/mods", json={"modIds": chunk}, timeout=30)
        r.raise_for_status()
        for m in r.json().get("data", []):
            out[m["id"]] = m
    return out


def _latest_compatible_file_id(mod_obj, mc_version, loader):
    """Latest file id for our MC version + loader from latestFilesIndexes."""
    loader_id = _LOADER_ID.get(loader, 6)
    matches = [
        ix.get("fileId")
        for ix in (mod_obj.get("latestFilesIndexes") or [])
        if ix.get("gameVersion") == mc_version
        and ix.get("modLoader") == loader_id
        and ix.get("fileId") is not None
    ]
    return max(matches) if matches else None


def find_updated_mod_ids(modules, mc_version, loader, api_key=""):
    """Bulk update check for many CurseForge mods in a handful of requests.

    Returns (updated_mod_ids, unresolved, contexts):
      - updated_mod_ids: set of mod ids with a newer compatible file
      - unresolved: modules the bulk pass couldn't decide (per-mod fallback)
      - contexts: mod_id -> {cf_mod_id, allow_dist, website} for resolved mods,
        so build_candidate can skip re-fetching the recover + info calls.
    """
    if not api_key:  # let the per-mod path report the key error for each mod
        return set(), list(modules), {}
    session = _session(api_key)
    file_ids = [m.cf_file_id for m in modules if m.cf_file_id]
    file_to_mod = _bulk_file_to_mod(session, file_ids)
    mod_objs = _bulk_mods(session, list(set(file_to_mod.values())))

    updated, unresolved, contexts = set(), [], {}
    for m in modules:
        cf_mod_id = file_to_mod.get(m.cf_file_id)
        mod_obj = mod_objs.get(cf_mod_id) if cf_mod_id is not None else None
        if mod_obj is None:
            unresolved.append(m)
            continue
        latest_fid = _latest_compatible_file_id(mod_obj, mc_version, loader)
        if latest_fid is None:
            unresolved.append(m)   # bulk index had nothing for our version/loader
            continue
        contexts[m.mod_id] = {
            "cf_mod_id": cf_mod_id,
            "allow_dist": mod_obj.get("allowModDistribution", True),
            "website": (mod_obj.get("links") or {}).get("websiteUrl", "") or "",
        }
        if latest_fid != m.cf_file_id:
            updated.add(m.mod_id)
    return updated, unresolved, contexts


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


def project_changelog(mod_id, file_id, api_key=""):
    """One file's changelog for the Add preview. `mod_id` = the CF project id
    (hit.id); `file_id` = the `ref` from project_versions (the CF file id).
    Reuses `_changelog` (sanitized HTML, "" on non-200). CF's changelog endpoint
    carries no version/date, so those stay empty and the frontend falls back to
    the dropdown label. Best-effort: any failure returns an all-empty object."""
    if not api_key:
        return {"version": "", "date": "", "body_html": ""}
    try:
        session = _session(api_key)
        return {"version": "", "date": "", "body_html": _changelog(session, mod_id, file_id)}
    except Exception:  # noqa: BLE001
        return {"version": "", "date": "", "body_html": ""}
