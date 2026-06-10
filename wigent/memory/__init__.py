from __future__ import annotations

import logging
from typing import Any

from wigent.config import settings
from wigent.memory.checkpoints import CheckpointManager, CheckpointError
from wigent.memory.context_manager import ContextManager, TokenBudgetExceeded
from wigent.memory.conversation import ConversationHistory
from wigent.memory.session import SessionManager, SessionData
from wigent.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MemorySystem:
    """Unified facade over all memory sub-systems.

    Provides a single entry point for context management, session
    persistence, checkpointing, and vector search.

    Usage
    -----
        mem = MemorySystem()
        mem.initialize()

        mem.context.add_message("user", "Hello")
        session = mem.sessions.create_session("my-session")
        mem.checkpoints.auto_checkpoint(label="before-refactor")
        mem.vectors.add_document("def foo(): pass", {"file": "bar.py"})

        mem.shutdown()
    """

    def __init__(self) -> None:
        self._context: ContextManager | None = None
        self._sessions: SessionManager | None = None
        self._checkpoints: CheckpointManager | None = None
        self._vectors: VectorStore | None = None
        self._initialized: bool = False

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def context(self) -> ContextManager:
        if self._context is None:
            raise RuntimeError("MemorySystem not initialized. Call .initialize() first.")
        return self._context

    @property
    def sessions(self) -> SessionManager:
        if self._sessions is None:
            raise RuntimeError("MemorySystem not initialized. Call .initialize() first.")
        return self._sessions

    @property
    def checkpoints(self) -> CheckpointManager:
        if self._checkpoints is None:
            raise RuntimeError("MemorySystem not initialized. Call .initialize() first.")
        return self._checkpoints

    @property
    def vectors(self) -> VectorStore:
        if self._vectors is None:
            raise RuntimeError("MemorySystem not initialized. Call .initialize() first.")
        return self._vectors

    # ── Lifecycle ──────────────────────────────────────────────────────

    def initialize(self, config: dict[str, Any] | None = None) -> None:
        """Initialise all memory sub-systems.

        Args:
            config: Optional override dict (currently unused; sub-system
                    paths come from ``settings``).
        """
        if self._initialized:
            return
        self._context = ContextManager()
        self._sessions = SessionManager()
        self._checkpoints = CheckpointManager()
        self._vectors = VectorStore()
        self._initialized = True
        logger.info("MemorySystem initialised")

    def shutdown(self) -> None:
        """Gracefully shut down all memory sub-systems.

        Currently a no-op; future versions may flush buffers or close
        connections here.
        """
        self._initialized = False
        self._context = None
        self._sessions = None
        self._checkpoints = None
        self._vectors = None
        logger.info("MemorySystem shut down")


__all__ = [
    "MemorySystem",
    "ContextManager",
    "TokenBudgetExceeded",
    "SessionManager",
    "SessionData",
    "CheckpointManager",
    "CheckpointError",
    "VectorStore",
    "ConversationHistory",
]
