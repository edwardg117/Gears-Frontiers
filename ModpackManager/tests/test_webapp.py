from modpack_manager.sources.base import Candidate, SearchHit
from modpack_manager import webapp


def _cand(mod_id="appleskin"):
    return Candidate(mod_id=mod_id, name="AppleSkin", platform="modrinth",
                     source_url="https://x/new.jar", current_version="3.0.5",
                     latest_version="3.1.0", severity="minor", side="CLIENT",
                     required=True, mod_type="Regular", status="ok", latest_size=10)


def _client(calls):
    app = webapp.create_app(
        scan_fn=lambda: (calls.setdefault("scan", 0), calls.update(scan=calls["scan"] + 1),
                         [_cand()])[-1],
        generate_fn=lambda payload, candidates=None: (calls.__setitem__("gen", payload),
                                                      {"written_file": "updates/u.xml",
                                                       "new_revision": "5", "mods": [], "failures": []})[-1],
        pack_fn=lambda: [{"mod_id": "farsight", "name": "Farsight", "version": "1.2",
                          "platform": "modrinth", "side": "BOTH"}],
        search_fn=lambda q, platform: [SearchHit("modrinth", "AAB", "sodium", "Sodium", "", "", "p")],
        resolve_fn=lambda ref: SearchHit("modrinth", "AAB", "sodium", "Sodium", "", "", "p"),
        versions_fn=lambda platform, pid: {"side": "CLIENT",
                                           "versions": [{"ref": "V1", "name": "0.5.8",
                                                         "type": "release", "url": "u"}]})
    app.config["TESTING"] = True
    return app.test_client()


def test_pack_route():
    c = _client({})
    assert c.get("/api/pack").get_json()["mods"][0]["mod_id"] == "farsight"


def test_search_route():
    c = _client({})
    data = c.get("/api/search?q=sodium&platform=both").get_json()
    assert data["hits"][0]["id"] == "AAB"


def test_resolve_route():
    c = _client({})
    assert c.get("/api/resolve?ref=sodium").get_json()["hit"]["slug"] == "sodium"


def test_versions_route():
    c = _client({})
    data = c.get("/api/project-versions?platform=modrinth&id=AAB").get_json()
    assert data["side"] == "CLIENT"
    assert data["versions"][0]["ref"] == "V1"


def test_generate_passes_full_payload():
    calls = {}
    c = _client(calls)
    body = {"updates": ["appleskin"], "adds": [], "removals": ["farsight"]}
    resp = c.post("/api/generate", json=body)
    assert resp.get_json()["new_revision"] == "5"
    assert calls["gen"] == body


def test_index_served():
    c = _client({})
    assert c.get("/").status_code == 200
