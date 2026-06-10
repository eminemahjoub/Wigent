from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SKIP_DIRS: set[str] = {
    "node_modules", ".git", "venv", ".venv", "__pycache__",
    "dist", "build", ".next", ".nuxt", ".turbo",
    "target", ".gradle", ".mvn",
    ".idea", ".vscode", ".env", ".agent",
    ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "bower_components", ".cache", "coverage",
}

SKIP_EXTENSIONS: set[str] = {
    ".lock", ".min.js", ".min.css",
    ".pyc", ".pyo", ".pyd",
    ".so", ".dll", ".dylib",
    ".exe", ".bin", ".out",
    ".o", ".obj", ".class",
    ".map", ".map.js",
    ".log",
}

SKIP_FILES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    ".DS_Store", "Thumbs.db",
}

SOURCE_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".md", ".rst",
    ".json", ".yaml", ".yml", ".toml",
    ".css", ".scss", ".less",
    ".html", ".htm",
    ".rs", ".go", ".java", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp",
    ".vue", ".svelte",
    ".sh", ".bash", ".zsh",
    ".sql",
    ".graphql", ".gql",
    ".proto",
}

MAX_FILE_SIZE = 1_000_000  # 1MB


@dataclass
class IndexResult:
    total_files: int = 0
    indexed_files: int = 0
    skipped_files: int = 0
    total_chunks: int = 0
    index_size_mb: float = 0.0
    elapsed_seconds: float = 0.0


@dataclass
class IndexStatus:
    last_indexed: datetime | None = None
    is_indexing: bool = False
    is_stale: bool = True
    needs_reindex: bool = True


class AutoIndexer:
    def __init__(self, vector_store: Any | None = None) -> None:
        self._vector_store = vector_store
        self._workspace_path: Path | None = None
        self._status = IndexStatus()
        self._lock = threading.Lock()
        self._background_thread: threading.Thread | None = None
        self._result: IndexResult = IndexResult()
        self._file_mtimes: dict[str, float] = {}
        self._stop_background = threading.Event()

    def index_on_startup(
        self,
        workspace: str | Path,
        background: bool = True,
    ) -> IndexResult:
        self._workspace_path = Path(workspace).resolve()
        self._result = IndexResult()

        if not self._workspace_path.is_dir():
            logger.warning("Workspace not found: %s", workspace)
            return self._result

        if background:
            self._stop_background.clear()
            self._background_thread = threading.Thread(
                target=self._index_in_background,
                daemon=True,
            )
            self._background_thread.start()
            return IndexResult()

        return self._index_sync()

    def _index_in_background(self) -> None:
        with self._lock:
            self._status.is_indexing = True
        try:
            result = self._index_sync()
            with self._lock:
                self._result = result
                self._status.is_indexing = False
                self._status.is_stale = False
                self._status.needs_reindex = False
                self._status.last_indexed = datetime.now(timezone.utc)
            logger.info(
                "Background index: %d files indexed (%d skipped) in %.1fs",
                result.indexed_files, result.skipped_files, result.elapsed_seconds,
            )
        except Exception as exc:
            with self._lock:
                self._status.is_indexing = False
            logger.error("Background indexing failed: %s", exc)

    def _index_sync(self) -> IndexResult:
        if not self._workspace_path:
            return IndexResult()

        start = time.monotonic()
        root = self._workspace_path
        total = 0
        indexed = 0
        skipped = 0
        chunks = 0

        for filepath in root.rglob("*"):
            if self._stop_background.is_set():
                break
            if not filepath.is_file():
                continue

            total += 1

            rel = filepath.relative_to(root)
            parts = rel.parts

            if any(p in SKIP_DIRS for p in parts):
                skipped += 1
                continue

            if filepath.suffix.lower() in SKIP_EXTENSIONS:
                skipped += 1
                continue

            if filepath.name in SKIP_FILES:
                skipped += 1
                continue

            if filepath.suffix.lower() not in SOURCE_EXTENSIONS:
                skipped += 1
                continue

            try:
                size = filepath.stat().st_size
                if size > MAX_FILE_SIZE:
                    skipped += 1
                    continue
            except OSError:
                skipped += 1
                continue

            indexed += 1
            self._file_mtimes[str(rel)] = os.path.getmtime(str(filepath))

            if self._vector_store is not None and hasattr(self._vector_store, "add_document"):
                try:
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    self._vector_store.add_document(
                        content,
                        metadata={"file": str(rel), "size": size},
                    )
                    chunks += 1
                except Exception:
                    pass

        elapsed = time.monotonic() - start
        index_size = 0.0
        if chunks and self._vector_store is not None:
            index_size = chunks * 0.0001

        return IndexResult(
            total_files=total,
            indexed_files=indexed,
            skipped_files=skipped,
            total_chunks=chunks,
            index_size_mb=round(index_size, 2),
            elapsed_seconds=round(elapsed, 2),
        )

    def get_index_status(self) -> IndexStatus:
        with self._lock:
            return IndexStatus(
                last_indexed=self._status.last_indexed,
                is_indexing=self._status.is_indexing,
                is_stale=self._status.is_stale,
                needs_reindex=self._status.needs_reindex,
            )

    def reindex_if_stale(self) -> bool:
        status = self.get_index_status()
        if status.needs_reindex or status.is_stale:
            self.index_on_startup(
                str(self._workspace_path) if self._workspace_path else "",
                background=False,
            )
            return True
        return False

    def track_file_changes(self) -> list[Path]:
        if not self._workspace_path:
            return []

        changed: list[Path] = []
        root = self._workspace_path
        current_mtimes: dict[str, float] = {}

        for filepath in root.rglob("*"):
            if not filepath.is_file():
                continue
            rel = str(filepath.relative_to(root))
            try:
                mtime = os.path.getmtime(str(filepath))
                current_mtimes[rel] = mtime
            except OSError:
                continue

            old_mtime = self._file_mtimes.get(rel)
            if old_mtime is None or mtime > old_mtime:
                changed.append(filepath)

        self._file_mtimes = current_mtimes
        return changed

    def clear_index(self) -> bool:
        self._stop_background.set()
        with self._lock:
            self._file_mtimes.clear()
            self._status = IndexStatus()
            self._result = IndexResult()
        if self._vector_store is not None and hasattr(self._vector_store, "clear_index"):
            try:
                self._vector_store.clear_index()
            except Exception:
                pass
        return True


__all__ = [
    "IndexResult",
    "IndexStatus",
    "AutoIndexer",
]
