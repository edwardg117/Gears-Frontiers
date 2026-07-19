"""Data types shared by the update sources."""

from dataclasses import dataclass, field, asdict


@dataclass
class ChangelogEntry:
    version: str
    date: str
    body_html: str


@dataclass
class Notice:
    level: str          # "warn" | "info"
    code: str           # stable id for dedup/dismissal/tests
    message: str        # human text for the banner

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AddedDependency:
    id: str
    satisfied: bool
    name: str | None = None
    url: str = ""               # project page, for the "open" link
    slug: str = ""              # platform slug -> used as the add's module_id
    side: str = "BOTH"          # CLIENT | SERVER | BOTH (detected)
    version: str = ""           # resolved latest compatible version name
    download_url: str = ""      # primary-file jar URL to hash/add
    size: int | None = None     # primary-file size in bytes
    addable: bool = False       # True once resolved to a queueable spec


@dataclass
class Candidate:
    mod_id: str
    name: str
    platform: str
    source_url: str
    current_version: str
    latest_version: str
    severity: str
    side: str
    required: bool
    mod_type: str
    changelogs: list = field(default_factory=list)
    added_dependencies: list = field(default_factory=list)
    status: str = "ok"          # ok | manual | error
    note: str = ""
    latest_size: int | None = None
    project_url: str = ""       # project/mod page, for the "open" link

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchHit:
    platform: str
    id: str
    slug: str
    name: str
    summary: str
    icon_url: str
    page_url: str

    def to_dict(self) -> dict:
        return asdict(self)
