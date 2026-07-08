"""Thin git wrapper for the pipeline's commit step. Shells out to git.exe rather than
using a library, since the pipeline only ever needs add+commit and this keeps the
dependency list smaller and easier to replicate across machines.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_CANDIDATE_PATHS = [
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Program Files\Git\bin\git.exe",
    r"C:\Program Files (x86)\Git\cmd\git.exe",
]


class GitError(Exception):
    pass


def _git_executable() -> str:
    found = shutil.which("git")
    if found:
        return found
    for candidate in _CANDIDATE_PATHS:
        if Path(candidate).exists():
            return candidate
    raise GitError(
        "git executable not found on PATH or in common install locations. "
        "Install Git for Windows and re-run."
    )


def commit_files(repo_root: Path, paths: list[Path], message: str) -> None:
    """Stages the given paths and commits them. No-ops (does not raise) if, after
    staging, there's nothing new to commit — this can legitimately happen on a
    reindex where content didn't actually change.
    """
    git = _git_executable()
    rel_paths = [str(p.relative_to(repo_root)) for p in paths]

    add_result = subprocess.run(
        [git, "-C", str(repo_root), "add", *rel_paths],
        capture_output=True,
        text=True,
    )
    if add_result.returncode != 0:
        raise GitError(f"git add failed: {add_result.stderr.strip()}")

    diff_result = subprocess.run(
        [git, "-C", str(repo_root), "diff", "--cached", "--quiet"]
    )
    if diff_result.returncode == 0:
        return  # nothing staged, nothing to commit

    commit_result = subprocess.run(
        [git, "-C", str(repo_root), "commit", "-m", message],
        capture_output=True,
        text=True,
    )
    if commit_result.returncode != 0:
        raise GitError(f"git commit failed: {commit_result.stderr.strip()}")
