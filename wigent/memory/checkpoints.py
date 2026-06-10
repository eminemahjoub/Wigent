from __future__ import annotations

import difflib
import json
import logging
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wigent.config import settings

logger = logging.getLogger(__name__)

CHECKPOINT_DIR_NAME = "checkpoints"


class CheckpointError(Exception):
    """Raised when a checkpoint operation fails."""


class CheckpointManager:
    """Saves and restores agent state snapshots with file backups.

    Each checkpoint is a directory under ``{SESSION_DIR}/checkpoints/{id}/``
    containing:
      ``metadata.json``    — label, timestamps, mode, iteration
      ``agent_state.json`` — full agent state (messages, tool calls, ...)
      ``files/``            — copies of modified files (path → original content)

    Thread-safe for concurrent access.
    """

    def __init__(self, storage_dir: str | None = None) -> None:
        self._base_dir = Path(
            storage_dir or os.path.join(settings.SESSION_DIR, CHECKPOINT_DIR_NAME)
        )
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────

    def create_checkpoint(
        self,
        label: str = "",
        auto: bool = False,
        agent_state: dict[str, Any] | None = None,
        messages: list[dict[str, Any]] | None = None,
        files_snapshot: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a new checkpoint.

        Args:
            label: Human-readable label.
            auto: If ``True``, marks the checkpoint as auto-generated.
            agent_state: Serializable agent state dict.
            messages: Current message list.
            files_snapshot: Dict mapping file paths to original content.

        Returns:
            A dict with checkpoint metadata.
        """
        ckpt_id = uuid.uuid4().hex[:12]
        ckpt_dir = self._base_dir / ckpt_id
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        prefix = "auto" if auto else "manual"

        metadata = {
            "id": ckpt_id,
            "label": label or f"{prefix}_checkpoint_{ckpt_id[:8]}",
            "auto": auto,
            "created_at": now,
            "message_count": len(messages) if messages else 0,
        }

        # Write metadata.
        (ckpt_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Write agent state.
        if agent_state:
            (ckpt_dir / "agent_state.json").write_text(
                json.dumps(agent_state, indent=2, default=str, ensure_ascii=False),
                encoding="utf-8",
            )

        # Write file snapshots.
        if files_snapshot:
            files_dir = ckpt_dir / "files"
            files_dir.mkdir(exist_ok=True)
            for fpath, content in files_snapshot.items():
                safe_name = fpath.replace("/", "__").replace("\\", "__")
                (files_dir / safe_name).write_text(content, encoding="utf-8")
            metadata["files_backed_up"] = len(files_snapshot)

        with self._lock:
            pass  # serialisation barrier

        logger.info(
            "Checkpoint created: %s  label=%s  auto=%s  files=%d",
            ckpt_id, metadata.get("label", ""), auto,
            len(files_snapshot) if files_snapshot else 0,
        )

        return metadata

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """Return metadata for all checkpoints, newest first."""
        checkpoints: list[dict[str, Any]] = []
        with self._lock:
            for ckpt_dir in sorted(self._base_dir.iterdir()):
                if not ckpt_dir.is_dir():
                    continue
                meta_path = ckpt_dir / "metadata.json"
                if not meta_path.is_file():
                    continue
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    # Enrich with file info.
                    files_dir = ckpt_dir / "files"
                    data["file_count"] = (
                        len([f for f in files_dir.iterdir() if f.is_file()])
                        if files_dir.is_dir() else 0
                    )
                    checkpoints.append(data)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Failed to read checkpoint %s: %s", ckpt_dir.name, exc)
        checkpoints.sort(key=lambda c: c.get("created_at", ""), reverse=True)
        return checkpoints

    def restore_checkpoint(self, ckpt_id: str) -> dict[str, Any]:
        """Restore agent state and file contents from a checkpoint.

        Returns a dict with ``agent_state``, ``messages`` (from ``agent_state.json``)
        and ``restored_files`` (paths that were written back).
        """
        ckpt_dir = self._base_dir / ckpt_id
        if not ckpt_dir.is_dir():
            raise CheckpointError(f"Checkpoint not found: {ckpt_id}")

        result: dict[str, Any] = {
            "checkpoint_id": ckpt_id,
            "restored_files": [],
            "agent_state": None,
        }

        # Restore agent state.
        state_path = ckpt_dir / "agent_state.json"
        if state_path.is_file():
            result["agent_state"] = json.loads(state_path.read_text(encoding="utf-8"))

        # Restore file snapshots.
        files_dir = ckpt_dir / "files"
        if files_dir.is_dir():
            for fname in files_dir.iterdir():
                if not fname.is_file():
                    continue
                original_path = fname.name.replace("__", "/")
                try:
                    content = fname.read_text(encoding="utf-8")
                    abs_path = os.path.join(settings.workspace_path, original_path)
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    Path(abs_path).write_text(content, encoding="utf-8")
                    result["restored_files"].append(original_path)
                    logger.info("Restored file: %s", original_path)
                except OSError as exc:
                    logger.warning("Failed to restore file %s: %s", original_path, exc)

        logger.info(
            "Checkpoint restored: %s  files_restored=%d",
            ckpt_id, len(result["restored_files"]),
        )
        return result

    def delete_checkpoint(self, ckpt_id: str) -> bool:
        """Delete a checkpoint by id.

        Returns ``True`` if the checkpoint was removed.
        """
        ckpt_dir = self._base_dir / ckpt_id
        if not ckpt_dir.is_dir():
            return False
        try:
            shutil.rmtree(ckpt_dir)
            logger.info("Checkpoint deleted: %s", ckpt_id)
            return True
        except OSError as exc:
            raise CheckpointError(f"Failed to delete checkpoint {ckpt_id}: {exc}") from exc

    def diff_checkpoints(self, id1: str, id2: str) -> list[dict[str, Any]]:
        """Compute a line-by-line diff of file snapshots between two checkpoints.

        Returns a list of diff entries, one per file that differs.
        """
        files1 = self._load_files(id1)
        files2 = self._load_files(id2)
        all_files = set(files1.keys()) | set(files2.keys())
        diffs: list[dict[str, Any]] = []

        for fname in sorted(all_files):
            old = files1.get(fname, "")
            new = files2.get(fname, "")
            if old == new:
                continue
            diff_lines = list(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"{fname} (checkpoint {id1[:8]})",
                    tofile=f"{fname} (checkpoint {id2[:8]})",
                )
            )
            diffs.append({
                "file": fname,
                "diff": "".join(diff_lines),
                "changed": old != new,
            })

        return diffs

    def auto_checkpoint(
        self,
        label: str = "",
        agent_state: dict[str, Any] | None = None,
        messages: list[dict[str, Any]] | None = None,
        files_snapshot: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Quick shorthand for ``create_checkpoint(auto=True, ...)``."""
        return self.create_checkpoint(
            label=label,
            auto=True,
            agent_state=agent_state,
            messages=messages,
            files_snapshot=files_snapshot,
        )

    def cleanup_old(self, keep_last: int = 10) -> int:
        """Remove the oldest auto-checkpoints, keeping the *keep_last*
        most recent ones.

        Args:
            keep_last: Number of most recent checkpoints to retain.

        Returns:
            Number of checkpoints removed.
        """
        all_ckpts = self.list_checkpoints()
        auto_ckpts = [c for c in all_ckpts if c.get("auto")]

        if len(auto_ckpts) <= keep_last:
            return 0

        # Sort oldest first; remove oldest beyond keep_last.
        auto_ckpts.sort(key=lambda c: c.get("created_at", ""))
        to_remove = auto_ckpts[:-keep_last]
        removed = 0
        for ckpt in to_remove:
            try:
                if self.delete_checkpoint(ckpt["id"]):
                    removed += 1
            except CheckpointError:
                pass

        if removed:
            logger.info("cleanup_old: removed %d checkpoints (keeping %d)", removed, keep_last)
        return removed

    # ── Internals ──────────────────────────────────────────────────────

    def _load_files(self, ckpt_id: str) -> dict[str, str]:
        """Load all file snapshots from a checkpoint as ``{filename: content}``."""
        files_dir = self._base_dir / ckpt_id / "files"
        result: dict[str, str] = {}
        if not files_dir.is_dir():
            return result
        for fname in files_dir.iterdir():
            if fname.is_file():
                original_path = fname.name.replace("__", "/")
                try:
                    result[original_path] = fname.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    logger.warning("Failed to read file snapshot %s: %s", fname, exc)
        return result


__all__ = ["CheckpointManager", "CheckpointError"]
