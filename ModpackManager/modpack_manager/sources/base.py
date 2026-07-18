"""Data types shared by the update sources."""

from dataclasses import dataclass, field, asdict


@dataclass
class ChangelogEntry:
    version: str
    date: str
    body_html: str


@dataclass
class AddedDependency:
    id: str
    satisfied: bool
    name: str | None = None
    url: str = ""               # project page, for the "open" link


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
