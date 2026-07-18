from modpack_manager.version_utils import classify_severity


def test_major_minor_patch():
    assert classify_severity("1.2.3", "2.0.0") == "major"
    assert classify_severity("1.2.3", "1.3.0") == "minor"
    assert classify_severity("1.2.3", "1.2.4") == "patch"


def test_unparseable_returns_unknown():
    assert classify_severity("weird-a", "weird-b") == "unknown"


def test_prefixed_versions_are_tolerated():
    assert classify_severity("mc1.21-2.0.0", "mc1.21-2.1.0") == "minor"
