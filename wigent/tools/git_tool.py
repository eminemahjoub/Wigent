# ════════════════════════════════════════
# wigent — Git Tool
# Role: Full git integration — status, diff, log, branches, staging,
#        commit (with approval), blame, stash, file history
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Complete git integration for the wigent agent.

Uses GitPython for reliable programmatic git operations.  All
destructive actions (commit, reset, branch delete, stash drop) require
an explicit ``approved=True`` flag — the agent must first show a
preview and get user confirmation.

Every function returns structured dicts — never raw strings."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wigent.tools._safe_path import resolve_path

logger = logging.getLogger(__name__)


# ── data types ────────────────────────────────────────────────────────────


@dataclass
class StatusEntry:
    file: str
    x: str  # staged status char (M/A/D/R/C/ ?)
    y: str  # unstaged status char
    status: str  # human-readable: "modified", "added", "deleted", "renamed", "untracked", "conflict"
    old_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiffLine:
    type: str  # "added" | "deleted" | "context" | "header"
    content: str
    old_line: int | None = None
    new_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiffFile:
    path: str
    added_lines: int = 0
    deleted_lines: int = 0
    hunks: list[list[DiffLine]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "added_lines": self.added_lines,
            "deleted_lines": self.deleted_lines,
            "hunks": [[h.to_dict() for h in hunk] for hunk in self.hunks],
        }


@dataclass
class CommitInfo:
    hexsha: str
    short_sha: str
    author_name: str
    author_email: str
    authored_at: str  # ISO-8601
    committer_name: str
    committer_email: str
    committed_at: str
    message: str
    summary: str
    files_changed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BlameLine:
    line: int
    content: str
    hexsha: str
    author_name: str
    author_email: str
    authored_at: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StashInfo:
    index: int
    message: str
    hexsha: str
    short_sha: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── helpers ───────────────────────────────────────────────────────────────


def _get_repo(path: str = "."):
    """Return a ``git.Repo`` for the given path.

    Raises ``ValueError`` if the path is outside the workspace or
    not a git repository.
    """
    resolved, err = resolve_path(path, require_existing=True)
    if err:
        raise ValueError(err)
    try:
        import git
        repo = git.Repo(resolved, search_parent_directories=True)
    except git.exc.InvalidGitRepositoryError:
        raise ValueError(f"Not a git repository: {resolved}")
    except Exception as exc:
        raise ValueError(f"Failed to open git repo: {exc}")
    return repo


def _dt_to_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _status_char(c: str) -> str:
    mapping = {
        " ": "",
        "M": "modified",
        "A": "added",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "U": "conflict",
        "?": "untracked",
        "!": "ignored",
    }
    return mapping.get(c, c)


def _short_stats(stats) -> dict[str, Any]:
    return {
        "files_changed": stats.total.get("files", 0) if hasattr(stats, "total") else 0,
        "insertions": stats.total.get("insertions", 0) if hasattr(stats, "total") else 0,
        "deletions": stats.total.get("deletions", 0) if hasattr(stats, "total") else 0,
    }


def _preview_staged(repo) -> dict[str, Any]:
    """Build a preview of what would be committed."""
    diff_preview = get_diff(path=repo.working_dir, staged=True)
    staged = get_status(path=repo.working_dir)
    staged_count = sum(1 for e in staged.get("entries", []) if e["x"] not in ("", "?"))
    return {
        "staged_files_count": staged_count,
        "staged_entries": [e for e in staged.get("entries", []) if e["x"] not in ("", "?")],
        "diff_files": diff_preview.get("files", []),
        "diff_insertions": diff_preview.get("insertions", 0),
        "diff_deletions": diff_preview.get("deletions", 0),
    }


# ── check_is_git_repo ────────────────────────────────────────────────────


def check_is_git_repo(path: str = ".") -> dict[str, Any]:
    """Check whether a directory is inside a git repository.

    Returns ``True`` even if the repo root is a parent directory.
    """
    resolved, err = resolve_path(path, require_existing=True)
    if err:
        return {"success": False, "is_git_repo": False, "error": err}
    try:
        import git
        repo = git.Repo(resolved, search_parent_directories=True)
        result = not repo.bare
        repo.close()
        return {"success": True, "is_git_repo": result, "git_dir": repo.git_dir, "working_dir": repo.working_dir, "error": None}
    except (git.exc.InvalidGitRepositoryError, Exception) as exc:
        return {"success": True, "is_git_repo": False, "error": None, "detail": str(exc)}


# ── get_repo_root ─────────────────────────────────────────────────────────


def get_repo_root(path: str = ".") -> dict[str, Any]:
    """Find the root directory of the git repository containing *path*."""
    resolved, err = resolve_path(path, require_existing=True)
    if err:
        return {"success": False, "error": err, "root": None}
    try:
        import git
        repo = git.Repo(resolved, search_parent_directories=True)
        root = repo.working_dir
        repo.close()
        return {"success": True, "root": root, "error": None}
    except (git.exc.InvalidGitRepositoryError, Exception) as exc:
        return {"success": False, "error": f"Not a git repository: {exc}", "root": None}


# ── get_status ────────────────────────────────────────────────────────────


def get_status(path: str = ".") -> dict[str, Any]:
    """Return the working tree status.

    Returns a list of ``StatusEntry`` objects with staged and unstaged
    status characters.
    """
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "entries": [], "count": 0, "error": str(exc)}

    entries: list[StatusEntry] = []
    try:
        # Untracked files
        untracked = repo.untracked_files

        # Index / working tree diffs
        diff_staged = repo.index.diff(repo.head.commit) if repo.head.is_valid() else []
        diff_unstaged = repo.index.diff(None)

        tracked_files: set[str] = set()

        for d in diff_staged:
            file_path = d.a_path if d.change_type in ("D",) else d.b_path
            tracked_files.add(file_path)
            old_path = d.a_path if d.change_type == "R" else None
            entries.append(StatusEntry(
                file=file_path,
                x=d.change_type,
                y="",
                status=_status_char(d.change_type),
                old_path=old_path,
            ))

        for d in diff_unstaged:
            file_path = d.a_path if d.change_type in ("D",) else d.b_path
            tracked_files.add(file_path)
            existing = next((e for e in entries if e.file == file_path), None)
            if existing:
                existing.y = d.change_type
                if not _is_staged(d.change_type):
                    existing.x = ""
                existing.status = _status_char(d.change_type)
            else:
                entries.append(StatusEntry(
                    file=file_path,
                    x="",
                    y=d.change_type,
                    status=_status_char(d.change_type),
                ))

        for f in untracked:
            if f not in tracked_files:
                entries.append(StatusEntry(
                    file=f,
                    x="?",
                    y="?",
                    status="untracked",
                ))

    except Exception as exc:
        repo.close()
        return {"success": False, "entries": [], "count": 0, "error": f"Failed to read status: {exc}"}

    result = {
        "success": True,
        "entries": [e.to_dict() for e in entries],
        "count": len(entries),
        "branch": _branch_name(repo),
        "ahead": 0,
        "behind": 0,
        "error": None,
    }

    # Add ahead/behind if remote tracking exists
    try:
        if repo.head.is_valid() and repo.head.upstream:
            info = repo.head.reference.tracking_branch()
            if info:
                commits_ahead = sum(1 for _ in repo.iter_commits(f"{info.name}..{repo.head.name}"))
                commits_behind = sum(1 for _ in repo.iter_commits(f"{repo.head.name}..{info.name}"))
                result["ahead"] = commits_ahead
                result["behind"] = commits_behind
    except Exception:
        pass

    repo.close()
    return result


def _is_staged(c: str) -> bool:
    return c in ("A", "M", "D", "R", "C")


def _branch_name(repo) -> str:
    try:
        return repo.active_branch.name
    except (TypeError, Exception):
        return "HEAD (detached)"


# ── get_diff ──────────────────────────────────────────────────────────────


def get_diff(path: str = ".", staged: bool = False) -> dict[str, Any]:
    """Return a structured diff of changes.

    Args:
        path: Directory or file path inside the workspace.
        staged: If True, diff staged (index) changes vs HEAD.
                If False, diff unstaged working tree changes.

    Returns:
        Dict with ``files`` (DiffFile list), total ``insertions``,
        ``deletions``, and ``raw_diff`` (unified diff string).
    """
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "files": [], "insertions": 0, "deletions": 0, "raw_diff": "", "error": str(exc)}

    if not repo.head.is_valid():
        repo.close()
        return {"success": False, "files": [], "insertions": 0, "deletions": 0, "raw_diff": "", "error": "Repository has no commits yet"}

    try:
        if staged:
            diffs = repo.head.commit.diff(repo.head.commit.tree, R=True) if repo.head.is_valid() else []
        else:
            diffs = repo.index.diff(None)

        insertions = 0
        deletions = 0
        files: list[DiffFile] = []
        raw_parts: list[str] = []

        for d in diffs:
            file_path = d.a_path if d.change_type == "D" else d.b_path
            try:
                diff_data = d.diff.decode("utf-8", errors="replace") if d.diff else ""
            except Exception:
                diff_data = ""

            raw_parts.append(diff_data)

            if staged and d.change_type == "D" and hasattr(d, "a_blob") and d.a_blob:
                try:
                    old_lines = d.a_blob.data_stream.read().decode("utf-8", errors="replace").splitlines()
                    insertions += 0
                    deletions += len(old_lines)
                except Exception:
                    pass
                files.append(DiffFile(path=file_path, added_lines=0, deleted_lines=deletions))
                continue

            parsed = _parse_diff(diff_data)
            ins = sum(1 for h in parsed for l in h if l.type == "added")
            dels = sum(1 for h in parsed for l in h if l.type == "deleted")
            insertions += ins
            deletions += dels

            if staged and d.change_type == "A" and d.b_blob:
                try:
                    new_lines = d.b_blob.data_stream.read().decode("utf-8", errors="replace").splitlines()
                    ins = len(new_lines)
                    deletions -= dels  # don't also count from the parsed diff
                    insertions += ins
                except Exception:
                    pass

            files.append(DiffFile(path=file_path, added_lines=ins, deleted_lines=dels, hunks=parsed))

        repo.close()
        return {
            "success": True,
            "files": [f.to_dict() for f in files],
            "files_changed": len(files),
            "insertions": insertions,
            "deletions": deletions,
            "raw_diff": "".join(raw_parts),
            "error": None,
        }

    except Exception as exc:
        repo.close()
        return {"success": False, "files": [], "insertions": 0, "deletions": 0, "raw_diff": "", "error": f"Diff failed: {exc}"}


def _parse_diff(diff_text: str) -> list[list[DiffLine]]:
    """Parse a unified diff string into hunks of DiffLine."""
    if not diff_text:
        return []
    hunks: list[list[DiffLine]] = []
    current_hunk: list[DiffLine] = []

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = [DiffLine(type="header", content=line)]
            parts = line.split()
            if len(parts) >= 2:
                old_range = parts[1]
                new_range = parts[2] if len(parts) > 2 else ""
                try:
                    old_start = int(old_range.split(",")[0].lstrip("-"))
                    new_start = int(new_range.split(",")[0].lstrip("+"))
                except (ValueError, IndexError):
                    old_start = None
                    new_start = None
                if old_start is not None and current_hunk:
                    current_hunk[0].old_line = old_start
                    current_hunk[0].new_line = new_start
        elif line.startswith("+"):
            current_hunk.append(DiffLine(type="added", content=line[1:]))
        elif line.startswith("-"):
            current_hunk.append(DiffLine(type="deleted", content=line[1:]))
        elif line.startswith(" "):
            current_hunk.append(DiffLine(type="context", content=line[1:]))
        elif line.startswith("\\"):
            current_hunk.append(DiffLine(type="context", content=line))
    if current_hunk:
        hunks.append(current_hunk)
    return hunks


# ── get_log ───────────────────────────────────────────────────────────────


def get_log(path: str = ".", n: int = 10) -> dict[str, Any]:
    """Return the recent commit log.

    Args:
        path: Directory inside the workspace.
        n: Maximum number of commits to return (default 10, max 500).

    Returns:
        Dict with ``commits`` (CommitInfo list).
    """
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "commits": [], "count": 0, "error": str(exc)}

    if not repo.head.is_valid():
        repo.close()
        return {"success": False, "commits": [], "count": 0, "error": "Repository has no commits yet"}

    try:
        n = max(1, min(n, 500))
        commits: list[CommitInfo] = []
        for c in repo.iter_commits(max_count=n):
            stats = _short_stats(c.stats) if c.stats else {}
            commits.append(CommitInfo(
                hexsha=c.hexsha,
                short_sha=c.hexsha[:7],
                author_name=c.author.name,
                author_email=c.author.email,
                authored_at=_dt_to_iso(c.authored_datetime),
                committer_name=c.committer.name,
                committer_email=c.committer.email,
                committed_at=_dt_to_iso(c.committed_datetime),
                message=c.message.strip(),
                summary=c.message.split("\n")[0] if c.message else "",
                files_changed=stats.get("files_changed", 0),
            ))

        current_branch = _branch_name(repo)
        repo.close()
        return {
            "success": True,
            "commits": [c.to_dict() for c in commits],
            "count": len(commits),
            "branch": current_branch,
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "commits": [], "count": 0, "error": f"Log failed: {exc}"}


# ── get_current_branch ───────────────────────────────────────────────────


def get_current_branch(path: str = ".") -> dict[str, Any]:
    """Return the name of the currently active branch."""
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "branch": None, "error": str(exc)}

    try:
        name = _branch_name(repo)
        is_detached = name == "HEAD (detached)"
        sha = repo.head.commit.hexsha[:7] if repo.head.is_valid() else None
        repo.close()
        return {
            "success": True,
            "branch": name,
            "is_detached": is_detached,
            "full_name": repo.active_branch.path if not is_detached else None,
            "sha": sha,
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "branch": None, "error": f"Failed to get branch: {exc}"}


# ── list_branches ─────────────────────────────────────────────────────────


def list_branches(path: str = ".", include_remote: bool = False) -> dict[str, Any]:
    """List all branches.

    Args:
        path: Directory inside the workspace.
        include_remote: If True, include remote-tracking branches.

    Returns:
        Dict with ``branches`` list and ``current`` branch name.
    """
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "branches": [], "current": None, "count": 0, "error": str(exc)}

    try:
        current = _branch_name(repo)
        branches: list[dict[str, Any]] = []

        for b in repo.branches:
            try:
                commit_sha = b.commit.hexsha[:7] if b.commit else None
            except Exception:
                commit_sha = None
            branches.append({
                "name": b.name,
                "full_path": b.path,
                "is_current": b.name == current,
                "commit_sha": commit_sha,
                "type": "local",
            })

        if include_remote:
            for r in repo.remotes:
                for ref in r.refs:
                    remote_name = ref.remote_name
                    branch_name = ref.remote_head
                    full = f"{remote_name}/{branch_name}"
                    try:
                        commit_sha = ref.commit.hexsha[:7] if ref.commit else None
                    except Exception:
                        commit_sha = None
                    branches.append({
                        "name": full,
                        "full_path": ref.path,
                        "is_current": False,
                        "commit_sha": commit_sha,
                        "type": "remote",
                    })

        repo.close()
        return {
            "success": True,
            "branches": branches,
            "current": current,
            "count": len(branches),
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "branches": [], "current": None, "count": 0, "error": f"Failed to list branches: {exc}"}


# ── stage_files ───────────────────────────────────────────────────────────


def stage_files(path: str = ".", file_patterns: list[str] | None = None) -> dict[str, Any]:
    """Stage files (``git add``) for the next commit.

    Args:
        path: Directory inside the workspace.
        file_patterns: List of file paths or glob patterns to stage.
                       If None, stages all changes (equivalent to ``git add -A``).

    Returns:
        Preview of what was staged.
    """
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "staged": [], "count": 0, "error": str(exc)}

    if not repo.head.is_valid():
        repo.close()
        return {"success": False, "staged": [], "count": 0, "error": "Repository has no commits yet"}

    try:
        staged_list: list[str] = []
        if file_patterns:
            repo.index.add(file_patterns)
            staged_list = file_patterns
        else:
            tracked = repo.index.diff(None)
            untracked = repo.untracked_files
            repo.index.add(".")
            staged_list = [d.b_path if d.change_type != "D" else d.a_path for d in tracked]
            staged_list.extend(untracked)

        repo.close()
        return {
            "success": True,
            "staged": staged_list,
            "count": len(staged_list),
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "staged": [], "count": 0, "error": f"Stage failed: {exc}"}


# ── unstage_files ─────────────────────────────────────────────────────────


def unstage_files(path: str = ".", file_patterns: list[str] | None = None) -> dict[str, Any]:
    """Unstage files (``git restore --staged``).

    Args:
        path: Directory inside the workspace.
        file_patterns: List of file paths to unstage.
                       If None, unstages everything.

    Returns:
        List of unstaged files.
    """
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "unstaged": [], "count": 0, "error": str(exc)}

    if not repo.head.is_valid():
        repo.close()
        return {"success": False, "unstaged": [], "count": 0, "error": "Repository has no commits yet"}

    try:
        unstaged_list: list[str] = []
        if file_patterns:
            repo.index.reset(paths=file_patterns)
            unstaged_list = file_patterns
        else:
            diff_staged = repo.head.commit.diff("HEAD") if repo.head.is_valid() else []
            repo.index.reset()
            unstaged_list = [d.a_path or d.b_path for d in diff_staged]

        repo.close()
        return {
            "success": True,
            "unstaged": unstaged_list,
            "count": len(unstaged_list),
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "unstaged": [], "count": 0, "error": f"Unstage failed: {exc}"}


# ── commit ────────────────────────────────────────────────────────────────


def commit(
    path: str = ".",
    message: str = "",
    approved: bool = False,
    author_name: str | None = None,
    author_email: str | None = None,
) -> dict[str, Any]:
    """Create a git commit.

    **Never commits without ``approved=True``.**  When ``approved`` is
    ``False`` (the default), returns a preview of staged changes that
    would be committed.  Only actually commits when the caller passes
    ``approved=True``.

    Args:
        path: Directory inside the workspace.
        message: Commit message.  If empty, generates a placeholder.
        approved: Must be ``True`` to actually commit.
        author_name: Override author name (optional).
        author_email: Override author email (optional).

    Returns:
        On preview (``approved=False``): preview dict with staged file
        count, entries, and diff stats.
        On commit (``approved=True``): CommitInfo dict.
    """
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    if not repo.head.is_valid():
        repo.close()
        return {"success": False, "error": "Repository has no commits yet"}

    try:
        preview = _preview_staged(repo)

        if not approved:
            no_staged = preview["staged_files_count"] == 0
            repo.close()
            return {
                "success": True,
                "committed": False,
                "approved": False,
                "preview": preview,
                "warning": "Nothing staged to commit" if no_staged else None,
                "message": "Pass approved=True to commit",
                "error": None,
            }

        if preview["staged_files_count"] == 0:
            repo.close()
            return {
                "success": False,
                "committed": False,
                "approved": True,
                "preview": preview,
                "error": "Nothing staged to commit — stage files first",
            }

        msg = message or "wigent: automated commit"
        kwargs = {"message": msg}
        if author_name:
            kwargs["author"] = f"{author_name} <{author_email or ''}>"
        if author_email and not author_name:
            kwargs["author"] = f"wigent <{author_email}>"

        import git
        try:
            commit_obj = repo.index.commit(**kwargs)
        except git.exc.CommitError as exc:
            repo.close()
            return {"success": False, "committed": False, "error": f"Commit failed: {exc}"}

        stats = _short_stats(commit_obj.stats) if commit_obj.stats else {}
        result = CommitInfo(
            hexsha=commit_obj.hexsha,
            short_sha=commit_obj.hexsha[:7],
            author_name=commit_obj.author.name,
            author_email=commit_obj.author.email,
            authored_at=_dt_to_iso(commit_obj.authored_datetime),
            committer_name=commit_obj.committer.name,
            committer_email=commit_obj.committer.email,
            committed_at=_dt_to_iso(commit_obj.committed_datetime),
            message=commit_obj.message.strip(),
            summary=commit_obj.message.split("\n")[0] if commit_obj.message else "",
            files_changed=stats.get("files_changed", 0),
        )
        repo.close()
        return {
            "success": True,
            "committed": True,
            "commit": result.to_dict(),
            "preview": preview,
            "error": None,
        }

    except Exception as exc:
        repo.close()
        return {"success": False, "committed": False, "error": f"Commit failed: {exc}"}


# ── create_branch ─────────────────────────────────────────────────────────


def create_branch(path: str = ".", name: str = "", base_branch: str | None = None) -> dict[str, Any]:
    """Create and switch to a new branch.

    Args:
        path: Directory inside the workspace.
        name: Name for the new branch.
        base_branch: Branch or commit to fork from (default: current HEAD).

    Returns:
        Dict with the new branch name and the sha it was created from.
    """
    if not name:
        return {"success": False, "error": "Branch name is required"}

    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    try:
        if base_branch:
            base = base_branch
        else:
            base = repo.head.commit.hexsha if repo.head.is_valid() else "HEAD"

        original_branch = _branch_name(repo)
        new_ref = repo.create_head(name, base)
        new_ref.checkout()

        sha = repo.head.commit.hexsha[:7] if repo.head.is_valid() else None
        repo.close()
        return {
            "success": True,
            "branch": name,
            "created_from": base[:7] if len(base) > 7 else base,
            "previous_branch": original_branch,
            "sha": sha,
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "error": f"Failed to create branch: {exc}"}


# ── get_blame ─────────────────────────────────────────────────────────────


def get_blame(path: str = ".", file_path: str = "", line: int | None = None) -> dict[str, Any]:
    """Get blame/annotate information for a file.

    Args:
        path: Directory inside the workspace (for repo discovery).
        file_path: Path to the file to blame (relative to repo root).
        line: If set, only return blame for this specific line (1-indexed).

    Returns:
        Dict with ``blame`` list (BlameLine per line).
    """
    if not file_path:
        return {"success": False, "blame": [], "count": 0, "error": "file_path is required"}

    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "blame": [], "count": 0, "error": str(exc)}

    if not repo.head.is_valid():
        repo.close()
        return {"success": False, "blame": [], "count": 0, "error": "Repository has no commits yet"}

    try:
        full_path = os.path.join(repo.working_dir, file_path)
        if not os.path.isfile(full_path):
            repo.close()
            return {"success": False, "blame": [], "count": 0, "error": f"File not found: {file_path}"}

        blame_lines: list[BlameLine] = []
        for commit_ref, lines in repo.blame("HEAD", file_path):
            hexsha = commit_ref.hexsha
            short_sha = hexsha[:7]
            author_name = commit_ref.author.name
            author_email = commit_ref.author.email
            authored_at = _dt_to_iso(commit_ref.authored_datetime)
            summary = commit_ref.message.split("\n")[0] if commit_ref.message else ""
            for i, content in enumerate(lines, 1):
                absolute_line = i + (blame_lines[-1].line if blame_lines else 0)
                blame_lines.append(BlameLine(
                    line=absolute_line,
                    content=content.rstrip("\n"),
                    hexsha=hexsha,
                    author_name=author_name,
                    author_email=author_email,
                    authored_at=authored_at,
                    summary=summary,
                ))

        if line is not None:
            blame_lines = [bl for bl in blame_lines if bl.line == line]
            if not blame_lines:
                repo.close()
                return {"success": False, "blame": [], "count": 0, "error": f"Line {line} not found in blame output"}

        repo.close()
        return {
            "success": True,
            "blame": [b.to_dict() for b in blame_lines],
            "count": len(blame_lines),
            "file": file_path,
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "blame": [], "count": 0, "error": f"Blame failed: {exc}"}


# ── get_file_history ─────────────────────────────────────────────────────


def get_file_history(path: str = ".", file_path: str = "") -> dict[str, Any]:
    """Return the commit history for a single file.

    Args:
        path: Directory inside the workspace (for repo discovery).
        file_path: File path relative to repo root.

    Returns:
        Dict with ``commits`` (CommitInfo list).
    """
    if not file_path:
        return {"success": False, "commits": [], "count": 0, "error": "file_path is required"}

    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "commits": [], "count": 0, "error": str(exc)}

    if not repo.head.is_valid():
        repo.close()
        return {"success": False, "commits": [], "count": 0, "error": "Repository has no commits yet"}

    try:
        full_path = os.path.join(repo.working_dir, file_path)
        if not os.path.isfile(full_path):
            repo.close()
            return {"success": False, "commits": [], "count": 0, "error": f"File not found: {file_path}"}

        commits: list[CommitInfo] = []
        for c in repo.iter_commits(paths=file_path):
            stats = _short_stats(c.stats) if c.stats else {}
            commits.append(CommitInfo(
                hexsha=c.hexsha,
                short_sha=c.hexsha[:7],
                author_name=c.author.name,
                author_email=c.author.email,
                authored_at=_dt_to_iso(c.authored_datetime),
                committer_name=c.committer.name,
                committer_email=c.committer.email,
                committed_at=_dt_to_iso(c.committed_datetime),
                message=c.message.strip(),
                summary=c.message.split("\n")[0] if c.message else "",
                files_changed=stats.get("files_changed", 0),
            ))

        repo.close()
        return {
            "success": True,
            "commits": [c.to_dict() for c in commits],
            "count": len(commits),
            "file": file_path,
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "commits": [], "count": 0, "error": f"File history failed: {exc}"}


# ── stash_changes ─────────────────────────────────────────────────────────


def stash_changes(path: str = ".", message: str = "", include_untracked: bool = False) -> dict[str, Any]:
    """Stash working directory changes.

    Args:
        path: Directory inside the workspace.
        message: Optional stash message.
        include_untracked: If True, also stash untracked files (``git stash -u``).

    Returns:
        Dict with stash result info.
    """
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    try:
        status_before = repo.is_dirty(index=True, working_tree=True, untracked_files=True)
        if not status_before:
            repo.close()
            return {"success": False, "error": "No changes to stash", "stashed": False}

        stash_args = ["save"]
        if include_untracked:
            stash_args.append("--include-untracked")
        if message:
            stash_args.append(message)
        else:
            stash_args.append(f"wigent: stash at {datetime.now().isoformat(timespec='seconds')}")

        repo.git.stash(*stash_args)

        stashes = _get_stashes(repo)
        new_stash = stashes[0] if stashes else None
        repo.close()
        return {
            "success": True,
            "stashed": True,
            "stash_index": 0,
            "message": message or f"wigent: stash at {datetime.now().isoformat(timespec='seconds')}",
            "stash_sha": new_stash.get("short_sha") if new_stash else None,
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "stashed": False, "error": f"Stash failed: {exc}"}


def _get_stashes(repo) -> list[dict[str, Any]]:
    """Get stash list by parsing ``git stash list`` output.

    Returns a list of dicts with keys: index, message, hexsha, short_sha.
    """
    try:
        output = repo.git.stash("list")
    except Exception:
        return []
    stashes = []
    import re as _re
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _re.match(r"stash@\{(\d+)\}:\s+(.*)", line)
        if m:
            try:
                commit = repo.commit(f"stash@{{{m.group(1)}}}")
                hexsha = commit.hexsha
                short_sha = hexsha[:7]
            except Exception:
                hexsha = ""
                short_sha = ""
            stashes.append({
                "index": int(m.group(1)),
                "message": m.group(2),
                "hexsha": hexsha,
                "short_sha": short_sha,
            })
    return stashes


# ── pop_stash ─────────────────────────────────────────────────────────────


def pop_stash(path: str = ".", index: int = 0) -> dict[str, Any]:
    """Pop (apply and drop) a stash entry.

    Args:
        path: Directory inside the workspace.
        index: Stash index to pop (0 = most recent).

    Returns:
        Dict with result info.
    """
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    try:
        stashes = _get_stashes(repo)
        if not stashes:
            repo.close()
            return {"success": False, "error": "No stashes to pop", "popped": False}

        if index >= len(stashes):
            repo.close()
            return {"success": False, "error": f"Stash index {index} out of range (0-{len(stashes) - 1})", "popped": False}

        target = stashes[index]
        sha_before = target.get("short_sha")

        repo.git.stash("pop", str(index))

        repo.close()
        return {
            "success": True,
            "popped": True,
            "index": index,
            "stash_sha": sha_before,
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "popped": False, "error": f"Stash pop failed: {exc}"}


# ── list_stashes ──────────────────────────────────────────────────────────


def list_stashes(path: str = ".") -> dict[str, Any]:
    """List all stash entries.

    Args:
        path: Directory inside the workspace.

    Returns:
        Dict with ``stashes`` list (StashInfo).
    """
    try:
        repo = _get_repo(path)
    except ValueError as exc:
        return {"success": False, "stashes": [], "count": 0, "error": str(exc)}

    stashes_list: list[StashInfo] = []
    try:
        for entry in _get_stashes(repo):
            stashes_list.append(StashInfo(
                index=entry.get("index", 0),
                message=entry.get("message", ""),
                hexsha=entry.get("hexsha", ""),
                short_sha=entry.get("short_sha", ""),
            ))
        repo.close()
        return {
            "success": True,
            "stashes": [s.to_dict() for s in stashes_list],
            "count": len(stashes_list),
            "error": None,
        }
    except Exception as exc:
        repo.close()
        return {"success": False, "stashes": [], "count": 0, "error": f"List stashes failed: {exc}"}


__all__ = [
    "check_is_git_repo",
    "get_repo_root",
    "get_status",
    "get_diff",
    "get_log",
    "get_current_branch",
    "list_branches",
    "stage_files",
    "unstage_files",
    "commit",
    "create_branch",
    "get_blame",
    "get_file_history",
    "stash_changes",
    "pop_stash",
    "list_stashes",
]
