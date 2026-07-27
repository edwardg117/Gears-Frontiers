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
