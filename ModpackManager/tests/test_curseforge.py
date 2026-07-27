import responses
from modpack_manager.xml_model import Module
from modpack_manager.sources import curseforge
from modpack_manager.sources.curseforge import _clean_version

API = "https://api.curseforge.com/v1"


def test_clean_version_extracts_mod_version_skipping_mc():
    assert _clean_version("AmbientSounds_NEOFORGE_v6.3.8_mc1.21.1.jar", None, "1.21.1") == "6.3.8"
    assert _clean_version("carryon-neoforge-1.21.1-2.2.5.8", None, "1.21.1") == "2.2.5.8"
    assert _clean_version("1.39.8", "Xaeros_1.39.8.jar", "1.21.1") == "1.39.8"


def test_clean_version_keeps_mod_version_that_prefixes_mc():
    # "1.2" is a prefix of "1.21.1" but is a real mod version -> must be kept
    assert _clean_version("mymod-1.2", None, "1.21.1") == "1.2"
    # the MC major.minor form (1.21) is still skipped, real version kept
    assert _clean_version("mymod-1.21-3.4.5", None, "1.21.1") == "3.4.5"


@responses.activate
def test_list_files_paginates_across_pages():
    url = f"{API}/mods/999/files"
    page0 = [{"id": i, "fileDate": "2026-01-01T00:00:00Z"} for i in range(50)]  # full page
    page1 = [{"id": 500, "fileDate": "2025-01-01T00:00:00Z"}]                   # short -> last
    responses.add(responses.GET, url, json={"data": page0}, status=200)
    responses.add(responses.GET, url, json={"data": page1}, status=200)
    files, hit_cap = curseforge._list_files(curseforge._session("CF"), 999, "1.21.1", "neoforge")
    assert len(files) == 51
    assert hit_cap is False
    assert len(responses.calls) == 2


@responses.activate
def test_list_files_reports_cap_when_pages_exhausted():
    url = f"{API}/mods/999/files"
    full = [{"id": i, "fileDate": "2026-01-01T00:00:00Z"} for i in range(50)]
    responses.add(responses.GET, url, json={"data": full}, status=200)
    responses.add(responses.GET, url, json={"data": full}, status=200)
    files, hit_cap = curseforge._list_files(
        curseforge._session("CF"), 999, "1.21.1", "neoforge", max_pages=2)
    assert hit_cap is True          # both pages full -> more may exist beyond the cap
    assert len(files) == 100
    assert len(responses.calls) == 2


def _module(file_id=7568054, version="1.39.4"):
    url = f"https://edge.forgecdn.net/files/7568/054/Xaeros_{version}.jar"
    m = Module(mod_id="xaeroworldmap", name="Xaeros World Map", url=url, version=version)
    return m


def _cf_module(mod_id, g1, g2, version="1.0"):
    url = f"https://edge.forgecdn.net/files/{g1}/{g2}/{mod_id}_{version}.jar"
    return Module(mod_id=mod_id, name=mod_id, url=url, version=version)


def _add_common(latest_download="https://edge.forgecdn.net/files/7600/000/Xaeros_1.39.8.jar",
                allow_dist=True):
    responses.add(responses.POST, f"{API}/mods/files",
                  json={"data": [{"id": 7568054, "modId": 999}]}, status=200)
    responses.add(responses.GET, f"{API}/mods/999",
                  json={"data": {"id": 999, "name": "Xaeros World Map",
                                 "allowModDistribution": allow_dist}}, status=200)
    responses.add(responses.GET, f"{API}/mods/999/files",
                  json={"data": [
                      {"id": 7600000, "displayName": "1.39.8", "fileName": "Xaeros_1.39.8.jar",
                       "fileDate": "2026-07-10T00:00:00Z", "fileLength": 2000,
                       "downloadUrl": latest_download,
                       "gameVersions": ["1.21.1", "NeoForge"]},
                      {"id": 7568054, "displayName": "1.39.4", "fileName": "Xaeros_1.39.4.jar",
                       "fileDate": "2026-06-01T00:00:00Z", "fileLength": 1900,
                       "downloadUrl": "https://edge.forgecdn.net/files/7568/054/Xaeros_1.39.4.jar",
                       "gameVersions": ["1.21.1", "NeoForge"]},
                  ]}, status=200)
    responses.add(responses.GET, f"{API}/mods/999/files/7600000/changelog",
                  json={"data": "<p>Fixed the map</p>"}, status=200)


@responses.activate
def test_build_candidate_happy_path():
    _add_common()
    c = curseforge.build_candidate(_module(), "1.21.1", "neoforge", set(), api_key="CF")
    assert c is not None
    assert c.status == "ok"
    assert c.latest_version == "1.39.8"
    assert c.source_url.endswith("Xaeros_1.39.8.jar")
    assert c.latest_size == 2000
    assert "Fixed the map" in c.changelogs[0].body_html


@responses.activate
def test_distribution_blocked_marks_manual():
    _add_common(latest_download=None, allow_dist=False)
    c = curseforge.build_candidate(_module(), "1.21.1", "neoforge", set(), api_key="CF")
    assert c.status == "manual"
    assert "manual" in c.note.lower()


@responses.activate
def test_missing_api_key_returns_error_candidate():
    c = curseforge.build_candidate(_module(), "1.21.1", "neoforge", set(), api_key="")
    assert c.status == "error"
    assert "api key" in c.note.lower()


@responses.activate
def test_find_updated_mod_ids_bulk_flags_only_changed():
    ma = _cf_module("a", "1000", "001")   # cf_file_id 1000001
    mb = _cf_module("b", "2000", "002")   # cf_file_id 2000002
    responses.add(responses.POST, f"{API}/mods/files", json={"data": [
        {"id": 1000001, "modId": 11},
        {"id": 2000002, "modId": 22},
    ]}, status=200)
    responses.add(responses.POST, f"{API}/mods", json={"data": [
        {"id": 11, "allowModDistribution": True, "links": {"websiteUrl": "http://a"},
         "latestFilesIndexes": [{"gameVersion": "1.21.1", "modLoader": 6, "fileId": 1000999}]},
        {"id": 22, "allowModDistribution": True, "links": {"websiteUrl": "http://b"},
         "latestFilesIndexes": [{"gameVersion": "1.21.1", "modLoader": 6, "fileId": 2000002}]},
    ]}, status=200)
    updated, unresolved, contexts = curseforge.find_updated_mod_ids(
        [ma, mb], "1.21.1", "neoforge", api_key="CF")
    assert updated == {"a"}                      # 11 has a newer fileId; 22 unchanged
    assert unresolved == []
    assert contexts["a"] == {"cf_mod_id": 11, "allow_dist": True, "website": "http://a"}


@responses.activate
def test_find_updated_unresolved_when_no_matching_index():
    ma = _cf_module("a", "1000", "001")
    responses.add(responses.POST, f"{API}/mods/files",
                  json={"data": [{"id": 1000001, "modId": 11}]}, status=200)
    responses.add(responses.POST, f"{API}/mods", json={"data": [
        {"id": 11, "allowModDistribution": True, "links": {},
         "latestFilesIndexes": [{"gameVersion": "1.20.1", "modLoader": 6, "fileId": 999}]},
    ]}, status=200)
    updated, unresolved, contexts = curseforge.find_updated_mod_ids(
        [ma], "1.21.1", "neoforge", api_key="CF")
    assert updated == set()
    assert [m.mod_id for m in unresolved] == ["a"]  # no index for our version -> fallback


def test_find_updated_no_api_key_marks_all_unresolved():
    ma = _cf_module("a", "1000", "001")
    updated, unresolved, contexts = curseforge.find_updated_mod_ids(
        [ma], "1.21.1", "neoforge", api_key="")
    assert updated == set()
    assert [m.mod_id for m in unresolved] == ["a"]
    assert contexts == {}


@responses.activate
def test_build_candidate_with_ctx_skips_recover_and_info():
    # No POST /mods/files and no GET /mods/999 registered — if build_candidate
    # made those (redundant) calls it would error out, so status=="ok" proves
    # the bulk context short-circuited them.
    ma = _cf_module("xaeroworldmap", "7568", "054", version="1.39.4")  # cf_file_id 7568054
    responses.add(responses.GET, f"{API}/mods/999/files", json={"data": [
        {"id": 7600000, "displayName": "1.39.8", "fileName": "x.jar",
         "fileDate": "2026-07-10T00:00:00Z", "fileLength": 2000,
         "downloadUrl": "https://edge.forgecdn.net/files/7600/000/x.jar",
         "gameVersions": ["1.21.1", "NeoForge"]},
        {"id": 7568054, "displayName": "1.39.4", "fileName": "x.jar",
         "fileDate": "2026-06-01T00:00:00Z", "fileLength": 1900, "downloadUrl": "u",
         "gameVersions": ["1.21.1", "NeoForge"]},
    ]}, status=200)
    responses.add(responses.GET, f"{API}/mods/999/files/7600000/changelog",
                  json={"data": "<p>cl</p>"}, status=200)
    ctx = {"cf_mod_id": 999, "allow_dist": True, "website": "http://x"}
    c = curseforge.build_candidate(ma, "1.21.1", "neoforge", set(), api_key="CF", ctx=ctx)
    assert c.status == "ok"
    assert c.latest_version == "1.39.8"
    assert c.project_url == "http://x"


@responses.activate
def test_search_returns_hits():
    responses.add(responses.GET, f"{API}/mods/search", json={"data": [
        {"id": 238222, "slug": "jei", "name": "JEI", "summary": "items",
         "logo": {"url": "https://l/jei.png"}, "links": {"websiteUrl": "https://cf/jei"}},
    ]}, status=200)
    hits = curseforge.search("jei", "1.21.1", "neoforge", api_key="CF")
    assert hits[0].platform == "curseforge"
    assert hits[0].id == "238222"
    assert hits[0].page_url == "https://cf/jei"


def test_search_no_key_returns_empty():
    assert curseforge.search("jei", "1.21.1", "neoforge", api_key="") == []


@responses.activate
def test_resolve_link_via_slug():
    responses.add(responses.GET, f"{API}/mods/search", json={"data": [
        {"id": 238222, "slug": "jei", "name": "JEI", "summary": "items",
         "logo": {"url": "l.png"}, "links": {"websiteUrl": "https://cf/jei"}}]}, status=200)
    hit = curseforge.resolve("https://www.curseforge.com/minecraft/mc-mods/jei", api_key="CF")
    assert hit.id == "238222"
    assert hit.name == "JEI"


@responses.activate
def test_project_versions_maps_release_types_and_skips_blocked():
    responses.add(responses.GET, f"{API}/mods/77/files", json={"data": [
        {"id": 9002, "displayName": "1.2.0", "fileName": "m-1.2.0.jar",
         "fileDate": "2026-07-10T00:00:00Z", "releaseType": 2,
         "downloadUrl": "https://edge/9002/m.jar"},
        {"id": 9001, "displayName": "1.1.0", "fileName": "m-1.1.0.jar",
         "fileDate": "2026-06-01T00:00:00Z", "releaseType": 1, "downloadUrl": None},
    ]}, status=200)
    out = curseforge.project_versions("77", "1.21.1", "neoforge", api_key="CF")
    assert out["side"] == "BOTH"
    assert len(out["versions"]) == 1               # blocked (null url) skipped
    assert out["versions"][0]["type"] == "beta"
    assert out["versions"][0]["ref"] == "9002"


@responses.activate
def test_project_changelog_wraps_file_changelog():
    responses.add(responses.GET, f"{API}/mods/999/files/7600000/changelog",
                  json={"data": "<p>Fixed the map</p>"}, status=200)
    out = curseforge.project_changelog(999, "7600000", api_key="CF")
    assert out["version"] == "" and out["date"] == ""      # CF changelog endpoint has no version/date
    assert "Fixed the map" in out["body_html"]


@responses.activate
def test_project_changelog_non_200_is_empty():
    responses.add(responses.GET, f"{API}/mods/999/files/1/changelog", status=404)
    assert curseforge.project_changelog(999, "1", api_key="CF")["body_html"] == ""


def test_project_changelog_no_key_is_empty():
    assert curseforge.project_changelog(999, "1", api_key="")["body_html"] == ""


@responses.activate
def test_project_changelog_transport_error_is_empty():
    responses.add(responses.GET, f"{API}/mods/999/files/1/changelog", body=ConnectionError("boom"))
    assert curseforge.project_changelog(999, "1", api_key="CF") == {"version": "", "date": "", "body_html": ""}


@responses.activate
def test_resolve_dependencies_happy_path_with_requires():
    # modId 306612 -> latest compatible file 8001 (from latestFilesIndexes);
    # that file itself requires modId 319057 (required) and 999999 (optional).
    responses.add(responses.POST, f"{API}/mods", json={"data": [
        {"id": 306612, "name": "Cloth Config API", "slug": "cloth-config",
         "allowModDistribution": True, "links": {"websiteUrl": "https://cf/cloth"},
         "latestFilesIndexes": [{"gameVersion": "1.21.1", "modLoader": 6, "fileId": 8001}]},
    ]}, status=200)
    responses.add(responses.POST, f"{API}/mods/files", json={"data": [
        {"id": 8001, "displayName": "15.0.140", "fileName": "cloth-15.0.140.jar",
         "fileLength": 512000, "downloadUrl": "https://edge.forgecdn.net/8001/cloth.jar",
         "dependencies": [{"modId": 319057, "relationType": 3},
                          {"modId": 999999, "relationType": 2}]},
    ]}, status=200)
    out = curseforge.resolve_dependencies([306612], "1.21.1", "neoforge", api_key="CF")
    spec = out["306612"]
    assert spec["name"] == "Cloth Config API"
    assert spec["slug"] == "cloth-config"
    assert spec["url"] == "https://cf/cloth"
    assert spec["side"] == "BOTH"
    assert spec["version"] == "15.0.140"
    assert spec["download_url"] == "https://edge.forgecdn.net/8001/cloth.jar"
    assert spec["size"] == 512000
    assert spec["addable"] is True
    assert spec["requires"] == ["319057"]           # required kept, optional dropped, str ids


@responses.activate
def test_resolve_dependencies_blocked_dep_not_addable():
    responses.add(responses.POST, f"{API}/mods", json={"data": [
        {"id": 306612, "name": "Blocked Lib", "slug": "blocked-lib",
         "allowModDistribution": False, "links": {"websiteUrl": "https://cf/blocked"},
         "latestFilesIndexes": [{"gameVersion": "1.21.1", "modLoader": 6, "fileId": 8001}]},
    ]}, status=200)
    responses.add(responses.POST, f"{API}/mods/files", json={"data": [
        {"id": 8001, "displayName": "1.0", "fileName": "blocked-1.0.jar",
         "fileLength": 100, "downloadUrl": None, "dependencies": []},
    ]}, status=200)
    out = curseforge.resolve_dependencies([306612], "1.21.1", "neoforge", api_key="CF")
    spec = out["306612"]
    assert spec["name"] == "Blocked Lib"            # meta still resolved -> name shows in banner
    assert spec["download_url"] == ""
    assert spec["addable"] is False
    assert spec["requires"] == []


def test_resolve_dependencies_no_key_returns_empty():
    assert curseforge.resolve_dependencies([306612], "1.21.1", "neoforge", api_key="") == {}


@responses.activate
def test_resolve_dependencies_no_compatible_file_not_addable():
    # mod meta resolves, but latestFilesIndexes has nothing for our mc_version/loader
    responses.add(responses.POST, f"{API}/mods", json={"data": [
        {"id": 306612, "name": "No Compat Lib", "slug": "no-compat-lib",
         "allowModDistribution": True, "links": {"websiteUrl": "https://cf/nc"},
         "latestFilesIndexes": [{"gameVersion": "1.20.1", "modLoader": 6, "fileId": 8001}]},
    ]}, status=200)
    out = curseforge.resolve_dependencies([306612], "1.21.1", "neoforge", api_key="CF")
    spec = out["306612"]
    assert spec["name"] == "No Compat Lib"     # meta still resolved (name shown in banner)
    assert spec["version"] == ""
    assert spec["download_url"] == ""
    assert spec["addable"] is False
    assert spec["requires"] == []


@responses.activate
def test_build_candidate_detects_new_required_cf_dep():
    responses.add(responses.POST, f"{API}/mods/files",
                  json={"data": [{"id": 7568054, "modId": 999}]}, status=200)
    responses.add(responses.GET, f"{API}/mods/999",
                  json={"data": {"id": 999, "name": "Xaeros World Map",
                                 "allowModDistribution": True}}, status=200)
    responses.add(responses.GET, f"{API}/mods/999/files", json={"data": [
        {"id": 7600000, "displayName": "1.39.8", "fileName": "Xaeros_1.39.8.jar",
         "fileDate": "2026-07-10T00:00:00Z", "fileLength": 2000,
         "downloadUrl": "https://edge.forgecdn.net/files/7600/000/Xaeros_1.39.8.jar",
         "dependencies": [
             {"modId": 306612, "relationType": 3},   # required, not installed -> collected
             {"modId": 555, "relationType": 3},       # required, but installed -> skipped
             {"modId": 777, "relationType": 2}],      # optional -> ignored
         "gameVersions": ["1.21.1", "NeoForge"]},
        {"id": 7568054, "displayName": "1.39.4", "fileName": "Xaeros_1.39.4.jar",
         "fileDate": "2026-06-01T00:00:00Z", "fileLength": 1900,
         "downloadUrl": "https://edge.forgecdn.net/files/7568/054/Xaeros_1.39.4.jar",
         "gameVersions": ["1.21.1", "NeoForge"]},
    ]}, status=200)
    responses.add(responses.GET, f"{API}/mods/999/files/7600000/changelog",
                  json={"data": "<p>cl</p>"}, status=200)
    # 4th positional arg is now the installed-CF-modId set
    c = curseforge.build_candidate(_module(), "1.21.1", "neoforge", {555}, api_key="CF")
    deps = c.added_dependencies
    assert [d.id for d in deps] == ["306612"]
    assert deps[0].platform == "curseforge"
    assert deps[0].satisfied is False
