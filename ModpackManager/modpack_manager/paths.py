"""Filesystem locations, resolved relative to the repo root."""

from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    # this file: <repo>/ModpackManager/modpack_manager/paths.py
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PackPaths:
    root: Path
    updates_dir: Path
    base_pack: Path
    preview_pack: Path
    main_pack: Path
    config_xml: Path
    config_ini: Path
    cache_dir: Path


def pack_paths() -> PackPaths:
    root = repo_root()
    return PackPaths(
        root=root,
        updates_dir=root / "updates",
        base_pack=root / "updates" / "base.xml",
        preview_pack=root / "GearsAndFrontiers_Preview.xml",
        main_pack=root / "GearsAndFrontiers.xml",
        config_xml=root / "config.xml",
        config_ini=root / "mod_update_config.ini",
        cache_dir=root / "ModpackManager" / "cache",
    )
