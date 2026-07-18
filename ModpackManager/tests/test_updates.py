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
                        lambda mods_, *a, **k: ({m.mod_id for m in mods_}, [], {}))
    monkeypatch.setattr(updates.modrinth, "build_candidate",
                        lambda m, *a, **k: _cand(m.mod_id, "minor"))
    monkeypatch.setattr(updates.curseforge, "build_candidate",
                        lambda m, *a, **k: _cand(m.mod_id, "major"))

    from modpack_manager.config import Config
    result = updates.scan(mods, Config())
    ids = [c.mod_id for c in result]
    assert set(ids) == {"a", "b"}          # c skipped (unknown), d skipped (Removal)
    assert ids[0] == "b"                    # major sorts before minor


def test_scan_isolates_per_mod_errors(monkeypatch):
    mods = {"a": _mod("a", "https://cdn.modrinth.com/data/A/versions/V/a.jar")}

    def boom(*a, **k):
        raise RuntimeError("api down")

    monkeypatch.setattr(updates.modrinth, "find_updated_mod_ids",
                        lambda mods_, *a, **k: ({m.mod_id for m in mods_}, []))
    monkeypatch.setattr(updates.modrinth, "build_candidate", boom)
    from modpack_manager.config import Config
    result = updates.scan(mods, Config())
    assert result[0].status == "error"
    assert "api down" in result[0].note


def test_excluded_mods_are_skipped(monkeypatch):
    mods = {"a": _mod("a", "https://cdn.modrinth.com/data/A/versions/V/a.jar")}
    monkeypatch.setattr(updates.modrinth, "build_candidate",
                        lambda m, *a, **k: _cand(m.mod_id))
    from modpack_manager.config import Config
    result = updates.scan(mods, Config(excluded_mods={"a"}))
    assert result == []
