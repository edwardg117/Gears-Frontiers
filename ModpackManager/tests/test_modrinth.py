import responses
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
def test_resolve_project_names_maps_id_and_slug_to_title():
    responses.add(responses.GET, f"{API}/projects", json=[
        {"id": "OZhUIuou", "slug": "sodium", "title": "Sodium"},
        {"id": "AABBCCDD", "slug": "lithium", "title": "Lithium"},
    ], status=200)
    names = modrinth.resolve_project_names(["OZhUIuou", "AABBCCDD"])
    assert names["OZhUIuou"] == "Sodium"
    assert names["sodium"] == "Sodium"       # slug is mapped too
    assert names["AABBCCDD"] == "Lithium"
