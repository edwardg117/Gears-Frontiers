"""Read the existing mod_update_config.ini."""

import configparser
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    curseforge_api_key: str = ""
    modrinth_api_key: str = ""
    mc_version: str = "1.21.1"
    loader: str = "neoforge"
    excluded_mods: set = field(default_factory=set)


def load_config(ini_path: Path) -> Config:
    parser = configparser.ConfigParser()
    if Path(ini_path).exists():
        parser.read(ini_path, encoding="utf-8")

    def get(section, key, fallback=""):
        return parser.get(section, key, fallback=fallback).strip()

    excluded = get("MODPACK", "excluded_mods")
    return Config(
        curseforge_api_key=get("API", "curseforge_api_key"),
        modrinth_api_key=get("API", "modrinth_api_key"),
        mc_version=get("MODPACK", "target_minecraft_version", "1.21.1") or "1.21.1",
        loader=get("MODPACK", "target_loader", "neoforge") or "neoforge",
        excluded_mods={m.strip() for m in excluded.split(",") if m.strip()},
    )
