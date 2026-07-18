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
