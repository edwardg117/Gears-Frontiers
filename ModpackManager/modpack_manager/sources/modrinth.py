"""Build update candidates from the Modrinth API."""

import json
import re

import requests
from ..version_utils import classify_severity
from ..text_render import render_markdown
from .base import Candidate, ChangelogEntry, AddedDependency, SearchHit

API = "https://api.modrinth.com/v2"
_UA = "Gears-Frontiers-ModpackManager/0.1 (github.com/edwardg117/Gears-Frontiers)"
_MODRINTH = re.compile(r"cdn\.modrinth\.com/data/([^/]+)/versions/([^/]+)/")


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
                added.append(AddedDependency(id=pid, satisfied=False,
                                             url=f"https://modrinth.com/mod/{pid}"))

    pf = _primary_file(latest)
    return Candidate(
        mod_id=module.mod_id, name=module.name, platform="modrinth",
        source_url=pf.get("url", ""), current_version=module.version or "unknown",
        latest_version=latest.get("version_number", "?"),
        severity=classify_severity(module.version or "", latest.get("version_number", "")),
        side=module.side, required=module.required, mod_type=module.mod_type,
        changelogs=changelogs, added_dependencies=added,
        status="ok", note=note, latest_size=pf.get("size"),
        project_url=f"https://modrinth.com/mod/{module.project_id}",
    )


# --- Bulk update check (few calls for the whole pack) --------------------------

def _chunk(seq, n=100):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _bulk_installed_hashes(session, version_ids):
    """Resolve installed version-ids -> primary-file sha1 via GET /versions?ids."""
    out = {}
    for chunk in _chunk(version_ids):
        r = session.get(f"{API}/versions", params={"ids": json.dumps(chunk)}, timeout=30)
        r.raise_for_status()
        for ver in r.json():
            files = ver.get("files", [])
            pf = next((f for f in files if f.get("primary")), files[0] if files else {})
            sha1 = (pf.get("hashes") or {}).get("sha1")
            if sha1:
                out[ver.get("id")] = sha1
    return out


def _bulk_latest(session, hashes, mc_version, loader):
    """sha1 -> latest compatible version, via POST /version_files/update."""
    out = {}
    for chunk in _chunk(hashes):
        r = session.post(
            f"{API}/version_files/update",
            json={"hashes": chunk, "algorithm": "sha1",
                  "loaders": [loader], "game_versions": [mc_version]},
            timeout=30,
        )
        r.raise_for_status()
        out.update(r.json())
    return out


def find_updated_mod_ids(modules, mc_version, loader, api_key=""):
    """Bulk update check for many Modrinth mods in a handful of requests.

    Returns (updated_mod_ids, unresolved) where updated_mod_ids is the set of
    mod ids that have a newer compatible version, and unresolved is the list of
    modules the bulk check couldn't decide (caller should fall back to a
    per-mod check for those).
    """
    session = _session(api_key)
    with_vid = [m for m in modules if m.version_id]
    vid_to_sha1 = _bulk_installed_hashes(session, [m.version_id for m in with_vid])
    hashes = list({vid_to_sha1[m.version_id] for m in with_vid if m.version_id in vid_to_sha1})
    latest_by_hash = _bulk_latest(session, hashes, mc_version, loader) if hashes else {}

    updated, unresolved = set(), []
    for m in modules:
        sha1 = vid_to_sha1.get(m.version_id)
        latest = latest_by_hash.get(sha1) if sha1 else None
        if latest is None:
            unresolved.append(m)          # couldn't resolve -> per-mod fallback
        elif latest.get("id") != m.version_id:
            updated.add(m.mod_id)
    return updated, unresolved


def resolve_project_names(project_ids, api_key=""):
    """Map Modrinth project id (and slug) -> human title, via bulk GET /projects."""
    session = _session(api_key)
    out = {}
    for chunk in _chunk(project_ids):
        r = session.get(f"{API}/projects", params={"ids": json.dumps(chunk)}, timeout=30)
        r.raise_for_status()
        for proj in r.json():
            title = proj.get("title") or proj.get("slug")
            if proj.get("id"):
                out[proj["id"]] = title
            if proj.get("slug"):
                out[proj["slug"]] = title
    return out


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
