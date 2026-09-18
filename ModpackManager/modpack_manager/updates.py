"""Orchestrate: current modules -> update candidates, concurrently."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .sources import modrinth, curseforge
from .sources.base import Candidate, Notice, AddedDependency

_SEVERITY_ORDER = {"major": 0, "minor": 1, "patch": 2, "unknown": 3}
_STATUS_ORDER = {"ok": 0, "manual": 1, "error": 2}
MAX_DEPTH = 4  # direct + 3 hops; Minecraft dependency chains are shallow, and this
               # plus the `seen` set is belt-and-suspenders against cycles.


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
    dep_notice = _resolve_dependencies(results, config, current_project_ids, cf_installed_ids)
    warnings = [n for n in (mr_notice, cf_notice, dep_notice) if n]
    return ScanResult(results, warnings)


def _resolve_platform(platform, dep_ids, config):
    """Resolve one platform's pending dep ids in bulk. Returns (specs, failed)."""
    try:
        if platform == "modrinth":
            return (modrinth.resolve_dependencies(
                dep_ids, config.mc_version, config.loader, config.modrinth_api_key), False)
        if platform == "curseforge":
            return (curseforge.resolve_dependencies(
                dep_ids, config.mc_version, config.loader, config.curseforge_api_key), False)
        return {}, False
    except Exception:  # this platform's pass aborts; its deps stay addable=False
        return {}, True


def _apply_spec(dep, spec):
    """Copy a resolved add-spec onto an existing (direct) AddedDependency in place,
    preserving a name/url already set at detection time."""
    if dep.name is None:
        dep.name = spec.get("name")
    dep.slug = spec.get("slug", "")
    dep.side = spec.get("side", "BOTH")
    dep.version = spec.get("version", "")
    dep.download_url = spec.get("download_url", "")
    dep.size = spec.get("size")
    dep.addable = spec.get("addable", False)
    if spec.get("url"):
        dep.url = spec["url"]


def _new_dependency(platform, dep_id, spec):
    """Build a fresh AddedDependency for a transitive dep from its resolved spec,
    or a bare non-addable one if it never resolved (over-cap / failed lookup)."""
    spec = spec or {}
    url = spec.get("url", "")
    if not url and platform == "modrinth":
        url = f"https://modrinth.com/mod/{dep_id}"
    return AddedDependency(
        id=str(dep_id), satisfied=False, platform=platform,
        name=spec.get("name"), url=url, slug=spec.get("slug", ""),
        side=spec.get("side", "BOTH"), version=spec.get("version", ""),
        download_url=spec.get("download_url", ""), size=spec.get("size"),
        addable=spec.get("addable", False))


def _closure_from(seeds, resolved, installed):
    """Every (platform, id) reachable from `seeds` via resolved `requires` edges,
    skipping installed ids and cycles. Naturally bounded: only resolved specs
    carry edges, so the walk stops at the fixpoint's frontier."""
    out, stack = set(), list(seeds)
    while stack:
        key = stack.pop()
        platform, dep_id = key
        if key in out or dep_id in installed.get(platform, set()):
            continue
        out.add(key)
        spec = resolved.get(key)
        if spec:
            for req in spec.get("requires", []):
                stack.append((platform, str(req)))
    return out


def _closure_ids(candidate, resolved, installed):
    """`_closure_from` seeded with one candidate's direct deps."""
    return _closure_from([(d.platform, str(d.id)) for d in candidate.added_dependencies if d.id],
                         resolved, installed)


def _resolve_closure(seeds, config, installed):
    """Bounded fixpoint (MAX_DEPTH hops) over dependency `requires` edges.

    `seeds` are (platform, id) pairs already filtered against `installed`. Shared
    by both entry points — the Updates scan seeds it from candidates, the Add tab
    from a single picked version — so a dep resolves identically either way.
    Returns (resolved: {(platform, id): spec}, failed: bool).
    """
    resolved, seen, failed, depth = {}, set(), False, 0
    frontier = set(seeds)
    while frontier and depth < MAX_DEPTH:
        pending = {}
        for (platform, dep_id) in frontier:
            if (platform, dep_id) not in seen:
                pending.setdefault(platform, []).append(dep_id)
        seen |= frontier
        if not pending:
            break
        # resolve the (<=2) platforms concurrently, mirroring scan's prefilter
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = {ex.submit(_resolve_platform, p, ids, config): p
                    for p, ids in pending.items()}
            batches = {futs[f]: f.result() for f in as_completed(futs)}
        nxt = set()
        for platform, (specs, plat_failed) in batches.items():
            failed = failed or plat_failed
            for dep_id, spec in specs.items():
                resolved[(platform, str(dep_id))] = spec
                for req in spec.get("requires", []):
                    key = (platform, str(req))
                    if key not in seen and str(req) not in installed.get(platform, set()):
                        nxt.add(key)
        frontier = nxt
        depth += 1
    return resolved, failed


def add_dependencies(platform, project_id, version_ref, config, installed=None):
    """New required deps — direct and transitive — for ONE version being added.

    The Updates path detects deps as a side effect of scanning for newer files;
    a manual add has no scan, so nothing resolved its deps at all. This seeds the
    same fixpoint from the exact version picked in the Add tab, so an added mod
    pulls in its missing libraries the way an updated one does.

    `installed` is {platform: {ids}}; ids absent from it are treated as missing.
    Returns (deps: list[AddedDependency], failed: bool).
    """
    installed = installed or {}
    installed = {"modrinth": {str(x) for x in installed.get("modrinth", ())},
                 "curseforge": {str(x) for x in installed.get("curseforge", ())}}
    try:
        if platform == "curseforge":
            direct = curseforge.file_dependencies(project_id, version_ref,
                                                  config.curseforge_api_key)
        else:
            direct = modrinth.version_dependencies(version_ref, config.modrinth_api_key)
    except Exception:  # noqa: BLE001 - a dead lookup must not break the Add preview
        return [], True

    seeds = {(platform, str(d)) for d in direct
             if str(d) not in installed.get(platform, set())}
    if not seeds:
        return [], False
    resolved, failed = _resolve_closure(seeds, config, installed)
    deps = [_new_dependency(p, i, resolved.get((p, i)))
            for (p, i) in _closure_from(seeds, resolved, installed)]
    deps.sort(key=lambda d: (d.name or d.slug or d.id or "").lower())
    return deps, failed


def _resolve_dependencies(results, config, current_project_ids=frozenset(),
                          installed_cf_mod_ids=frozenset()):
    """Enrich every new required dependency — direct and transitive, both platforms —
    with a queueable add-spec, and flatten each candidate's full transitive closure
    onto its `added_dependencies`. Runs a bounded fixpoint (MAX_DEPTH hops) over a
    shared memo so a subtree shared by two updates is fetched once. Best-effort: a
    platform whose resolver raises leaves its deps addable=False and yields a
    `deps_unresolved` warning; the reactive frontend behaviour is inherited."""
    installed = {"modrinth": {str(x) for x in current_project_ids},
                 "curseforge": {str(x) for x in installed_cf_mod_ids}}

    # 1) seed the frontier from every candidate's direct deps, minus installed
    frontier = set()
    for c in results:
        for d in c.added_dependencies:
            if d.id and str(d.id) not in installed.get(d.platform, set()):
                frontier.add((d.platform, str(d.id)))
    if not frontier:
        return None

    # 2) fixpoint (shared with the Add tab's add_dependencies)
    resolved, failed = _resolve_closure(frontier, config, installed)

    # 3) attach each candidate's flattened closure: enrich direct deps in place,
    #    append transitive ones (deduped by (platform, id), sorted for determinism)
    for c in results:
        direct = {(d.platform, str(d.id)) for d in c.added_dependencies if d.id}
        for d in c.added_dependencies:
            if not d.id:
                continue
            spec = resolved.get((d.platform, str(d.id)))
            if spec:
                _apply_spec(d, spec)
        for key in sorted(_closure_ids(c, resolved, installed) - direct):
            platform, dep_id = key
            c.added_dependencies.append(_new_dependency(platform, dep_id, resolved.get(key)))

    if failed:
        return Notice("warn", "deps_unresolved",
                      "Dependency resolution failed — some new required dependencies were not "
                      "auto-queued. Check the changelog banners and add them manually.")
    return None
