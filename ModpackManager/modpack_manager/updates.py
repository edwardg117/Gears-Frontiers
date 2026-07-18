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


def _check(module, config, current_project_ids, cf_ctx=None) -> Candidate | None:
    try:
        if module.platform == "modrinth":
            return modrinth.build_candidate(
                module, config.mc_version, config.loader, current_project_ids,
                api_key=config.modrinth_api_key)
        return curseforge.build_candidate(
            module, config.mc_version, config.loader, current_project_ids,
            api_key=config.curseforge_api_key, ctx=cf_ctx)
    except Exception as e:  # isolate per-mod failures
        return Candidate(
            mod_id=module.mod_id, name=module.name, platform=module.platform,
            source_url=module.url, current_version=module.version or "unknown",
            latest_version="?", severity="unknown", side=module.side,
            required=module.required, mod_type=module.mod_type,
            status="error", note=str(e))


def _modrinth_to_check(modrinth_mods, config) -> list:
    """Bulk-prefilter Modrinth mods so only those with an update (plus any the
    bulk check couldn't resolve) get an expensive per-mod version fetch."""
    if not modrinth_mods:
        return []
    try:
        updated_ids, unresolved = modrinth.find_updated_mod_ids(
            modrinth_mods, config.mc_version, config.loader, config.modrinth_api_key)
        return [m for m in modrinth_mods if m.mod_id in updated_ids] + unresolved
    except Exception:  # bulk failed entirely -> per-mod fallback for all
        return list(modrinth_mods)


def _curseforge_to_check(cf_mods, config) -> tuple[list, dict]:
    """Bulk-prefilter CF mods. Returns (mods_to_build, contexts) where contexts
    maps mod_id -> resolved {cf_mod_id, allow_dist, website} so build_candidate
    can skip the per-mod recover + info calls."""
    if not cf_mods:
        return [], {}
    try:
        updated_ids, unresolved, contexts = curseforge.find_updated_mod_ids(
            cf_mods, config.mc_version, config.loader, config.curseforge_api_key)
        return [m for m in cf_mods if m.mod_id in updated_ids] + unresolved, contexts
    except Exception:  # bulk failed entirely -> per-mod fallback for all
        return list(cf_mods), {}


def scan(modules: dict, config, max_workers: int = 5) -> list[Candidate]:
    current_project_ids = {m.project_id for m in modules.values() if m.project_id}
    eligible = [m for m in modules.values() if _eligible(m, config)]
    modrinth_mods = [m for m in eligible if m.platform == "modrinth"]
    cf_mods = [m for m in eligible if m.platform == "curseforge"]

    # the two bulk prefilters are independent network round-trips -> run concurrently
    with ThreadPoolExecutor(max_workers=2) as pre:
        cf_future = pre.submit(_curseforge_to_check, cf_mods, config)
        mr_future = pre.submit(_modrinth_to_check, modrinth_mods, config)
        cf_to_check, cf_contexts = cf_future.result()
        modrinth_to_check = mr_future.result()
    to_check = modrinth_to_check + cf_to_check

    results: list[Candidate] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check, m, config, current_project_ids, cf_contexts.get(m.mod_id)): m
                   for m in to_check}
        for fut in as_completed(futures):
            candidate = fut.result()
            if candidate is not None:
                results.append(candidate)
    results.sort(key=lambda c: (_STATUS_ORDER.get(c.status, 9),
                                _SEVERITY_ORDER.get(c.severity, 9), c.name.lower()))
    _resolve_dependency_names(results, config)
    return results


def _resolve_dependency_names(results, config):
    """Fill in human-readable names for added Modrinth dependencies (they arrive
    as opaque project ids) in one bulk lookup. Best-effort: on failure the UI
    falls back to showing the id."""
    dep_ids = {d.id for c in results if c.platform == "modrinth"
               for d in c.added_dependencies if d.name is None and d.id}
    if not dep_ids:
        return
    try:
        names = modrinth.resolve_project_names(list(dep_ids), config.modrinth_api_key)
    except Exception:
        return
    for c in results:
        for d in c.added_dependencies:
            if d.name is None:
                d.name = names.get(d.id)
