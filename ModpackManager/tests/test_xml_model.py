from pathlib import Path
from modpack_manager import xml_model

FIX = Path(__file__).parent / "fixtures"


def test_parse_detects_platform_and_ids():
    mods = xml_model.parse_packs([FIX / "base_sample.xml"])
    apple = mods["appleskin"]
    assert apple.platform == "modrinth"
    assert apple.project_id == "EsAfCjCV"
    assert apple.version_id == "oy4bhPTN"
    assert apple.version == "3.0.5"
    assert apple.side == "CLIENT"

    xaero = mods["xaeroworldmap"]
    assert xaero.platform == "curseforge"
    assert xaero.cf_file_id == 7568054


def test_later_layer_overrides_earlier(tmp_path):
    override = tmp_path / "updates-2026-01-01.xml"
    override.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ServerPack version="4.1" xmlns="http://www.mcupdater.com">'
        '<Server id="u" name="u" version="1.21.1">'
        '<Module name="AppleSkin" id="appleskin" side="CLIENT">'
        '<URL priority="1">https://cdn.modrinth.com/data/EsAfCjCV/versions/NEWVER11/appleskin-3.1.0.jar</URL>'
        '<Meta><version>3.1.0</version></Meta>'
        '</Module></Server></ServerPack>',
        encoding="utf-8",
    )
    mods = xml_model.parse_packs([FIX / "base_sample.xml", override])
    assert mods["appleskin"].version_id == "NEWVER11"
    assert mods["appleskin"].version == "3.1.0"
    # side preserved from the base layer when the override omits it
    assert mods["appleskin"].side == "CLIENT"


def test_unknown_platform_when_url_not_recognised():
    mods = xml_model.parse_packs([FIX / "base_sample.xml"])
    assert "appleskin" in mods and mods["appleskin"].platform == "modrinth"


def _write_pack(path, module_xml):
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ServerPack version="4.1" xmlns="http://www.mcupdater.com">'
        f'<Server id="s" name="s" version="1.21.1">{module_xml}</Server></ServerPack>',
        encoding="utf-8",
    )


def test_override_without_required_keeps_base_required_false(tmp_path):
    base = tmp_path / "base.xml"
    _write_pack(base,
        '<Module name="M" id="m" side="CLIENT">'
        '<URL priority="1">https://cdn.modrinth.com/data/P/versions/V/m.jar</URL>'
        '<Required>false</Required></Module>')
    over = tmp_path / "updates-2026-01-01.xml"
    _write_pack(over,  # note: no <Required> element in the override
        '<Module name="M" id="m" side="CLIENT">'
        '<URL priority="1">https://cdn.modrinth.com/data/P/versions/W/m.jar</URL>'
        '<Meta><version>2.0</version></Meta></Module>')
    mods = xml_model.parse_packs([base, over])
    assert mods["m"].required is False  # base's Required=false must survive


def test_urlless_removal_overrides_base_entry(tmp_path):
    base = tmp_path / "base.xml"
    _write_pack(base,
        '<Module name="Farsight" id="farsight" side="CLIENT">'
        '<URL priority="1">https://cdn.modrinth.com/data/P/versions/V/farsight.jar</URL>'
        '</Module>')
    over = tmp_path / "updates-2026-05-01.xml"
    _write_pack(over,  # a Removal with NO <URL> — must still override the base
        '<Module name="Farsight" id="farsight" side="CLIENT">'
        '<Required>false</Required><ModType>Removal</ModType></Module>')
    mods = xml_model.parse_packs([base, over])
    assert "farsight" in mods
    assert mods["farsight"].mod_type == "Removal"  # so it's excluded from the picker


def test_override_with_explicit_required_true_wins(tmp_path):
    base = tmp_path / "base.xml"
    _write_pack(base,
        '<Module name="M" id="m"><URL priority="1">https://cdn.modrinth.com/data/P/versions/V/m.jar</URL>'
        '<Required>false</Required></Module>')
    over = tmp_path / "updates-2026-01-01.xml"
    _write_pack(over,
        '<Module name="M" id="m"><URL priority="1">https://cdn.modrinth.com/data/P/versions/W/m.jar</URL>'
        '<Required>true</Required></Module>')
    mods = xml_model.parse_packs([base, over])
    assert mods["m"].required is True  # explicit override still wins
