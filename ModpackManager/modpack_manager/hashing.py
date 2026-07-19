"""Download a jar and compute its MD5 + byte size, with an on-disk cache."""

import hashlib
import json
from pathlib import Path

from .sources import http


def _download_session():
    return http.build_session()


class HashCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self._data = {}

    def get(self, url: str):
        entry = self._data.get(url)
        return (entry["md5"], entry["size"]) if entry else None

    def set(self, url: str, md5: str, size: int):
        self._data[url] = {"md5": md5, "size": size}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")


def compute(url: str, session=None, cache: HashCache | None = None) -> tuple[str, int]:
    if cache is not None:
        hit = cache.get(url)
        if hit:
            return hit
    session = session or _download_session()
    md5 = hashlib.md5()
    size = 0
    with session.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=65536):
            md5.update(chunk)
            size += len(chunk)
    result = (md5.hexdigest(), size)
    if cache is not None:
        cache.set(url, result[0], result[1])
    return result
