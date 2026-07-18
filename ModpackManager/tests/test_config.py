from modpack_manager.config import load_config


def test_load_config_reads_keys_and_target(ini_file):
    p = ini_file("""
        [API]
        curseforge_api_key = CF-KEY
        modrinth_api_key =

        [MODPACK]
        target_minecraft_version = 1.21.1
        target_loader = neoforge
        excluded_mods = foo, bar
    """)
    cfg = load_config(p)
    assert cfg.curseforge_api_key == "CF-KEY"
    assert cfg.modrinth_api_key == ""
    assert cfg.mc_version == "1.21.1"
    assert cfg.loader == "neoforge"
    assert cfg.excluded_mods == {"foo", "bar"}


def test_load_config_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "does_not_exist.ini")
    assert cfg.mc_version == "1.21.1"
    assert cfg.loader == "neoforge"
    assert cfg.excluded_mods == set()
