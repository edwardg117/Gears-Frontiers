"""Write the filtered update XML and wire it into the Preview pack."""

import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

MCU_NS = "http://www.mcupdater.com"


def _sub(parent, tag, text=None):
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def write_update_xml(selected, modules, out_path, mc_version, hashfn):
    """selected: list[Candidate]; modules: dict[id,Module]; hashfn(url)->(md5,size)."""
    ET.register_namespace("", MCU_NS)
    root = ET.Element(f"{{{MCU_NS}}}ServerPack", {"version": "4.1"})
    today = date.today().isoformat()
    server = ET.SubElement(root, f"{{{MCU_NS}}}Server", {
        "id": f"update-{today}", "abstract": "false", "name": f"Update {today}",
        "newsUrl": "about:blank", "version": mc_version, "generateList": "true",
        "autoConnect": "false", "revision": "",
        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher", "launcherType": "Vanilla",
    })
    summary = []
    for cand in selected:
        module = modules[cand.mod_id]
        md5, size = hashfn(cand.source_url)
        module_el = ET.SubElement(server, f"{{{MCU_NS}}}Module", {
            "name": cand.name, "id": cand.mod_id,
            "depends": module.depends or "", "side": cand.side,
        })
        url_el = _sub(module_el, f"{{{MCU_NS}}}URL", cand.source_url)
        url_el.set("priority", "1")
        if module.mod_path:
            _sub(module_el, f"{{{MCU_NS}}}ModPath", module.mod_path)
        _sub(module_el, f"{{{MCU_NS}}}Size", size)
        _sub(module_el, f"{{{MCU_NS}}}Required", "true" if cand.required else "false")
        _sub(module_el, f"{{{MCU_NS}}}ModType", cand.mod_type or "Regular")
        _sub(module_el, f"{{{MCU_NS}}}MD5", md5)
        meta = ET.SubElement(module_el, f"{{{MCU_NS}}}Meta")
        _sub(meta, f"{{{MCU_NS}}}version", cand.latest_version)
        summary.append({"id": cand.mod_id, "md5": md5, "size": size, "ok": True})

    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return summary


def _bump_revision(rev: str) -> str:
    m = re.search(r"(\d+)(?!.*\d)", rev)  # last integer run
    if not m:
        return "1"
    return rev[:m.start()] + str(int(m.group(1)) + 1) + rev[m.end():]


def wire_into_preview(preview_path, import_url) -> str:
    """Add <Import>import_url</Import> before <Loader> (if absent) and bump revision."""
    path = Path(preview_path)
    text = path.read_text(encoding="utf-8")

    # bump revision on the <Server ...> element
    def _rev(match):
        return f'revision="{_bump_revision(match.group(1))}"'
    text, _ = re.subn(r'revision="([^"]*)"', _rev, text, count=1)
    new_rev = re.search(r'revision="([^"]*)"', text).group(1)

    # add the import once, indented, immediately before <Loader
    if import_url not in text:
        loader_match = re.search(r'([ \t]*)<Loader', text)
        indent = loader_match.group(1) if loader_match else "\t\t"
        import_line = f'{indent}<Import url="{import_url}">null</Import>\n'
        text = text[:loader_match.start()] + import_line + text[loader_match.start():]

    path.write_text(text, encoding="utf-8")
    return new_rev
