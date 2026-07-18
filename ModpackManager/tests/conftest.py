import textwrap
import pytest


@pytest.fixture
def ini_file(tmp_path):
    def _write(body: str):
        p = tmp_path / "mod_update_config.ini"
        p.write_text(textwrap.dedent(body), encoding="utf-8")
        return p
    return _write
