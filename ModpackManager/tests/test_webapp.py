import json

from modpack_manager.sources.base import Candidate, SearchHit
from modpack_manager.updates import ScanResult
from modpack_manager.sources.base import Notice
from modpack_manager import webapp


def _cand(mod_id="appleskin"):
    return Candidate(mod_id=mod_id, name="AppleSkin", platform="modrinth",
                     source_url="https://x/new.jar", current_version="3.0.5",
                     latest_version="3.1.0", severity="minor", side="CLIENT",
                     required=True, mod_type="Regular", status="ok", latest_size=10)


def _client(calls):
    def _gen(payload, candidates=None):
        calls["gen"] = payload
        yield {"type": "progress", "i": 1, "n": 1, "name": "AppleSkin"}
        yield {"type": "result", "written_file": "updates/u.xml", "new_revision": "5",
               "mods": [], "failures": [],
               "touched_files": ["updates/u.xml", "GearsAndFrontiers_Preview.xml"],
               "diff": "diff text", "manual_count": 0}

    app = webapp.create_app(
        scan_fn=lambda: ScanResult([_cand()], []),
        generate_fn=_gen,
        pack_fn=lambda: [{"mod_id": "farsight", "name": "Farsight", "version": "1.2",
                          "platform": "modrinth", "side": "BOTH"}],
        search_fn=lambda q, platform: ([SearchHit("modrinth", "AAB", "sodium", "Sodium", "", "", "p")], []),
        resolve_fn=lambda ref: SearchHit("modrinth", "AAB", "sodium", "Sodium", "", "", "p"),
        versions_fn=lambda platform, pid: {"side": "CLIENT",
                                           "versions": [{"ref": "V1", "name": "0.5.8",
                                                         "type": "release", "url": "u"}]},
        commit_fn=lambda touched, message: calls.update(commit=(touched, message)) or {"ok": True, "sha": "abc1234"},
        discard_fn=lambda touched: calls.update(discard=touched) or {"ok": True})
    app.config["TESTING"] = True
    return app.test_client()


def _stream_lines(resp):
    return [json.loads(ln) for ln in resp.get_data(as_text=True).splitlines() if ln.strip()]


def test_pack_route():
    assert _client({}).get("/api/pack").get_json()["mods"][0]["mod_id"] == "farsight"


def test_search_route():
    data = _client({}).get("/api/search?q=sodium&platform=both").get_json()
    assert data["hits"][0]["id"] == "AAB"
    assert data["warnings"] == []


def test_resolve_route():
    assert _client({}).get("/api/resolve?ref=sodium").get_json()["hit"]["slug"] == "sodium"


def test_versions_route():
    data = _client({}).get("/api/project-versions?platform=modrinth&id=AAB").get_json()
    assert data["side"] == "CLIENT" and data["versions"][0]["ref"] == "V1"


def test_index_served():
    assert _client({}).get("/").status_code == 200


def test_generate_streams_progress_then_result():
    calls = {}
    c = _client(calls)
    body = {"updates": ["appleskin"], "adds": [], "removals": ["farsight"]}
    resp = c.post("/api/generate", json=body)
    assert resp.status_code == 200
    events = _stream_lines(resp)
    assert events[0]["type"] == "progress"
    assert events[-1]["type"] == "result" and events[-1]["new_revision"] == "5"
    assert calls["gen"] == body


def test_commit_uses_stored_touched_paths():
    calls = {}
    c = _client(calls)
    # a generate must run first so the server records last_touched
    c.post("/api/generate", json={"updates": ["appleskin"], "adds": [], "removals": []}).get_data()  # consume the stream so last_touched is recorded
    resp = c.post("/api/commit", json={"message": "chore(preview): test"})
    assert resp.get_json() == {"ok": True, "sha": "abc1234"}
    touched, message = calls["commit"]
    assert touched == ["updates/u.xml", "GearsAndFrontiers_Preview.xml"]  # server-held, not client-sent
    assert message == "chore(preview): test"


def test_commit_without_generate_is_rejected():
    resp = _client({}).post("/api/commit", json={"message": "x"})
    assert resp.status_code == 400


def test_commit_blank_message_is_rejected():
    c = _client({})
    c.post("/api/generate", json={"updates": ["appleskin"], "adds": [], "removals": []}).get_data()  # consume the stream so last_touched is recorded
    assert c.post("/api/commit", json={"message": "   "}).status_code == 400


def test_discard_uses_stored_paths_and_clears_them():
    calls = {}
    c = _client(calls)
    c.post("/api/generate", json={"updates": ["appleskin"], "adds": [], "removals": []}).get_data()  # consume the stream so last_touched is recorded
    assert c.post("/api/discard").get_json() == {"ok": True}
    assert calls["discard"] == ["updates/u.xml", "GearsAndFrontiers_Preview.xml"]
    # cleared: a second discard now 400s (nothing recorded)
    assert c.post("/api/discard").status_code == 400


def test_failed_generate_leaves_nothing_committable():
    def _gen(payload, candidates=None):
        yield {"type": "progress", "i": 1, "n": 1, "name": "X"}
        yield {"type": "result", "written_file": None, "new_revision": None, "mods": [],
               "failures": [{"id": "x", "error": "boom"}], "touched_files": [], "diff": "",
               "manual_count": 0}
    app = webapp.create_app(
        scan_fn=lambda: ScanResult([], []), generate_fn=_gen, pack_fn=lambda: [],
        search_fn=lambda q, p: ([], []), resolve_fn=lambda r: None, versions_fn=lambda p, i: {},
        commit_fn=lambda t, m: {"ok": True, "sha": "x"}, discard_fn=lambda t: {"ok": True})
    app.config["TESTING"] = True
    c = app.test_client()
    c.post("/api/generate", json={"updates": ["x"], "adds": [], "removals": []}).get_data()
    assert c.post("/api/commit", json={"message": "m"}).status_code == 400   # no touched_files -> nothing to commit
    assert c.post("/api/discard").status_code == 400


def test_discard_failure_keeps_paths_retryable():
    calls = {"n": 0}
    def _gen(payload, candidates=None):
        yield {"type": "result", "written_file": "updates/u.xml", "new_revision": "5",
               "mods": [], "failures": [],
               "touched_files": ["updates/u.xml", "GearsAndFrontiers_Preview.xml"],
               "diff": "d", "manual_count": 0}
    def _failing_discard(touched):
        calls["n"] += 1
        return {"ok": False, "error": "restore failed"}
    app = webapp.create_app(
        scan_fn=lambda: ScanResult([], []), generate_fn=_gen, pack_fn=lambda: [],
        search_fn=lambda q, p: ([], []), resolve_fn=lambda r: None, versions_fn=lambda p, i: {},
        commit_fn=lambda t, m: {"ok": True, "sha": "x"}, discard_fn=_failing_discard)
    app.config["TESTING"] = True
    c = app.test_client()
    c.post("/api/generate", json={"updates": [], "adds": [], "removals": []}).get_data()
    assert c.post("/api/discard").get_json()["ok"] is False   # failed
    assert c.post("/api/discard").get_json()["ok"] is False   # still retryable, not 400
    assert calls["n"] == 2                                     # discard_fn called both times


def test_updates_route_returns_candidates_and_warnings():
    app = webapp.create_app(
        scan_fn=lambda: ScanResult([_cand()], [Notice("warn", "deps_unresolved", "deps failed")]),
        generate_fn=lambda p, c=None: iter([]), pack_fn=lambda: [],
        search_fn=lambda q, pl: ([], []), resolve_fn=lambda r: None,
        versions_fn=lambda pl, i: {}, commit_fn=lambda t, m: {"ok": True}, discard_fn=lambda t: {"ok": True})
    app.config["TESTING"] = True
    data = app.test_client().get("/api/updates").get_json()
    assert data["candidates"][0]["mod_id"] == "appleskin"
    assert data["warnings"][0]["code"] == "deps_unresolved"
