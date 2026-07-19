"""Path-scoped git operations for the diff / commit / discard flow.

Every function takes an explicit list of repo-relative paths and NEVER runs a
broad ``git add -A`` / ``git add .`` — staging is provably limited to the paths
handed in, so the maintainer's unrelated working-tree changes are never touched.
"""

import subprocess
from pathlib import Path

_COMMIT_TIMEOUT = 120  # seconds — generous, to allow a YubiKey touch


def _run(root, args, timeout=30, check=True):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=check)


def _is_untracked(root, path) -> bool:
    out = _run(root, ["status", "--porcelain", "--", path]).stdout
    return out.startswith("??")


def diff(root, paths) -> str:
    """Unified diff of ``paths``. Read-only: mutates no git state, so closing the
    result modal without acting leaves the tree exactly as generate left it.
    An untracked new file is diffed against /dev/null (git special-cases it
    cross-platform and exits 1 when there are differences — expected, not an error)."""
    parts = []
    for p in paths:
        if _is_untracked(root, p):
            r = _run(root, ["diff", "--no-index", "--", "/dev/null", p], check=False)
        else:
            r = _run(root, ["diff", "--", p], check=False)
        if r.stdout:
            parts.append(r.stdout)
    return "\n".join(parts)


def commit(root, paths, message) -> dict:
    """Stage and commit exactly ``paths``. The commit pathspec excludes any other
    pre-staged changes. Signing (YubiKey) happens inside ``git commit``; a timeout
    leaves the files staged so nothing is lost."""
    try:
        _run(root, ["add", "--", *paths])
        _run(root, ["commit", "-m", message, "--", *paths], timeout=_COMMIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "timeout": True,
                "error": "Key touch timed out — the files are staged; retry or commit from a terminal."}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": (e.stderr or e.stdout or str(e)).strip()}
    sha = _run(root, ["rev-parse", "--short", "HEAD"]).stdout.strip()
    return {"ok": True, "sha": sha}


def discard(root, paths) -> dict:
    """Revert exactly ``paths``: a modified tracked file is restored to HEAD; a
    newly-created (untracked) file is deleted."""
    try:
        for p in paths:
            if _is_untracked(root, p):
                (Path(root) / p).unlink(missing_ok=True)
            else:
                _run(root, ["restore", "--", p])
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": (e.stderr or e.stdout or str(e)).strip()}
    return {"ok": True}
