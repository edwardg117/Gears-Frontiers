import types
from datetime import date

from modpack_manager import service
from modpack_manager.sources.base import Candidate


def _fake_paths(tmp_path):
    return types.SimpleNamespace(
        root=tmp_path,
        updates_dir=tmp_path / "updates",
        preview_pack=tmp_path / "GearsAndFrontiers_Preview.xml",
        config_ini=tmp_path / "c.ini",
        cache_dir=tmp_path / "cache",
    )


def _patch_collaborators(monkeypatch, tmp_path, compute):
    monkeypatch.setattr(service, "pack_paths", lambda: _fake_paths(tmp_path))
    monkeypatch.setattr(service, "load_config", lambda p: types.SimpleNamespace(mc_version="1.21.1"))
    monkeypatch.setattr(service, "parse_packs", lambda layers: {})
    monkeypatch.setattr(service, "_pack_layer_paths", lambda paths: [])
    monkeypatch.setattr(service, "compute", compute)
    monkeypatch.setattr(service.gen, "write_batch_xml", lambda entries, out, mc: [])
    monkeypatch.setattr(service.gen, "wire_into_preview", lambda preview, url: "7")
    monkeypatch.setattr(service.git_ops, "diff", lambda root, paths: "DIFF")


def _cand():
    return Candidate(mod_id="a", name="ModA", platform="modrinth",
                     source_url="http://x/a.jar", current_version="1", latest_version="2",
                     severity="minor", side="BOTH", required=True, mod_type="Regular", status="ok")


def test_generate_events_emits_progress_then_result(monkeypatch, tmp_path):
    _patch_collaborators(monkeypatch, tmp_path, lambda url, cache=None: ("abc123", 10))
    events = list(service.generate_events(
        {"updates": ["a"], "adds": [], "removals": []}, [_cand()]))

    progress = [e for e in events if e["type"] == "progress"]
    result = [e for e in events if e["type"] == "result"][0]
    assert progress[0]["i"] == 1 and progress[0]["n"] == 1 and progress[0]["name"] == "ModA"
    today = date.today().isoformat()
    assert result["written_file"] == f"updates/updates-{today}.xml"
    assert result["touched_files"] == [f"updates/updates-{today}.xml", "GearsAndFrontiers_Preview.xml"]
    assert result["diff"] == "DIFF"


def test_generate_events_failure_yields_no_touched(monkeypatch, tmp_path):
    def boom(url, cache=None):
        raise RuntimeError("network")
    _patch_collaborators(monkeypatch, tmp_path, boom)
    events = list(service.generate_events(
        {"updates": ["a"], "adds": [], "removals": []}, [_cand()]))
    result = [e for e in events if e["type"] == "result"][0]
    assert result["failures"] and result["written_file"] is None
    assert result["touched_files"] == [] and result["diff"] == ""


def test_generate_events_nothing_queued(monkeypatch, tmp_path):
    _patch_collaborators(monkeypatch, tmp_path, lambda url, cache=None: ("abc123", 10))
    events = list(service.generate_events(
        {"updates": [], "adds": [], "removals": []}, []))
    result = [e for e in events if e["type"] == "result"][0]
    assert result["note"] and result["written_file"] is None
    assert result["touched_files"] == [] and result["diff"] == ""


def test_real_commit_delegates_to_git_ops(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(service, "pack_paths", lambda: types.SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(service.git_ops, "commit",
                        lambda root, paths, msg: seen.update(root=root, paths=paths, msg=msg) or {"ok": True, "sha": "z"})
    out = service.real_commit(["updates/u.xml", "GearsAndFrontiers_Preview.xml"], "msg")
    assert out == {"ok": True, "sha": "z"}
    assert seen["root"] == tmp_path and seen["paths"][0] == "updates/u.xml" and seen["msg"] == "msg"


def test_real_search_records_notice_on_platform_failure(monkeypatch, tmp_path):
    from modpack_manager.sources.base import SearchHit
    monkeypatch.setattr(service, "pack_paths", lambda: types.SimpleNamespace(config_ini=tmp_path / "c.ini"))
    monkeypatch.setattr(service, "load_config", lambda p: types.SimpleNamespace(
        mc_version="1.21.1", loader="neoforge", modrinth_api_key="", curseforge_api_key="k"))
    monkeypatch.setattr(service.modrinth, "search", lambda *a, **k: [SearchHit("modrinth", "A", "a", "A", "", "", "p")])
    def boom(*a, **k):
        raise RuntimeError("cf down")
    monkeypatch.setattr(service.curseforge, "search", boom)
    hits, warnings = service.real_search("x", "both")
    assert [h.id for h in hits] == ["A"]                                 # modrinth hit still returned
    assert any(w.code == "curseforge_search_failed" and w.level == "warn" for w in warnings)
