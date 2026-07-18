from modpack_manager import paths


def test_repo_root_contains_updates_dir():
    root = paths.repo_root()
    assert (root / "updates").is_dir()
    assert (root / "GearsAndFrontiers_Preview.xml").is_file()


def test_pack_paths():
    p = paths.pack_paths()
    assert p.updates_dir.name == "updates"
    assert p.preview_pack.name == "GearsAndFrontiers_Preview.xml"
    assert p.config_ini.name == "mod_update_config.ini"
