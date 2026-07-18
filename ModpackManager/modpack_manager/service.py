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


def real_generate(selected_ids, candidates=None):
    paths = pack_paths()
    config = load_config(paths.config_ini)
    modules = parse_packs(_pack_layer_paths(paths))
    if candidates is None:
        candidates = real_scan()
    by_id = {c.mod_id: c for c in candidates}
    chosen = [by_id[i] for i in selected_ids if i in by_id and by_id[i].status == "ok"]
    if not chosen:
        return {"written_file": None, "new_revision": None, "mods": [], "failures": [],
                "note": "No updatable mods were selected — nothing written."}

    cache = HashCache(paths.cache_dir / "hashes.json")
    failures = []

    def hashfn(url):
        return compute(url, cache=cache)

    # Pre-hash everything first so a failure aborts before we write (transactional).
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
