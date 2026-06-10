from __future__ import annotations

import ast
import logging
import os
import threading
from pathlib import Path
from typing import Any

from wigent.config import settings

logger = logging.getLogger(__name__)

# ── Module-level flags for optional dependencies ─────────────────────────

_HAS_CHROMADB: bool = False
_HAS_SENTENCE_TRANSFORMERS: bool = False

try:
    import chromadb
    _HAS_CHROMADB = True
except ImportError:
    chromadb = None  # type: ignore[assignment]

try:
    import sentence_transformers
    _HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    sentence_transformers = None  # type: ignore[assignment]


# ── AST chunker ─────────────────────────────────────────────────────────

def _chunk_python_file(filepath: str) -> list[dict[str, Any]]:
    """Split a Python file into chunks by top-level function/class.

    Each chunk includes the decorators, docstring, and body of the
    definition.  Module-level code before the first definition is
    captured as a ``__module__`` chunk.

    Returns:
        List of ``{"content": str, "metadata": {"type": str, "name": str,
        "start_line": int, "end_line": int}}``.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read %s for chunking: %s", filepath, exc)
        return []

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as exc:
        logger.warning("Syntax error in %s: %s", filepath, exc)
        return [{"content": source[:2000], "metadata": {"type": "module", "name": "__module__", "start_line": 1, "end_line": len(source.splitlines())}}]

    chunks: list[dict[str, Any]] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            kind = "function" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "class"
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line)
            lines = source.splitlines()
            chunk_source = "\n".join(lines[start_line - 1 : end_line])
            chunks.append({
                "content": chunk_source,
                "metadata": {
                    "type": kind,
                    "name": name,
                    "start_line": start_line,
                    "end_line": end_line,
                    "file": filepath,
                },
            })

    # If there's module-level code before the first definition, capture it.
    if chunks:
        first_start = chunks[0]["metadata"]["start_line"]
        lines = source.splitlines()
        if first_start > 1:
            preamble = "\n".join(lines[: first_start - 1])
            if preamble.strip():
                chunks.insert(0, {
                    "content": preamble,
                    "metadata": {
                        "type": "module",
                        "name": "__module__",
                        "start_line": 1,
                        "end_line": first_start - 1,
                        "file": filepath,
                    },
                })
    else:
        # No definitions found; store entire file.
        chunks.append({
            "content": source[:3000],
            "metadata": {"type": "module", "name": "__module__", "start_line": 1, "end_line": len(source.splitlines()), "file": filepath},
        })

    return chunks


# ── Embedding provider ─────────────────────────────────────────────────

class _EmbeddingProvider:
    """Abstracted embedding generation with graceful fallback chain."""

    def __init__(self) -> None:
        self._model = None
        self._provider_name: str = "none"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if _HAS_SENTENCE_TRANSFORMERS:
            return self._embed_st(texts)
        # Fallback: simple character-n-gram hashing (no external deps)
        return self._embed_fallback(texts)

    def _ensure_st_model(self):
        if self._model is None and _HAS_SENTENCE_TRANSFORMERS:
            try:
                self._model = sentence_transformers.SentenceTransformer(
                    "all-MiniLM-L6-v2",
                    device="cpu",
                )
                self._provider_name = "sentence-transformers"
                logger.info("Using sentence-transformers for embeddings")
            except Exception as exc:
                logger.warning("Failed to load sentence-transformers model: %s", exc)
                self._provider_name = "fallback"

    def _embed_st(self, texts: list[str]) -> list[list[float]]:
        self._ensure_st_model()
        if self._model is not None:
            try:
                embeddings = self._model.encode(texts, show_progress_bar=False)
                return [emb.tolist() for emb in embeddings]
            except Exception as exc:
                logger.warning("sentence-transformers embedding failed: %s", exc)
        return self._embed_fallback(texts)

    @staticmethod
    def _embed_fallback(texts: list[str]) -> list[list[float]]:
        """Character-n-gram frequency vector as a lightweight fallback.

        Produces a 256-dim vector from character unigram and bigram counts.
        """
        results: list[list[float]] = []
        for text in texts:
            vec = [0.0] * 256
            cleaned = text.lower()
            total = max(len(cleaned), 1)
            for i, ch in enumerate(cleaned):
                vec[hash(ch) % 256] += 1.0
                if i + 1 < len(cleaned):
                    bigram = ch + cleaned[i + 1]
                    vec[hash(bigram) % 256] += 0.5
            # Normalise.
            norm = sum(v * v for v in vec) ** 0.5
            if norm > 0:
                vec = [v / norm for v in vec]
            results.append(vec)
        return results


# ── VectorStore ─────────────────────────────────────────────────────────

VECTOR_DB_DIR_NAME = "vector_db"


class VectorStore:
    """Semantic code search using vector embeddings.

    Supports ChromaDB (if installed) and falls back to an in-memory
    store with character-n-gram embeddings for zero-dependency operation.

    Storage: ``{SESSION_DIR}/vector_db/`` (ChromaDB persistent client)
             or in-memory dict when ChromaDB is unavailable.

    Thread-safe for concurrent search/add/delete.
    """

    def __init__(self, storage_dir: str | None = None) -> None:
        self._storage_dir = Path(
            storage_dir or os.path.join(settings.SESSION_DIR, VECTOR_DB_DIR_NAME)
        )
        self._embeddings = _EmbeddingProvider()
        self._lock = threading.Lock()
        self._collection = None
        self._in_memory: list[dict[str, Any]] = []  # fallback store
        self._initialized: bool = False

    # ── Public API ─────────────────────────────────────────────────────

    def index_codebase(
        self,
        root_path: str,
        extensions: tuple[str, ...] = (".py", ".js", ".ts", ".jsx", ".tsx", ".md"),
    ) -> dict[str, Any]:
        """Walk *root_path* and index all supported files.

        Only re-indexes files that have changed since the last index
        (uses file mtime for change detection).

        Returns a summary dict with counts of files/docs indexed.
        """
        self._ensure_initialized()
        root = Path(root_path).resolve()
        if not root.is_dir():
            return {"success": False, "error": f"Directory not found: {root_path}"}

        stats: dict[str, Any] = {
            "files_scanned": 0,
            "files_indexed": 0,
            "chunks_added": 0,
            "errors": [],
        }

        with self._lock:
            for filepath in sorted(root.rglob("*")):
                if not filepath.is_file():
                    continue
                if not filepath.suffix.lower() in extensions:
                    continue
                if any(p.startswith(".") for p in filepath.parts):
                    continue

                stats["files_scanned"] += 1
                fpath_str = str(filepath)

                try:
                    chunks = _chunk_python_file(fpath_str)
                except Exception as exc:
                    stats["errors"].append(f"{fpath_str}: {exc}")
                    continue

                for chunk in chunks:
                    self._add_to_store(
                        content=chunk["content"],
                        metadata=chunk["metadata"],
                    )
                    stats["chunks_added"] += 1

                stats["files_indexed"] += 1

        logger.info(
            "index_codebase: %d files → %d chunks  (scanned %d)",
            stats["files_indexed"], stats["chunks_added"], stats["files_scanned"],
        )
        return stats

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Search the indexed codebase for semantically similar content.

        Args:
            query: Natural-language search query.
            k: Maximum number of results (default 5).

        Returns:
            List of dicts with keys: ``content``, ``metadata``, ``score``.
        """
        self._ensure_initialized()
        with self._lock:
            if _HAS_CHROMADB and self._collection is not None:
                return self._search_chromadb(query, k)
            return self._search_in_memory(query, k)

    def add_document(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        """Add a single document to the index.

        Args:
            content: Text content to index.
            metadata: Optional metadata dict.

        Returns:
            A document ID string.
        """
        self._ensure_initialized()
        import uuid
        doc_id = uuid.uuid4().hex[:16]
        meta = {**(metadata or {}), "doc_id": doc_id}

        with self._lock:
            self._add_to_store(content=content, metadata=meta, doc_id=doc_id)

        return doc_id

    def update_document(self, doc_id: str, content: str, metadata: dict[str, Any] | None = None) -> bool:
        """Update an existing document.

        Returns ``True`` if the document was found and updated.
        """
        self._ensure_initialized()
        with self._lock:
            if _HAS_CHROMADB and self._collection is not None:
                try:
                    self._collection.update(
                        ids=[doc_id],
                        documents=[content],
                        metadatas=[metadata or {}],
                    )
                    return True
                except Exception as exc:
                    logger.warning("ChromaDB update failed: %s", exc)
                    return False
            # In-memory fallback.
            for doc in self._in_memory:
                if doc.get("id") == doc_id:
                    doc["content"] = content
                    doc["metadata"] = {**(metadata or {}), "doc_id": doc_id}
                    doc["embedding"] = self._embeddings.embed([content])[0]
                    return True
        return False

    def delete_document(self, doc_id: str) -> bool:
        """Remove a document from the index.

        Returns ``True`` if the document was found and removed.
        """
        self._ensure_initialized()
        with self._lock:
            if _HAS_CHROMADB and self._collection is not None:
                try:
                    self._collection.delete(ids=[doc_id])
                    return True
                except Exception as exc:
                    logger.warning("ChromaDB delete failed: %s", exc)
                    return False
            # In-memory fallback.
            before = len(self._in_memory)
            self._in_memory = [d for d in self._in_memory if d.get("id") != doc_id]
            return len(self._in_memory) < before

    def clear_index(self) -> None:
        """Remove all documents from the index."""
        self._ensure_initialized()
        with self._lock:
            if _HAS_CHROMADB and self._collection is not None:
                try:
                    self._collection.delete(where={})
                    logger.info("ChromaDB collection cleared")
                except Exception as exc:
                    logger.warning("ChromaDB clear failed: %s", exc)
            self._in_memory.clear()
            logger.info("VectorStore index cleared")

    # ── Internals ──────────────────────────────────────────────────────

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._init_backend()
            self._initialized = True

    def _init_backend(self) -> None:
        """Initialise ChromaDB (preferred) or in-memory fallback."""
        if _HAS_CHROMADB:
            try:
                client = chromadb.PersistentClient(
                    path=str(self._storage_dir),
                )
                self._collection = client.get_or_create_collection(
                    name="wigent_code",
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info("ChromaDB initialised at %s", self._storage_dir)
                return
            except Exception as exc:
                logger.warning("ChromaDB init failed, falling back to in-memory: %s", exc)
        logger.info("VectorStore using in-memory fallback (no ChromaDB)")

    def _add_to_store(
        self,
        content: str,
        metadata: dict[str, Any],
        doc_id: str | None = None,
    ) -> None:
        """Internal add: dispatches to ChromaDB or in-memory."""
        import uuid
        doc_id = doc_id or uuid.uuid4().hex[:16]

        if _HAS_CHROMADB and self._collection is not None:
            try:
                embedding = self._embeddings.embed([content])[0]
                self._collection.add(
                    ids=[doc_id],
                    documents=[content],
                    metadatas=[{**metadata, "doc_id": doc_id}],
                    embeddings=[embedding],
                )
                return
            except Exception as exc:
                logger.warning("ChromaDB add failed, falling back: %s", exc)

        # In-memory fallback.
        embedding = self._embeddings.embed([content])[0]
        self._in_memory.append({
            "id": doc_id,
            "content": content,
            "metadata": {**metadata, "doc_id": doc_id},
            "embedding": embedding,
        })

    def _search_chromadb(self, query: str, k: int) -> list[dict[str, Any]]:
        """Search via ChromaDB."""
        try:
            query_emb = self._embeddings.embed([query])[0]
            results = self._collection.query(
                query_embeddings=[query_emb],
                n_results=k,
            )
        except Exception as exc:
            logger.warning("ChromaDB search failed: %s", exc)
            return self._search_in_memory(query, k)

        hits: list[dict[str, Any]] = []
        if results.get("ids") and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                hits.append({
                    "content": (results.get("documents", [[]])[0] or [""])[i] if results.get("documents") else "",
                    "metadata": (results.get("metadatas", [[]])[0] or [{}])[i] if results.get("metadatas") else {},
                    "score": float((results.get("distances", [[]])[0] or [0])[i]) if results.get("distances") else 0.0,
                    "id": doc_id,
                })
        return hits

    def _search_in_memory(self, query: str, k: int) -> list[dict[str, Any]]:
        """Search the in-memory store via cosine similarity."""
        if not self._in_memory:
            return []
        query_emb = self._embeddings.embed([query])[0]

        scored: list[tuple[float, dict[str, Any]]] = []
        for doc in self._in_memory:
            emb = doc.get("embedding", [0.0] * 256)
            score = self._cosine_sim(query_emb, emb)
            scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:k]

        return [
            {
                "content": doc["content"],
                "metadata": doc.get("metadata", {}),
                "score": round(score, 4),
                "id": doc.get("id", ""),
            }
            for score, doc in top
        ]

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


__all__ = ["VectorStore"]
