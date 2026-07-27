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
    monkeypatch.setattr(updates.modrinth, "find_updated_mod_ids",
                        lambda mods_, *a, **k: ({m.mod_id for m in mods_}, []))
    monkeypatch.setattr(updates.curseforge, "find_updated_mod_ids",
                        lambda mods_, *a, **k: ({m.mod_id for m in mods_}, [], {}, set()))
    monkeypatch.setattr(updates.modrinth, "build_candidate",
                        lambda m, *a, **k: _cand(m.mod_id, "minor"))
    monkeypatch.setattr(updates.curseforge, "build_candidate",
                        lambda m, *a, **k: _cand(m.mod_id, "major"))

    from modpack_manager.config import Config
    result = updates.scan(mods, Config())
    ids = [c.mod_id for c in result.candidates]
    assert set(ids) == {"a", "b"}          # c skipped (unknown), d skipped (Removal)
    assert ids[0] == "b"                    # major sorts before minor
    assert result.warnings == []


def test_scan_isolates_per_mod_errors(monkeypatch):
    mods = {"a": _mod("a", "https://cdn.modrinth.com/data/A/versions/V/a.jar")}

    def boom(*a, **k):
        raise RuntimeError("api down")

    monkeypatch.setattr(updates.modrinth, "find_updated_mod_ids",
                        lambda mods_, *a, **k: ({m.mod_id for m in mods_}, []))
    monkeypatch.setattr(updates.modrinth, "build_candidate", boom)
    from modpack_manager.config import Config
    result = updates.scan(mods, Config())
    assert result.candidates[0].status == "error"
    assert "api down" in result.candidates[0].note


def test_excluded_mods_are_skipped(monkeypatch):
    mods = {"a": _mod("a", "https://cdn.modrinth.com/data/A/versions/V/a.jar")}
    monkeypatch.setattr(updates.modrinth, "build_candidate",
                        lambda m, *a, **k: _cand(m.mod_id))
    from modpack_manager.config import Config
    result = updates.scan(mods, Config(excluded_mods={"a"}))
    assert result.candidates == []


def _cand_with_dep(mod_id, dep_id):
    from modpack_manager.sources.base import AddedDependency
    c = _cand(mod_id, "minor")
    c.added_dependencies = [AddedDependency(id=dep_id, satisfied=False)]
    return c


def test_resolve_dependencies_enriches_candidate(monkeypatch):
    c = _cand_with_dep("createbigcannons", "DEP1")

    def fake_resolve(ids, mc, loader, key):
        assert list(ids) == ["DEP1"]
        return {"DEP1": {"name": "Create", "slug": "create", "side": "BOTH",
                         "version": "6.0.6", "download_url": "https://cdn/create.jar",
                         "size": 1234, "addable": True}}

    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", fake_resolve)
    from modpack_manager.config import Config
    updates._resolve_dependencies([c], Config())
    d = c.added_dependencies[0]
    assert d.name == "Create"
    assert d.slug == "create"
    assert d.side == "BOTH"
    assert d.version == "6.0.6"
    assert d.download_url == "https://cdn/create.jar"
    assert d.size == 1234
    assert d.addable is True


def test_resolve_dependencies_noop_without_deps(monkeypatch):
    called = []
    monkeypatch.setattr(updates.modrinth, "resolve_dependencies",
                        lambda *a, **k: called.append(1) or {})
    from modpack_manager.config import Config
    updates._resolve_dependencies([_cand("plain")], Config())  # candidate with no deps
    assert called == []                                        # no network pass triggered


def test_resolve_dependencies_skips_unresolved_dep(monkeypatch):
    c = _cand_with_dep("createbigcannons", "DEP1")
    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", lambda *a, **k: {})
    from modpack_manager.config import Config
    updates._resolve_dependencies([c], Config())
    d = c.added_dependencies[0]
    assert d.addable is False      # unresolved dep stays non-addable
    assert d.name is None          # left at its default; nothing copied


def test_resolve_dependencies_returns_notice_on_failure(monkeypatch):
    c = _cand_with_dep("m", "DEP1")
    def boom(*a, **k):
        raise RuntimeError("deps api down")
    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", boom)
    from modpack_manager.config import Config
    notice = updates._resolve_dependencies([c], Config())
    assert notice is not None and notice.code == "deps_unresolved" and notice.level == "warn"


def test_scan_warns_on_bulk_fallback_but_still_builds(monkeypatch):
    mods = {"a": _mod("a", "https://cdn.modrinth.com/data/A/versions/V/a.jar")}
    def boom(*a, **k):
        raise RuntimeError("bulk down")
    monkeypatch.setattr(updates.modrinth, "find_updated_mod_ids", boom)   # bulk prefilter fails
    monkeypatch.setattr(updates.modrinth, "build_candidate", lambda m, *a, **k: _cand(m.mod_id))
    from modpack_manager.config import Config
    result = updates.scan(mods, Config())
    assert [c.mod_id for c in result.candidates] == ["a"]                 # per-mod fallback still built it
    assert any(w.code == "modrinth_bulk_fallback" and w.level == "info" for w in result.warnings)


def test_resolve_dependencies_transitive_closure_and_memo(monkeypatch):
    # candidate -> A (required), A -> B (required), B not installed.
    # Two candidates share A, so the memo must fetch A once and B once.
    from modpack_manager.sources.base import AddedDependency
    c1 = _cand("cbc", "minor"); c1.added_dependencies = [AddedDependency(id="A", satisfied=False)]
    c2 = _cand("guns", "minor"); c2.added_dependencies = [AddedDependency(id="A", satisfied=False)]

    calls = []
    def fake_resolve(ids, mc, loader, key):
        calls.append(sorted(ids))
        table = {
            "A": {"name": "Arch", "slug": "arch", "side": "BOTH", "version": "1",
                  "download_url": "u", "size": 1, "addable": True, "requires": ["B"]},
            "B": {"name": "Bee", "slug": "bee", "side": "BOTH", "version": "2",
                  "download_url": "u2", "size": 2, "addable": True, "requires": []},
        }
        return {pid: table[pid] for pid in ids if pid in table}

    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", fake_resolve)
    from modpack_manager.config import Config
    notice = updates._resolve_dependencies([c1, c2], Config())
    assert notice is None
    for c in (c1, c2):
        assert {d.id for d in c.added_dependencies} == {"A", "B"}       # flattened closure
        assert {d.slug for d in c.added_dependencies} == {"arch", "bee"}
        assert all(d.platform == "modrinth" for d in c.added_dependencies)
    assert calls == [["A"], ["B"]]     # A resolved once (shared), then B once — no re-fetch


def test_resolve_dependencies_handles_cycle(monkeypatch):
    from modpack_manager.sources.base import AddedDependency
    c = _cand("root", "minor"); c.added_dependencies = [AddedDependency(id="A", satisfied=False)]
    def fake_resolve(ids, mc, loader, key):
        table = {"A": {"slug": "a", "name": "A", "side": "BOTH", "version": "1",
                       "download_url": "u", "size": 1, "addable": True, "requires": ["B"]},
                 "B": {"slug": "b", "name": "B", "side": "BOTH", "version": "1",
                       "download_url": "u", "size": 1, "addable": True, "requires": ["A"]}}
        return {pid: table[pid] for pid in ids if pid in table}
    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", fake_resolve)
    from modpack_manager.config import Config
    notice = updates._resolve_dependencies([c], Config())
    assert notice is None                              # A<->B cycle terminates via `seen`
    assert {d.id for d in c.added_dependencies} == {"A", "B"}   # each attached exactly once


def test_resolve_dependencies_depth_cap_surfaces_overcap_dep(monkeypatch):
    from modpack_manager.sources.base import AddedDependency
    c = _cand("root", "minor"); c.added_dependencies = [AddedDependency(id="D0", satisfied=False)]
    chain = {f"D{i}": [f"D{i+1}"] for i in range(5)}   # D0->D1->D2->D3->D4->D5 (6 links)
    def fake_resolve(ids, mc, loader, key):
        return {pid: {"slug": pid.lower(), "name": pid, "side": "BOTH", "version": "1",
                      "download_url": "u", "size": 1, "addable": True,
                      "requires": chain.get(pid, [])} for pid in ids}
    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", fake_resolve)
    from modpack_manager.config import Config
    updates._resolve_dependencies([c], Config())      # MAX_DEPTH == 4
    deps = {d.id: d for d in c.added_dependencies}
    assert deps["D0"].addable is True and deps["D3"].addable is True   # within the cap
    assert "D4" in deps and deps["D4"].addable is False               # over-cap: surfaced, not addable
    assert "D5" not in deps                                            # never discovered


def test_resolve_dependencies_partial_platform_failure(monkeypatch):
    # Modrinth candidate resolves a transitive chain fully; the CF candidate's
    # resolver raises -> its dep stays non-addable, MR closure is complete, one notice.
    from modpack_manager.sources.base import AddedDependency
    mr = _cand("mrmod", "minor")
    mr.added_dependencies = [AddedDependency(id="A", satisfied=False, platform="modrinth")]
    cf = _cand("cfmod", "minor"); cf.platform = "curseforge"
    cf.added_dependencies = [AddedDependency(id="306612", satisfied=False, platform="curseforge")]

    def fake_mr(ids, mc, loader, key):
        table = {"A": {"name": "Arch", "slug": "arch", "side": "BOTH", "version": "1",
                       "download_url": "u", "size": 1, "addable": True, "requires": ["B"]},
                 "B": {"name": "Bee", "slug": "bee", "side": "BOTH", "version": "2",
                       "download_url": "u2", "size": 2, "addable": True, "requires": []}}
        return {pid: table[pid] for pid in ids if pid in table}
    def boom_cf(ids, mc, loader, key):
        raise RuntimeError("cf api down")

    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", fake_mr)
    monkeypatch.setattr(updates.curseforge, "resolve_dependencies", boom_cf)
    from modpack_manager.config import Config
    notice = updates._resolve_dependencies([mr, cf], Config())
    # CF platform failed -> deps_unresolved warn notice
    assert notice is not None and notice.code == "deps_unresolved" and notice.level == "warn"
    # Modrinth closure fully resolved despite the CF failure
    assert {d.id for d in mr.added_dependencies} == {"A", "B"}
    assert all(d.addable for d in mr.added_dependencies)
    # CF dep surfaced but not addable (its resolver raised)
    cf_deps = {d.id: d for d in cf.added_dependencies}
    assert cf_deps["306612"].addable is False


def test_resolve_dependencies_skips_installed_transitive_dep(monkeypatch):
    # candidate -> A -> B, but B is already installed. The fixpoint must not
    # resolve OR attach B (installed-set filtering at the transitive frontier).
    from modpack_manager.sources.base import AddedDependency
    c = _cand("root", "minor")
    c.added_dependencies = [AddedDependency(id="A", satisfied=False, platform="modrinth")]
    resolved_ids = []
    def fake_mr(ids, mc, loader, key):
        resolved_ids.extend(ids)
        table = {"A": {"name": "A", "slug": "a", "side": "BOTH", "version": "1",
                       "download_url": "u", "size": 1, "addable": True, "requires": ["B"]},
                 "B": {"name": "B", "slug": "b", "side": "BOTH", "version": "1",
                       "download_url": "u", "size": 1, "addable": True, "requires": []}}
        return {pid: table[pid] for pid in ids if pid in table}
    monkeypatch.setattr(updates.modrinth, "resolve_dependencies", fake_mr)
    from modpack_manager.config import Config
    updates._resolve_dependencies([c], Config(), current_project_ids={"B"})  # B installed
    assert {d.id for d in c.added_dependencies} == {"A"}   # B filtered: not attached
    assert "B" not in resolved_ids                          # B filtered: never even resolved


def test_resolve_dependencies_cf_transitive_chain(monkeypatch):
    # A CF candidate whose dep 100 requires 200 (transitive), via the CF resolver.
    from modpack_manager.sources.base import AddedDependency
    c = _cand("cfmod", "minor"); c.platform = "curseforge"
    c.added_dependencies = [AddedDependency(id="100", satisfied=False, platform="curseforge")]
    def fake_cf(ids, mc, loader, key):
        table = {"100": {"name": "Lib100", "slug": "lib100", "url": "https://cf/100",
                         "side": "BOTH", "version": "1", "download_url": "u", "size": 1,
                         "addable": True, "requires": ["200"]},
                 "200": {"name": "Lib200", "slug": "lib200", "url": "https://cf/200",
                         "side": "BOTH", "version": "2", "download_url": "u2", "size": 2,
                         "addable": True, "requires": []}}
        return {i: table[i] for i in ids if i in table}
    monkeypatch.setattr(updates.curseforge, "resolve_dependencies", fake_cf)
    from modpack_manager.config import Config
    notice = updates._resolve_dependencies([c], Config())
    assert notice is None
    deps = {d.id: d for d in c.added_dependencies}
    assert set(deps) == {"100", "200"}                 # transitive CF dep attached
    assert deps["200"].platform == "curseforge"
    assert deps["200"].slug == "lib200" and deps["200"].addable is True
    assert deps["200"].url == "https://cf/200"         # CF resolver url flows through _new_dependency
