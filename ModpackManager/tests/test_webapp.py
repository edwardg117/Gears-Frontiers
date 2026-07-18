from modpack_manager.sources.base import Candidate
from modpack_manager import webapp


def _cand(mod_id="appleskin"):
    return Candidate(mod_id=mod_id, name="AppleSkin", platform="modrinth",
                     source_url="https://x/new.jar", current_version="3.0.5",
                     latest_version="3.1.0", severity="minor", side="CLIENT",
                     required=True, mod_type="Regular", status="ok", latest_size=10)


def _make_client(scan_result=None, generate_result=None):
    calls = {"scan": 0, "generate": []}

    def fake_scan():
        calls["scan"] += 1
        return scan_result or [_cand()]

    def fake_generate(selected_ids, candidates=None):
        calls["generate"].append(selected_ids)
        return generate_result or {"written_file": "updates/updates-2026-07-17.xml",
                                    "new_revision": "5", "mods": [], "failures": []}

    app = webapp.create_app(scan_fn=fake_scan, generate_fn=fake_generate)
    app.config["TESTING"] = True
    return app.test_client(), calls


def test_get_updates_returns_candidates_json():
    client, calls = _make_client()
    resp = client.get("/api/updates")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["candidates"][0]["mod_id"] == "appleskin"
    assert calls["scan"] == 1


def test_get_updates_is_cached_until_refresh():
    client, calls = _make_client()
    client.get("/api/updates")
    client.get("/api/updates")
    assert calls["scan"] == 1                      # served from cache
    client.get("/api/updates?refresh=1")
    assert calls["scan"] == 2                      # forced re-scan


def test_post_generate_passes_selected_ids():
    client, calls = _make_client()
    resp = client.post("/api/generate", json={"selected_mod_ids": ["appleskin", "create"]})
    assert resp.status_code == 200
    assert resp.get_json()["new_revision"] == "5"
    assert calls["generate"] == [["appleskin", "create"]]


def test_index_served():
    client, _ = _make_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Gears" in resp.data or b"update" in resp.data.lower()
