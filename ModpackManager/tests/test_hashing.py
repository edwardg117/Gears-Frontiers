import hashlib
import responses
from modpack_manager import hashing

URL = "https://cdn.modrinth.com/data/x/versions/y/mod.jar"
BLOB = b"pretend jar bytes" * 100


@responses.activate
def test_compute_md5_and_size(tmp_path):
    responses.add(responses.GET, URL, body=BLOB, status=200)
    cache = hashing.HashCache(tmp_path / "hashes.json")
    md5, size = hashing.compute(URL, cache=cache)
    assert md5 == hashlib.md5(BLOB).hexdigest()
    assert size == len(BLOB)


@responses.activate
def test_cache_hit_avoids_second_request(tmp_path):
    responses.add(responses.GET, URL, body=BLOB, status=200)
    cache = hashing.HashCache(tmp_path / "hashes.json")
    hashing.compute(URL, cache=cache)
    # second call must not hit the network (only one registered response, one call)
    md5, size = hashing.compute(URL, cache=cache)
    assert len(responses.calls) == 1
    assert md5 == hashlib.md5(BLOB).hexdigest()


def test_cache_persists_to_disk(tmp_path):
    path = tmp_path / "hashes.json"
    cache = hashing.HashCache(path)
    cache.set(URL, "deadbeef", 10)
    reloaded = hashing.HashCache(path)
    assert reloaded.get(URL) == ("deadbeef", 10)
