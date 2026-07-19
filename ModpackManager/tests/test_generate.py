import xml.etree.ElementTree as ET

from modpack_manager import generate

NS = {"m": "http://www.mcupdater.com"}


def test_write_batch_xml_regular_and_removal(tmp_path):
    out = tmp_path / "updates-2026-07-18.xml"
    entries = [
        {"kind": "regular", "op": "add", "name": "Sodium", "id": "sodium",
         "side": "CLIENT", "required": True, "mod_type": "Regular", "depends": "",
         "mod_path": None, "url": "https://cdn/sodium-0.5.8.jar",
         "md5": "d41d8cd98f00b204e9800998ecf8427e", "size": 1234, "version": "0.5.8"},
        {"kind": "removal", "name": "Farsight", "id": "farsight", "side": "BOTH",
         "size": 100, "required": False},
    ]
    summary = generate.write_batch_xml(entries, out, mc_version="1.21.1")
    root = ET.parse(out).getroot()
    mods = root.findall(".//m:Module", NS)
    assert {m.get("id") for m in mods} == {"sodium", "farsight"}
    sod = root.find(".//m:Module[@id='sodium']", NS)
    assert sod.get("side") == "CLIENT"
    assert sod.find("m:MD5", NS).text == "d41d8cd98f00b204e9800998ecf8427e"
    assert sod.find("m:Size", NS).text == "1234"
    assert sod.find("m:Meta/m:version", NS).text == "0.5.8"
    far = root.find(".//m:Module[@id='farsight']", NS)
    assert far.find("m:ModType", NS).text == "Removal"
    assert far.find("m:URL", NS) is None                # removal has no URL
    assert far.find("m:Size", NS).text == "100"         # proven removal format keeps Size
    assert far.find("m:Required", NS).text == "false"
    assert [s["id"] for s in summary] == ["sodium", "farsight"]


PREVIEW = """<?xml version="1.0" encoding="UTF-8"?>
<ServerPack version="4.1" xmlns="http://www.mcupdater.com">
\t<Server id="Preview" name="Preview" version="1.21.1" revision="4">
\t\t<Import url="https://x/base.xml">base</Import>
\t\t<Loader type="NeoForge" version="21.1.220" loadOrder="0"/>
\t</Server>
</ServerPack>
"""


def test_wire_into_preview_adds_import_and_bumps_revision(tmp_path):
    p = tmp_path / "Preview.xml"
    p.write_text(PREVIEW, encoding="utf-8")
    rev = generate.wire_into_preview(p, "https://x/updates/updates-2026-07-17.xml")
    text = p.read_text(encoding="utf-8")
    assert rev == "5"
    assert 'revision="5"' in text
    assert text.index("updates-2026-07-17.xml") < text.index("<Loader")
    assert text.count("updates-2026-07-17.xml") == 1


def test_wire_into_preview_is_idempotent(tmp_path):
    p = tmp_path / "Preview.xml"
    p.write_text(PREVIEW, encoding="utf-8")
    generate.wire_into_preview(p, "https://x/updates/updates-2026-07-17.xml")
    generate.wire_into_preview(p, "https://x/updates/updates-2026-07-17.xml")
    text = p.read_text(encoding="utf-8")
    assert text.count("updates-2026-07-17.xml") == 1  # not duplicated
    assert 'revision="6"' in text                      # revision still bumps


def _regular(**over):
    e = {"kind": "regular", "op": "add", "name": "Sodium", "id": "sodium",
         "side": "BOTH", "required": True, "mod_type": "Regular", "depends": "",
         "mod_path": None, "url": "https://cdn/s.jar",
         "md5": "d41d8cd98f00b204e9800998ecf8427e", "size": 1, "version": "1"}
    e.update(over)
    return e


def _server(out):
    return ET.parse(out).getroot().find(".//m:Server", NS)


def test_launch_attrs_neoforge_unchanged(tmp_path):
    out = tmp_path / "u.xml"
    generate.write_batch_xml([_regular()], out, "1.21.1", loader="neoforge")
    s = _server(out)
    assert s.get("mainClass") == "cpw.mods.bootstraplauncher.BootstrapLauncher"
    assert s.get("launcherType") == "Vanilla"


def test_launch_attrs_unknown_loader_falls_back_to_neoforge(tmp_path):
    out = tmp_path / "u.xml"
    generate.write_batch_xml([_regular()], out, "1.21.1", loader="fabric")  # unmapped -> default
    assert _server(out).get("mainClass") == "cpw.mods.bootstraplauncher.BootstrapLauncher"
