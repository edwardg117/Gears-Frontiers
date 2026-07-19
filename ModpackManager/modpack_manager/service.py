"""Wire the real collaborators for the running app."""

import xml.etree.ElementTree as ET
from datetime import date

from . import generate as gen
from . import updates as upd
from . import git_ops
from .config import load_config
from .hashing import HashCache, compute
from .paths import pack_paths
from .sources import modrinth, curseforge
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
        # the URL is the `url` attribute; the element text is just a label
        url = (el.get("url") or "").strip()
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


def generate_events(payload, candidates=None):
    """Generator: yields {'type':'progress',...} per downloaded jar, then a single
    {'type':'result',...}. payload: {updates:[mod_id], adds:[AddSpec], removals:[mod_id]}."""
    paths = pack_paths()
    config = load_config(paths.config_ini)
    modules = parse_packs(_pack_layer_paths(paths))
    if candidates is None:
        yield {"type": "progress", "phase": "scanning"}
        candidates = real_scan()
    cand_by_id = {c.mod_id: c for c in candidates}
    cache = HashCache(paths.cache_dir / "hashes.json")

    # Collect the jars to download first, so progress can report a known total.
    # Each spec: (op, name, mod_id, side, required, mod_type, depends, mod_path, url, version)
    specs = []
    for mid in payload.get("updates", []):
        c = cand_by_id.get(mid)
        if not c or c.status != "ok":
            continue
        m = modules.get(mid)
        specs.append(("update", c.name, mid, c.side, c.required, c.mod_type,
                      m.depends if m else "", m.mod_path if m else None,
                      c.source_url, c.latest_version))
    for spec in payload.get("adds", []):
        specs.append(("add", spec["name"], spec["module_id"], spec.get("side", "BOTH"),
                      bool(spec.get("required", True)), "Regular", "", None,
                      spec["url"], spec.get("version", "")))

    entries, failures = [], []
    total = len(specs)
    for i, (op, name, mod_id, side, required, mod_type, depends, mod_path, url, version) in enumerate(specs, 1):
        yield {"type": "progress", "i": i, "n": total, "name": name}
        try:
            md5, size = compute(url, cache=cache)
        except Exception as e:  # noqa: BLE001
            failures.append({"id": mod_id, "error": str(e)})
            continue
        entries.append({"kind": "regular", "op": op, "name": name, "id": mod_id,
                        "side": side, "required": required, "mod_type": mod_type,
                        "depends": depends, "mod_path": mod_path, "url": url,
                        "md5": md5, "size": size, "version": version})

    for mid in payload.get("removals", []):
        m = modules.get(mid)
        if m:
            entries.append({"kind": "removal", "name": m.name, "id": mid, "side": m.side,
                            "size": m.size, "required": m.required})

    manual_count = sum(1 for c in candidates if getattr(c, "status", None) == "manual")

    if failures:
        yield {"type": "result", "written_file": None, "new_revision": None, "mods": [],
               "failures": failures, "touched_files": [], "diff": "", "manual_count": manual_count}
        return
    if not entries:
        yield {"type": "result", "written_file": None, "new_revision": None, "mods": [],
               "failures": [], "note": "Nothing queued — nothing written.",
               "touched_files": [], "diff": "", "manual_count": manual_count}
        return

    today = date.today().isoformat()
    out_path = paths.updates_dir / f"updates-{today}.xml"
    summary = gen.write_batch_xml(entries, out_path, config.mc_version)
    new_rev = gen.wire_into_preview(paths.preview_pack, f"{_GITHUB_RAW}updates-{today}.xml")
    written_file = f"updates/updates-{today}.xml"
    touched = [written_file, paths.preview_pack.name]
    yield {"type": "result", "written_file": written_file, "new_revision": new_rev,
           "mods": summary, "failures": [], "touched_files": touched,
           "diff": git_ops.diff(paths.root, touched), "manual_count": manual_count}


def real_generate(payload, candidates=None):
    """Synchronous drain of generate_events -> the final result dict (minus the
    streaming-only 'type' key). Kept for non-streaming callers/tests."""
    result = {"written_file": None, "new_revision": None, "mods": [], "failures": []}
    for evt in generate_events(payload, candidates):
        if evt.get("type") == "result":
            result = {k: v for k, v in evt.items() if k != "type"}
    return result


def real_commit(touched, message):
    """Stage + commit exactly the paths generate wrote (see git_ops.commit)."""
    return git_ops.commit(pack_paths().root, touched, message)


def real_discard(touched):
    """Revert exactly the paths generate wrote (see git_ops.discard)."""
    return git_ops.discard(pack_paths().root, touched)
