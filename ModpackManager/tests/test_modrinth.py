import responses
from urllib3.util.retry import Retry
from modpack_manager.xml_model import Module
from modpack_manager.sources import modrinth

API = "https://api.modrinth.com/v2"


def _module(version_id="OLDVER11", version="3.0.5"):
    url = f"https://cdn.modrinth.com/data/PROJ1234/versions/{version_id}/appleskin-{version}.jar"
    return Module(mod_id="appleskin", name="AppleSkin", url=url, version=version)


def _versions_payload():
    return [
        {
            "id": "NEWVER22", "version_number": "3.1.0",
            "date_published": "2026-07-10T00:00:00Z",
            "changelog": "- added things",
            "dependencies": [{"project_id": "DEP0001", "dependency_type": "required"}],
            "files": [{"primary": True, "url": "https://cdn.modrinth.com/new.jar", "size": 999,
                       "hashes": {"sha1": "abc"}}],
        },
        {
            "id": "MIDVER22", "version_number": "3.0.9",
            "date_published": "2026-07-01T00:00:00Z",
            "changelog": "- interim fix",
            "dependencies": [],
            "files": [{"primary": True, "url": "https://cdn.modrinth.com/mid.jar", "size": 990,
                       "hashes": {"sha1": "def"}}],
        },
        {
            "id": "OLDVER11", "version_number": "3.0.5",
            "date_published": "2026-06-01T00:00:00Z",
            "changelog": "- old",
            "dependencies": [],
            "files": [{"primary": True, "url": "https://cdn.modrinth.com/old.jar", "size": 980,
                       "hashes": {"sha1": "ghi"}}],
        },
    ]


@responses.activate
def test_build_candidate_returns_range_and_severity():
    responses.add(responses.GET, f"{API}/project/PROJ1234/version",
                  json=_versions_payload(), status=200)
    c = modrinth.build_candidate(_module(), mc_version="1.21.1", loader="neoforge",
                                 current_project_ids=set())
    assert c is not None
    assert c.latest_version == "3.1.0"
    assert c.severity == "minor"
    # changelog range excludes the installed version, newest-first
    assert [e.version for e in c.changelogs] == ["3.1.0", "3.0.9"]
    assert c.source_url == "https://cdn.modrinth.com/new.jar"
    assert c.latest_size == 999
    assert c.added_dependencies[0].id == "DEP0001"
    assert c.added_dependencies[0].satisfied is False
    assert c.added_dependencies[0].url == "https://modrinth.com/mod/DEP0001"


@responses.activate
def test_up_to_date_returns_none():
    payload = _versions_payload()[-1:]  # only the installed version
    responses.add(responses.GET, f"{API}/project/PROJ1234/version", json=payload, status=200)
    c = modrinth.build_candidate(_module(), "1.21.1", "neoforge", set())
    assert c is None


@responses.activate
def test_dependency_marked_satisfied_when_present():
    responses.add(responses.GET, f"{API}/project/PROJ1234/version",
                  json=_versions_payload(), status=200)
    c = modrinth.build_candidate(_module(), "1.21.1", "neoforge",
                                 current_project_ids={"DEP0001"})
    assert c.added_dependencies == []  # satisfied deps are not reported


@responses.activate
def test_find_updated_mod_ids_flags_only_changed():
    m1 = Module(mod_id="a", name="A",
                url="https://cdn.modrinth.com/data/PA/versions/VA1/a.jar", version="1.0")
    m2 = Module(mod_id="b", name="B",
                url="https://cdn.modrinth.com/data/PB/versions/VB1/b.jar", version="1.0")
    responses.add(responses.GET, f"{API}/versions", json=[
        {"id": "VA1", "files": [{"primary": True, "hashes": {"sha1": "sha_a"}}]},
        {"id": "VB1", "files": [{"primary": True, "hashes": {"sha1": "sha_b"}}]},
    ], status=200)
    responses.add(responses.POST, f"{API}/version_files/update", json={
        "sha_a": {"id": "VA2"},   # newer than installed VA1 -> updated
        "sha_b": {"id": "VB1"},   # unchanged -> no update
    }, status=200)
    updated, unresolved = modrinth.find_updated_mod_ids([m1, m2], "1.21.1", "neoforge")
    assert updated == {"a"}
    assert unresolved == []


@responses.activate
def test_find_updated_mod_ids_unresolved_when_hash_missing():
    m = Module(mod_id="c", name="C",
               url="https://cdn.modrinth.com/data/PC/versions/VC1/c.jar")
    responses.add(responses.GET, f"{API}/versions", json=[], status=200)  # no sha1 resolved
    updated, unresolved = modrinth.find_updated_mod_ids([m], "1.21.1", "neoforge")
    assert updated == set()
    assert [x.mod_id for x in unresolved] == ["c"]


@responses.activate
def test_resolve_dependencies_builds_addable_spec():
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "DEP0001", "slug": "cloth-config", "title": "Cloth Config API",
         "client_side": "required", "server_side": "required"},
    ], status=200)
    responses.add(responses.GET, f"{API}/project/DEP0001/version", json=[
        {"id": "CCV2", "version_number": "15.0.140",
         "date_published": "2026-07-10T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn.modrinth.com/cc.jar", "size": 4242}]},
        {"id": "CCV1", "version_number": "15.0.100",
         "date_published": "2026-06-01T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn.modrinth.com/cc-old.jar", "size": 4000}]},
    ], status=200)
    out = modrinth.resolve_dependencies(["DEP0001"], "1.21.1", "neoforge")
    spec = out["DEP0001"]
    assert spec["name"] == "Cloth Config API"
    assert spec["slug"] == "cloth-config"
    assert spec["side"] == "BOTH"
    assert spec["version"] == "15.0.140"          # newest by date
    assert spec["download_url"] == "https://cdn.modrinth.com/cc.jar"
    assert spec["size"] == 4242
    assert spec["addable"] is True


@responses.activate
def test_resolve_dependencies_detects_client_side():
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "DEP3", "slug": "clientmod", "title": "Client Mod",
         "client_side": "required", "server_side": "unsupported"}], status=200)
    responses.add(responses.GET, f"{API}/project/DEP3/version", json=[
        {"id": "V", "version_number": "1.0", "date_published": "2026-07-10T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/c.jar", "size": 1}]}], status=200)
    out = modrinth.resolve_dependencies(["DEP3"], "1.21.1", "neoforge")
    assert out["DEP3"]["side"] == "CLIENT"
    assert out["DEP3"]["addable"] is True


@responses.activate
def test_resolve_dependencies_no_compatible_version_not_addable():
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "DEP2", "slug": "somelib", "title": "Some Lib",
         "client_side": "required", "server_side": "required"}], status=200)
    responses.add(responses.GET, f"{API}/project/DEP2/version", json=[], status=200)
    out = modrinth.resolve_dependencies(["DEP2"], "1.21.1", "neoforge")
    spec = out["DEP2"]
    assert spec["name"] == "Some Lib"      # meta still resolved
    assert spec["slug"] == "somelib"
    assert spec["download_url"] == ""
    assert spec["addable"] is False


@responses.activate
def test_resolve_dependencies_meta_failure_not_addable():
    responses.add(responses.GET, f"{API}/projects", status=500)
    responses.add(responses.GET, f"{API}/project/DEP4/version", json=[
        {"id": "V", "version_number": "1.0", "date_published": "2026-07-10T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/d.jar", "size": 1}]}], status=200)
    out = modrinth.resolve_dependencies(["DEP4"], "1.21.1", "neoforge")
    spec = out["DEP4"]
    assert spec["name"] is None            # no meta -> no name
    assert spec["slug"] == ""
    assert spec["addable"] is False        # can't queue without a slug


@responses.activate
def test_resolve_dependencies_isolates_one_bad_dep():
    # DEP_OK resolves cleanly; DEP_BAD's version fetch fails (500).
    # The failure must not abort resolution of the sibling dep.
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "DEP_OK", "slug": "okmod", "title": "OK Mod",
         "client_side": "required", "server_side": "required"},
        {"id": "DEP_BAD", "slug": "badmod", "title": "Bad Mod",
         "client_side": "required", "server_side": "required"},
    ], status=200)
    responses.add(responses.GET, f"{API}/project/DEP_OK/version", json=[
        {"id": "V", "version_number": "1.0", "date_published": "2026-07-10T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/ok.jar", "size": 7}]}], status=200)
    responses.add(responses.GET, f"{API}/project/DEP_BAD/version", status=500)
    out = modrinth.resolve_dependencies(["DEP_OK", "DEP_BAD"], "1.21.1", "neoforge")
    assert out["DEP_OK"]["addable"] is True          # sibling still resolves
    assert out["DEP_OK"]["download_url"] == "https://cdn/ok.jar"
    assert out["DEP_BAD"]["addable"] is False         # bad dep degrades gracefully
    assert out["DEP_BAD"]["name"] == "Bad Mod"        # meta still filled
    assert out["DEP_BAD"]["requires"] == []           # failed version fetch -> empty requires


@responses.activate
def test_resolve_dependencies_handles_null_date_published():
    # Regression: a version with date_published: null previously made .sort()
    # raise TypeError and abort the whole batch. It must now sort as oldest.
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "DEPN", "slug": "nulldate", "title": "Null Date Mod",
         "client_side": "required", "server_side": "required"}], status=200)
    responses.add(responses.GET, f"{API}/project/DEPN/version", json=[
        {"id": "VN", "version_number": "2.0", "date_published": None,
         "files": [{"primary": True, "url": "https://cdn/n2.jar", "size": 20}]},
        {"id": "VO", "version_number": "1.0", "date_published": "2026-06-01T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/n1.jar", "size": 10}]},
    ], status=200)
    out = modrinth.resolve_dependencies(["DEPN"], "1.21.1", "neoforge")
    spec = out["DEPN"]
    assert spec["addable"] is True                    # resolved, no crash
    assert spec["version"] == "1.0"                    # null date sorts oldest, so VO (1.0) is newest
    assert spec["download_url"] == "https://cdn/n1.jar"


@responses.activate
def test_search_returns_hits():
    responses.add(responses.GET, f"{API}/search", json={"hits": [
        {"project_id": "AAB", "slug": "sodium", "title": "Sodium",
         "description": "fast", "icon_url": "https://i/s.png"},
    ]}, status=200)
    hits = modrinth.search("sodium", "1.21.1", "neoforge")
    assert len(hits) == 1
    assert hits[0].platform == "modrinth"
    assert hits[0].id == "AAB"
    assert hits[0].name == "Sodium"
    assert hits[0].page_url == "https://modrinth.com/mod/sodium"


@responses.activate
def test_resolve_link_to_project():
    responses.add(responses.GET, f"{API}/project/sodium", json={
        "id": "AAB", "slug": "sodium", "title": "Sodium", "description": "fast",
        "icon_url": "i.png"}, status=200)
    hit = modrinth.resolve("https://modrinth.com/mod/sodium")
    assert hit.id == "AAB"
    assert hit.name == "Sodium"


@responses.activate
def test_project_versions_side_and_types():
    responses.add(responses.GET, f"{API}/project/AAB", json={
        "id": "AAB", "slug": "sodium", "title": "Sodium",
        "client_side": "required", "server_side": "unsupported"}, status=200)
    responses.add(responses.GET, f"{API}/project/AAB/version", json=[
        {"id": "V2", "version_number": "0.6.0", "version_type": "beta",
         "date_published": "2026-07-10T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/0.6.0.jar"}]},
        {"id": "V1", "version_number": "0.5.8", "version_type": "release",
         "date_published": "2026-06-01T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/0.5.8.jar"}]},
    ], status=200)
    out = modrinth.project_versions("AAB", "1.21.1", "neoforge")
    assert out["side"] == "CLIENT"
    assert [v["type"] for v in out["versions"]] == ["beta", "release"]
    assert out["versions"][0]["url"] == "https://cdn/0.6.0.jar"
    assert out["versions"][1]["ref"] == "V1"


@responses.activate
def test_build_candidate_handles_null_date_published():
    # Regression: a version with date_published: null previously made .sort()
    # raise TypeError. Null dates must sort as oldest instead of crashing.
    responses.add(responses.GET, f"{API}/project/PROJ1234/version", json=[
        {"id": "NEWVER", "version_number": "2.0", "date_published": "2026-07-10T00:00:00Z",
         "changelog": "new", "dependencies": [],
         "files": [{"primary": True, "url": "https://cdn.modrinth.com/new.jar", "size": 10,
                    "hashes": {"sha1": "a"}}]},
        {"id": "NULLVER", "version_number": "1.5", "date_published": None,
         "changelog": "null date", "dependencies": [],
         "files": [{"primary": True, "url": "https://cdn.modrinth.com/null.jar", "size": 5,
                    "hashes": {"sha1": "b"}}]},
    ], status=200)
    m = Module(mod_id="appleskin", name="AppleSkin",
               url="https://cdn.modrinth.com/data/PROJ1234/versions/NULLVER/appleskin-1.5.jar",
               version="1.5")
    c = modrinth.build_candidate(m, "1.21.1", "neoforge", current_project_ids=set())
    assert c is not None
    assert c.latest_version == "2.0"                       # null date sorts oldest -> NEWVER wins
    assert c.source_url == "https://cdn.modrinth.com/new.jar"


@responses.activate
def test_project_versions_handles_null_date_published():
    # Regression: a version with date_published: null must not crash the sort.
    responses.add(responses.GET, f"{API}/project/AAB", json={
        "id": "AAB", "slug": "sodium", "title": "Sodium",
        "client_side": "required", "server_side": "required"}, status=200)
    responses.add(responses.GET, f"{API}/project/AAB/version", json=[
        {"id": "V2", "version_number": "0.6.0", "version_type": "release",
         "date_published": None,
         "files": [{"primary": True, "url": "https://cdn/0.6.0.jar"}]},
        {"id": "V1", "version_number": "0.5.8", "version_type": "release",
         "date_published": "2026-06-01T00:00:00Z",
         "files": [{"primary": True, "url": "https://cdn/0.5.8.jar"}]},
    ], status=200)
    out = modrinth.project_versions("AAB", "1.21.1", "neoforge")
    assert [v["ref"] for v in out["versions"]] == ["V1", "V2"]  # null date sorts oldest
    assert out["side"] == "BOTH"


def test_modrinth_session_uses_retrying_adapter():
    r = modrinth._session().get_adapter("https://api.modrinth.com").max_retries
    assert isinstance(r, Retry) and 429 in r.status_forcelist


def test_curseforge_session_uses_retrying_adapter():
    from modpack_manager.sources import curseforge
    r = curseforge._session("k").get_adapter("https://api.curseforge.com").max_retries
    assert isinstance(r, Retry) and 429 in r.status_forcelist


def test_hashing_default_session_uses_retrying_adapter():
    from modpack_manager import hashing
    s = hashing._download_session()
    r = s.get_adapter("https://cdn.example.com").max_retries
    assert isinstance(r, Retry) and 429 in r.status_forcelist


@responses.activate
def test_project_changelog_returns_version_date_body():
    responses.add(responses.GET, f"{API}/version/V2", json={
        "id": "V2", "version_number": "0.6.0", "date_published": "2026-07-10T00:00:00Z",
        "changelog": "- added things"}, status=200)
    out = modrinth.project_changelog("V2")
    assert out["version"] == "0.6.0"
    assert out["date"] == "2026-07-10"
    assert "added things" in out["body_html"]


@responses.activate
def test_project_changelog_non_200_is_empty():
    responses.add(responses.GET, f"{API}/version/BAD", status=404)
    assert modrinth.project_changelog("BAD") == {"version": "", "date": "", "body_html": ""}


@responses.activate
def test_project_changelog_transport_error_is_empty():
    responses.add(responses.GET, f"{API}/version/BOOM", body=ConnectionError("boom"))
    assert modrinth.project_changelog("BOOM") == {"version": "", "date": "", "body_html": ""}


@responses.activate
def test_resolve_dependencies_surfaces_required_requires():
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "DEP0001", "slug": "cloth-config", "title": "Cloth Config API",
         "client_side": "required", "server_side": "required"}], status=200)
    responses.add(responses.GET, f"{API}/project/DEP0001/version", json=[
        {"id": "CCV2", "version_number": "15.0.140", "date_published": "2026-07-10T00:00:00Z",
         "dependencies": [
             {"project_id": "ARCH99", "dependency_type": "required"},   # kept
             {"project_id": "OPT88", "dependency_type": "optional"},     # dropped
             {"project_id": None, "dependency_type": "required"}],       # no id -> dropped
         "files": [{"primary": True, "url": "https://cdn.modrinth.com/cc.jar", "size": 4242}]},
    ], status=200)
    out = modrinth.resolve_dependencies(["DEP0001"], "1.21.1", "neoforge")
    assert out["DEP0001"]["requires"] == ["ARCH99"]
    assert out["DEP0001"]["addable"] is True     # unchanged behaviour otherwise


# --- version_dependencies (Add path) ------------------------------------------

@responses.activate
def test_version_dependencies_returns_only_required_project_ids():
    responses.add(responses.GET, f"{API}/version/VER1", json={
        "id": "VER1",
        "dependencies": [
            {"project_id": "REQ1", "dependency_type": "required"},
            {"project_id": "OPT1", "dependency_type": "optional"},
            {"project_id": "REQ2", "dependency_type": "required"},
            {"project_id": None, "dependency_type": "required"},
        ],
    }, status=200)
    assert modrinth.version_dependencies("VER1") == ["REQ1", "REQ2"]


@responses.activate
def test_version_dependencies_is_best_effort_on_failure():
    responses.add(responses.GET, f"{API}/version/GONE", json={}, status=404)
    assert modrinth.version_dependencies("GONE") == []
