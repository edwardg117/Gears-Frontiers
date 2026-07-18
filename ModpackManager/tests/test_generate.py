import xml.etree.ElementTree as ET

from modpack_manager.xml_model import Module
from modpack_manager.sources.base import Candidate
from modpack_manager import generate

NS = {"m": "http://www.mcupdater.com"}


def _module():
    return Module(mod_id="appleskin", name="AppleSkin",
                  url="https://cdn.modrinth.com/data/E/versions/OLD/appleskin-3.0.5.jar",
                  side="CLIENT", required=True, mod_type="Regular", depends="cloth",
                  mod_path="mods")


def _candidate():
    return Candidate(mod_id="appleskin", name="AppleSkin", platform="modrinth",
                     source_url="https://cdn.modrinth.com/data/E/versions/NEW/appleskin-3.1.0.jar",
                     current_version="3.0.5", latest_version="3.1.0", severity="minor",
                     side="CLIENT", required=True, mod_type="Regular", status="ok",
                     latest_size=1234)


def test_write_update_xml_has_correct_hash_and_preserved_attrs(tmp_path):
    out = tmp_path / "updates-2026-07-17.xml"
    generate.write_update_xml(
        [_candidate()], {"appleskin": _module()}, out, mc_version="1.21.1",
        hashfn=lambda url: ("d41d8cd98f00b204e9800998ecf8427e", 1234))
    root = ET.parse(out).getroot()
    mod = root.find(".//m:Module", NS)
    assert mod.get("id") == "appleskin"
    assert mod.get("side") == "CLIENT"
    assert mod.get("depends") == "cloth"
    assert mod.find("m:MD5", NS).text == "d41d8cd98f00b204e9800998ecf8427e"
    assert mod.find("m:Size", NS).text == "1234"
    assert mod.find("m:ModPath", NS).text == "mods"
    assert mod.find("m:URL", NS).text.endswith("appleskin-3.1.0.jar")
    assert mod.find("m:Meta/m:version", NS).text == "3.1.0"


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
