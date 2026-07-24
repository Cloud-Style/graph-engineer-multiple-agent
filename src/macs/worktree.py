"""Git worktree helpers for isolated implementer writes."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def ensure_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    if (repo / ".git").exists():
        return
    init = _git(repo, "init")
    if init.returncode != 0:
        raise RuntimeError(init.stderr)
    _git(repo, "config", "user.email", "macs@example.com")
    _git(repo, "config", "user.name", "macs")
    (repo / "README").write_text("fixture\n", encoding="utf-8")
    _git(repo, "add", "README")
    commit = _git(repo, "commit", "-m", "init")
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr)


def create_task_worktree(
    repo: Path,
    *,
    run_id: str,
    task_id: str,
    worktrees_root: Path,
) -> tuple[Path, str]:
    """Create an isolated worktree/branch for one write task."""
    ensure_git_repo(repo)
    worktrees_root.mkdir(parents=True, exist_ok=True)
    branch = f"macs/{run_id}/{task_id}"
    path = worktrees_root / task_id
    if path.exists():
        return path, branch
    # Base branch
    _git(repo, "branch", branch)
    add = _git(repo, "worktree", "add", str(path), branch)
    if add.returncode != 0:
        # retry with checkout -b from HEAD
        add = _git(repo, "worktree", "add", "-b", branch, str(path))
        if add.returncode != 0:
            raise RuntimeError(add.stderr)
    return path, branch


def commit_file(worktree: Path, relative: str, content: str, message: str) -> None:
    target = worktree / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(worktree, "add", relative)
    commit = _git(worktree, "commit", "-m", message)
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr)
