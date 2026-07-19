import subprocess
import pytest

from modpack_manager import git_ops


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """A temp git repo with a committed preview file and an unrelated tracked file.
    Signing is disabled so tests never block on a key."""
    root = tmp_path
    _git(root, "init")
    _git(root, "config", "user.email", "t@t.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "GearsAndFrontiers_Preview.xml").write_text('<Server revision="1"/>\n', encoding="utf-8")
    (root / "unrelated.txt").write_text("original\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "baseline")
    return root


def _make_generated(repo):
    """Simulate what generate wrote: a new update file + a modified preview,
    plus an unrelated dirty file that must never be committed."""
    (repo / "updates").mkdir(exist_ok=True)
    (repo / "updates" / "u.xml").write_text("<newfile/>\n", encoding="utf-8")
    (repo / "GearsAndFrontiers_Preview.xml").write_text('<Server revision="2"/>\n', encoding="utf-8")
    (repo / "unrelated.txt").write_text("now dirty\n", encoding="utf-8")
    return ["updates/u.xml", "GearsAndFrontiers_Preview.xml"]


def test_commit_includes_only_named_paths(repo):
    paths = _make_generated(repo)
    res = git_ops.commit(repo, paths, "chore: test")
    assert res["ok"] is True and res["sha"]

    committed = subprocess.run(
        ["git", "-C", str(repo), "show", "--name-only", "--pretty=format:", "HEAD"],
        capture_output=True, text=True, check=True).stdout.split()
    assert set(committed) == {"updates/u.xml", "GearsAndFrontiers_Preview.xml"}

    # the unrelated file was never staged/committed — still dirty
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "unrelated.txt"],
                            capture_output=True, text=True, check=True).stdout
    assert "unrelated.txt" in status


def test_discard_reverts_new_and_modified(repo):
    paths = _make_generated(repo)
    res = git_ops.discard(repo, paths)
    assert res["ok"] is True
    assert not (repo / "updates" / "u.xml").exists()          # new file deleted
    assert (repo / "GearsAndFrontiers_Preview.xml").read_text(encoding="utf-8") == '<Server revision="1"/>\n'
    # unrelated dirty file left untouched
    assert (repo / "unrelated.txt").read_text(encoding="utf-8") == "now dirty\n"


def test_diff_is_readonly_and_shows_both(repo):
    paths = _make_generated(repo)
    out = git_ops.diff(repo, paths)
    assert "newfile" in out            # from the untracked --no-index diff
    assert 'revision="2"' in out       # from the tracked diff
    # read-only: the new file is still untracked after diff
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "updates/u.xml"],
                            capture_output=True, text=True, check=True).stdout
    assert status.startswith("??")


def test_commit_timeout_returns_flag(repo, monkeypatch):
    real_run = git_ops._run

    def fake_run(root, args, timeout=30, check=True):
        if args and args[0] == "commit":
            raise subprocess.TimeoutExpired(cmd="git commit", timeout=timeout)
        return real_run(root, args, timeout=timeout, check=check)

    monkeypatch.setattr(git_ops, "_run", fake_run)
    paths = _make_generated(repo)
    res = git_ops.commit(repo, paths, "chore: test")
    assert res["ok"] is False and res["timeout"] is True


def test_commit_excludes_prestaged_unrelated(repo):
    paths = _make_generated(repo)
    _git(repo, "add", "unrelated.txt")            # maintainer pre-stages unrelated WIP
    res = git_ops.commit(repo, paths, "chore: test")
    assert res["ok"] is True
    committed = subprocess.run(
        ["git", "-C", str(repo), "show", "--name-only", "--pretty=format:", "HEAD"],
        capture_output=True, text=True, check=True).stdout.split()
    assert "unrelated.txt" not in committed
    # still staged, not committed, not lost
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "unrelated.txt"],
                            capture_output=True, text=True, check=True).stdout
    assert status.startswith("M ")                 # staged M in column 1


def test_diff_is_best_effort_on_git_error(tmp_path):
    # tmp_path is NOT a git repo -> git commands fail, but diff must not raise
    assert git_ops.diff(tmp_path, ["anything.xml"]) == ""
