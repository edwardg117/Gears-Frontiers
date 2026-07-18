"""Parse MCUpdater ServerPack XML and merge layered packs into current state."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

NS = {"m": "http://www.mcupdater.com"}
_MODRINTH = re.compile(r"cdn\.modrinth\.com/data/([^/]+)/versions/([^/]+)/")
_FORGE = re.compile(r"edge\.forgecdn\.net/files/(\d+)/(\d+)/")


@dataclass
class Module:
    mod_id: str
    name: str
    url: str
    side: str = "BOTH"
    required: bool = True
    required_set: bool = True  # was <Required> explicitly present in the XML?
    mod_type: str = "Regular"
    depends: str = ""
    mod_path: str | None = None
    size: int | None = None
    md5: str | None = None
    version: str | None = None
    source_file: str = ""
    platform: str = "unknown"
    project_id: str | None = None
    version_id: str | None = None
    cf_file_id: int | None = None

    def __post_init__(self):
        if "cdn.modrinth.com" in self.url:
            self.platform = "modrinth"
            m = _MODRINTH.search(self.url)
            if m:
                self.project_id, self.version_id = m.group(1), m.group(2)
        elif "forgecdn.net" in self.url:
            self.platform = "curseforge"
            m = _FORGE.search(self.url)
            if m:
                self.cf_file_id = int(f"{m.group(1)}{m.group(2)}")


def _text(module: ET.Element, tag: str) -> str | None:
    el = module.find(f"m:{tag}", NS)
    if el is None:
        el = module.find(tag)
    return el.text.strip() if el is not None and el.text else None


def _parse_module(el: ET.Element, source_file: str) -> Module | None:
    url = _text(el, "URL")
    if not url:
        return None
    meta = el.find("m:Meta", NS)
    if meta is None:
        meta = el.find("Meta")
    version = None
    if meta is not None:
        vel = meta.find("m:version", NS)
        if vel is None:
            vel = meta.find("version")
        version = vel.text.strip() if vel is not None and vel.text else None
    size = _text(el, "Size")
    req_text = _text(el, "Required")
    return Module(
        mod_id=el.get("id", "unknown"),
        name=el.get("name", "unknown"),
        url=url,
        side=el.get("side", "BOTH"),
        required=(req_text or "true").lower() == "true",
        required_set=req_text is not None,
        mod_type=_text(el, "ModType") or "Regular",
        depends=el.get("depends", ""),
        mod_path=_text(el, "ModPath"),
        size=int(size) if size and size.isdigit() else None,
        md5=_text(el, "MD5"),
        version=version,
        source_file=source_file,
    )


def _merge(base: Module, override: Module) -> Module:
    """Override wins for present fields; base fills what the override omits."""
    return Module(
        mod_id=override.mod_id,
        name=override.name or base.name,
        url=override.url,
        side=override.side if override.side != "BOTH" else base.side,
        required=override.required if override.required_set else base.required,
        required_set=override.required_set or base.required_set,
        mod_type=override.mod_type,
        depends=override.depends or base.depends,
        mod_path=override.mod_path or base.mod_path,
        size=override.size,
        md5=override.md5,
        version=override.version or base.version,
        source_file=override.source_file,
    )


def parse_pack_file(path: Path) -> dict[str, Module]:
    tree = ET.parse(path)
    root = tree.getroot()
    modules = root.findall(".//m:Module", NS) or root.findall(".//Module")
    out: dict[str, Module] = {}
    for el in modules:
        mod = _parse_module(el, Path(path).name)
        if mod:
            out[mod.mod_id] = mod
    return out


def parse_packs(paths: list[Path]) -> dict[str, Module]:
    merged: dict[str, Module] = {}
    for path in paths:
        if not Path(path).exists():
            continue
        for mod_id, mod in parse_pack_file(path).items():
            if mod_id in merged:
                merged[mod_id] = _merge(merged[mod_id], mod)
            else:
                merged[mod_id] = mod
    return merged
