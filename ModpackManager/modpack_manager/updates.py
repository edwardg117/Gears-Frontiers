"""Orchestrate: current modules -> update candidates, concurrently."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .sources import modrinth, curseforge
from .sources.base import Candidate, Notice

_SEVERITY_ORDER = {"major": 0, "minor": 1, "patch": 2, "unknown": 3}
_STATUS_ORDER = {"ok": 0, "manual": 1, "error": 2}


@dataclass
class ScanResult:
    candidates: list
    warnings: list


def _eligible(module, config) -> bool:
    return (
        module.platform in ("modrinth", "curseforge")
        and module.mod_type != "Removal"
        and module.mod_id not in config.excluded_mods
    )


def _check(module, config, current_project_ids, installed_cf_mod_ids, cf_ctx=None) -> Candidate | None:
    try:
        if module.platform == "modrinth":
            return modrinth.build_candidate(
                module, config.mc_version, config.loader, current_project_ids,
                api_key=config.modrinth_api_key)
        return curseforge.build_candidate(
            module, config.mc_version, config.loader, installed_cf_mod_ids,
            api_key=config.curseforge_api_key, ctx=cf_ctx)
    except Exception as e:  # isolate per-mod failures
        return Candidate(
            mod_id=module.mod_id, name=module.name, platform=module.platform,
            source_url=module.url, current_version=module.version or "unknown",
            latest_version="?", severity="unknown", side=module.side,
            required=module.required, mod_type=module.mod_type,
            status="error", note=str(e))


def _modrinth_to_check(modrinth_mods, config):
    """Bulk-prefilter Modrinth mods. Returns (mods_to_build, notice_or_None)."""
    if not modrinth_mods:
        return [], None
    try:
        updated_ids, unresolved = modrinth.find_updated_mod_ids(
            modrinth_mods, config.mc_version, config.loader, config.modrinth_api_key)
        return [m for m in modrinth_mods if m.mod_id in updated_ids] + unresolved, None
    except Exception:  # bulk failed entirely -> per-mod fallback for all
        return list(modrinth_mods), Notice(
            "info", "modrinth_bulk_fallback",
            "Modrinth bulk update-check was unavailable — fell back to per-mod checks (results are complete).")


def _curseforge_to_check(cf_mods, config):
    """Bulk-prefilter CF mods. Returns
    (mods_to_build, contexts, installed_cf_mod_ids, notice_or_None)."""
    if not cf_mods:
        return [], {}, set(), None
    try:
        updated_ids, unresolved, contexts, installed_cf_mod_ids = curseforge.find_updated_mod_ids(
            cf_mods, config.mc_version, config.loader, config.curseforge_api_key)
        return ([m for m in cf_mods if m.mod_id in updated_ids] + unresolved,
                contexts, installed_cf_mod_ids, None)
    except Exception:  # bulk failed entirely -> per-mod fallback for all
        return list(cf_mods), {}, set(), Notice(
            "info", "curseforge_bulk_fallback",
            "CurseForge bulk update-check was unavailable — fell back to per-mod checks (results are complete).")


def scan(modules: dict, config, max_workers: int = 5) -> ScanResult:
    current_project_ids = {m.project_id for m in modules.values()
                           if m.project_id and m.mod_type != "Removal"}
    eligible = [m for m in modules.values() if _eligible(m, config)]
    modrinth_mods = [m for m in eligible if m.platform == "modrinth"]
    cf_mods = [m for m in eligible if m.platform == "curseforge"]

    # the two bulk prefilters are independent network round-trips -> run concurrently
    with ThreadPoolExecutor(max_workers=2) as pre:
        cf_future = pre.submit(_curseforge_to_check, cf_mods, config)
        mr_future = pre.submit(_modrinth_to_check, modrinth_mods, config)
        cf_to_check, cf_contexts, cf_installed_ids, cf_notice = cf_future.result()
        modrinth_to_check, mr_notice = mr_future.result()
    to_check = modrinth_to_check + cf_to_check

    results: list[Candidate] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check, m, config,
                             current_project_ids=current_project_ids,
                             installed_cf_mod_ids=cf_installed_ids,
                             cf_ctx=cf_contexts.get(m.mod_id)): m
                   for m in to_check}
        for fut in as_completed(futures):
            candidate = fut.result()
            if candidate is not None:
                results.append(candidate)
    results.sort(key=lambda c: (_STATUS_ORDER.get(c.status, 9),
                                _SEVERITY_ORDER.get(c.severity, 9), c.name.lower()))
    dep_notice = _resolve_dependencies(results, config)
    warnings = [n for n in (mr_notice, cf_notice, dep_notice) if n]
    return ScanResult(results, warnings)


def _resolve_dependencies(results, config):
    """Enrich each new (unsatisfied) dependency with a queueable add-spec: name,
    slug, side, latest compatible version + download url + size, and an `addable`
    flag. One bulk pass over all Modrinth candidates. Best-effort — a dep we
    can't resolve stays addable=False and the UI keeps showing the warning
    without auto-queuing it."""
    dep_ids = {d.id for c in results if c.platform == "modrinth"
               for d in c.added_dependencies if d.id}
    if not dep_ids:
        return None
    try:
        specs = modrinth.resolve_dependencies(
            list(dep_ids), config.mc_version, config.loader, config.modrinth_api_key)
    except Exception:
        return Notice("warn", "deps_unresolved",
                      "Dependency resolution failed — new required dependencies were not auto-queued. "
                      "Check the changelog banners and add them manually.")
    for c in results:
        for d in c.added_dependencies:
            spec = specs.get(d.id)
            if not spec:
                continue
            if d.name is None:      # keep an already-resolved name; refresh the rest each scan
                d.name = spec.get("name")
            d.slug = spec.get("slug", "")
            d.side = spec.get("side", "BOTH")
            d.version = spec.get("version", "")
            d.download_url = spec.get("download_url", "")
            d.size = spec.get("size")
            d.addable = spec.get("addable", False)
    return None
