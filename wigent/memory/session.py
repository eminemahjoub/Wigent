from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wigent.config import settings

logger = logging.getLogger(__name__)


class SessionData:
    """Data container for a single session.

    Serialises to/from JSON for persistent storage.
    """

    def __init__(
        self,
        session_id: str,
        name: str = "",
        description: str = "",
        messages: list[dict[str, Any]] | None = None,
        mode_history: list[str] | None = None,
        files_modified: list[str] | None = None,
        total_tokens: int = 0,
        total_cost: float = 0.0,
        tags: list[str] | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.name = name or f"session_{session_id[:8]}"
        self.description = description
        self.messages = messages or []
        self.mode_history = mode_history or []
        self.files_modified = files_modified or []
        self.total_tokens = total_tokens
        self.total_cost = total_cost
        self.tags = tags or []
        now = datetime.now(timezone.utc).isoformat()
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "messages": self.messages,
            "mode_history": self.mode_history,
            "files_modified": self.files_modified,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionData:
        return cls(**data)


class SessionManager:
    """Persists, loads, lists, and exports agent sessions.

    Storage: ``{SESSION_DIR}/{name}.json``
    Thread-safe for concurrent access.
    """

    def __init__(self, storage_dir: str | None = None) -> None:
        self._storage_dir = os.path.abspath(
            storage_dir or settings.SESSION_DIR
        )
        os.makedirs(self._storage_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: dict[str, SessionData] = {}

    # ── CRUD ────────────────────────────────────────────────────────────

    def create_session(
        self,
        name: str = "",
        description: str = "",
        tags: list[str] | None = None,
    ) -> SessionData:
        """Create a new session with a unique id.

        Args:
            name: Human-readable session name.
            description: Optional description of the session goal.
            tags: Optional list of tags for filtering.

        Returns:
            The newly created ``SessionData``.
        """
        import uuid
        session_id = uuid.uuid4().hex[:16]
        session = SessionData(
            session_id=session_id,
            name=name or f"session_{session_id[:8]}",
            description=description,
            tags=tags or [],
        )
        with self._lock:
            self._cache[session.name] = session
            self._persist(session)
        logger.info("Session created: %s (%s)", session.name, session_id[:8])
        return session

    def save_session(self, session: SessionData) -> None:
        """Persist an existing session to disk.

        Updates the ``updated_at`` timestamp automatically.
        """
        session.updated_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._cache[session.name] = session
            self._persist(session)

    def load_session(self, name: str) -> SessionData | None:
        """Load a session by name.

        Returns ``None`` if the session does not exist.
        """
        with self._lock:
            if name in self._cache:
                return self._cache[name]
            path = self._path_for(name)
            if path.is_file():
                session = self._deserialize(path)
                if session:
                    self._cache[name] = session
                return session
        return None

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return metadata for all stored sessions.

        Returns a list of summaries (not full message histories).
        """
        sessions: list[dict[str, Any]] = []
        with self._lock:
            seen = set()
            for path in sorted(Path(self._storage_dir).glob("*.json")):
                name = path.stem
                if name in seen:
                    continue
                seen.add(name)
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    sessions.append({
                        "name": data.get("name", name),
                        "session_id": data.get("session_id", ""),
                        "description": data.get("description", ""),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "message_count": len(data.get("messages", [])),
                        "total_tokens": data.get("total_tokens", 0),
                        "total_cost": data.get("total_cost", 0.0),
                        "tags": data.get("tags", []),
                        "file_count": len(data.get("files_modified", [])),
                    })
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Failed to read session %s: %s", name, exc)
        return sessions

    def delete_session(self, name: str) -> bool:
        """Delete a session by name.

        Returns ``True`` if the session was deleted.
        """
        path = self._path_for(name)
        with self._lock:
            self._cache.pop(name, None)
            if path.is_file():
                path.unlink()
                logger.info("Session deleted: %s", name)
                return True
        return False

    # ── Export ──────────────────────────────────────────────────────────

    def export_session(self, name: str, fmt: str = "json") -> str | None:
        """Export a session in the requested format.

        Args:
            name: Session name.
            fmt: ``"json"`` or ``"md"`` (Markdown).

        Returns:
            The serialised content as a string, or ``None`` if the
            session does not exist.
        """
        session = self.load_session(name)
        if session is None:
            return None

        if fmt == "json":
            return json.dumps(session.to_dict(), indent=2, ensure_ascii=False)
        if fmt == "md":
            return self._to_markdown(session)
        raise ValueError(f"Unsupported export format: {fmt}")

    def get_session_summary(self, name: str) -> dict[str, Any] | None:
        """Return a lightweight summary of a session (no full messages)."""
        session = self.load_session(name)
        if session is None:
            return None
        return {
            "name": session.name,
            "session_id": session.session_id,
            "description": session.description,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "message_count": len(session.messages),
            "mode_history": list(session.mode_history),
            "total_tokens": session.total_tokens,
            "total_cost": session.total_cost,
            "tags": list(session.tags),
            "files_modified": list(session.files_modified),
        }

    # ── Internals ──────────────────────────────────────────────────────

    def _path_for(self, name: str) -> Path:
        safe_name = name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        return Path(self._storage_dir) / f"{safe_name}.json"

    def _persist(self, session: SessionData) -> None:
        """Write a session to its JSON file."""
        path = self._path_for(session.name)
        try:
            path.write_text(
                json.dumps(session.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Failed to persist session %s: %s", session.name, exc)

    def _deserialize(self, path: Path) -> SessionData | None:
        """Read a session from a JSON file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SessionData.from_dict(data)
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            logger.warning("Failed to deserialize %s: %s", path, exc)
            return None

    @staticmethod
    def _to_markdown(session: SessionData) -> str:
        """Format a session as a Markdown document."""
        lines = [
            f"# Session: {session.name}",
            f"**ID:** {session.session_id}",
            f"**Created:** {session.created_at}",
            f"**Updated:** {session.updated_at}",
            f"**Tokens:** {session.total_tokens}  **Cost:** ${session.total_cost:.6f}",
            f"**Messages:** {len(session.messages)}",
            "",
            "## Messages",
        ]
        for i, m in enumerate(session.messages, 1):
            role = m.get("role", "?").upper()
            content = str(m.get("content", ""))[:500]
            lines.append(f"\n### {i}. {role}\n```\n{content}\n```")
        if session.files_modified:
            lines.append("\n## Files Modified")
            for f in session.files_modified:
                lines.append(f"- `{f}`")
        if session.mode_history:
            lines.append("\n## Modes Used")
            for mode in session.mode_history:
                lines.append(f"- {mode}")
        if session.tags:
            lines.append("\n## Tags")
            lines.append(", ".join(session.tags))
        return "\n".join(lines)


__all__ = ["SessionManager", "SessionData"]
