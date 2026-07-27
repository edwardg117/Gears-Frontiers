from modpack_manager.sources.base import Candidate, ChangelogEntry, AddedDependency


def test_candidate_to_dict_roundtrips_nested():
    c = Candidate(
        mod_id="create", name="Create", platform="modrinth",
        source_url="https://x/y.jar", current_version="6.0.4",
        latest_version="6.0.6", severity="patch", side="BOTH",
        required=True, mod_type="Regular",
        changelogs=[ChangelogEntry("6.0.6", "2026-07-10", "<p>fix</p>")],
        added_dependencies=[AddedDependency("morered", False)],
        status="ok", latest_size=1234,
    )
    d = c.to_dict()
    assert d["mod_id"] == "create"
    assert d["changelogs"][0]["version"] == "6.0.6"
    assert d["added_dependencies"][0]["id"] == "morered"
    assert d["added_dependencies"][0]["satisfied"] is False
    assert d["status"] == "ok"


def test_search_hit_to_dict():
    from modpack_manager.sources.base import SearchHit
    h = SearchHit(platform="modrinth", id="AAB", slug="sodium", name="Sodium",
                  summary="fast", icon_url="i.png", page_url="https://modrinth.com/mod/sodium")
    d = h.to_dict()
    assert d["platform"] == "modrinth"
    assert d["slug"] == "sodium"
    assert d["page_url"].endswith("/sodium")


def test_added_dependency_new_fields_default_and_roundtrip():
    from modpack_manager.sources.base import Candidate, AddedDependency
    dep = AddedDependency(id="cloth-config", satisfied=False)
    # new fields default to a not-yet-resolved, not-addable spec
    assert dep.slug == ""
    assert dep.side == "BOTH"
    assert dep.version == ""
    assert dep.download_url == ""
    assert dep.size is None
    assert dep.addable is False
    # populated fields survive Candidate.to_dict() (asdict) nesting
    dep2 = AddedDependency(id="create", satisfied=False, name="Create", slug="create",
                           side="CLIENT", version="6.0.6",
                           download_url="https://cdn/create.jar", size=1234, addable=True)
    c = Candidate(mod_id="cbc", name="CBC", platform="modrinth", source_url="u",
                  current_version="1", latest_version="2", severity="minor", side="BOTH",
                  required=True, mod_type="Regular", added_dependencies=[dep2], status="ok")
    d = c.to_dict()["added_dependencies"][0]
    assert d["slug"] == "create"
    assert d["side"] == "CLIENT"
    assert d["version"] == "6.0.6"
    assert d["download_url"] == "https://cdn/create.jar"
    assert d["size"] == 1234
    assert d["addable"] is True


def test_added_dependency_platform_defaults_and_roundtrips():
    from modpack_manager.sources.base import Candidate, AddedDependency
    # defaults to "modrinth" so every existing construction + test is unchanged
    assert AddedDependency(id="cloth-config", satisfied=False).platform == "modrinth"
    # CF deps set it explicitly, and it survives Candidate.to_dict() (asdict) nesting
    dep = AddedDependency(id="306612", satisfied=False, platform="curseforge")
    c = Candidate(mod_id="cbc", name="CBC", platform="curseforge", source_url="u",
                  current_version="1", latest_version="2", severity="minor", side="BOTH",
                  required=True, mod_type="Regular", added_dependencies=[dep], status="ok")
    assert c.to_dict()["added_dependencies"][0]["platform"] == "curseforge"
