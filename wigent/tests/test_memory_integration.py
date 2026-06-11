"""Integration tests for the wigent memory system (Phase 4).

These tests import memory sub-modules directly (bypassing ``wigent/__init__.py``
to avoid the ``google.generativeai`` import hang).
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

# Bypass wigent/__init__.py to avoid model import chain.
from wigent.memory.context_manager import ContextManager, TokenBudgetExceeded
from wigent.memory.session import SessionManager, SessionData
from wigent.memory.checkpoints import CheckpointManager, CheckpointError
from wigent.memory.vector_store import VectorStore


# ── Helpers ─────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_storage():
    """Yield a temp directory path, then clean up."""
    path = tempfile.mkdtemp(prefix="wigent_mem_test_")
    yield path
    import shutil
    shutil.rmtree(path, ignore_errors=True)


# ── 1. ContextManager ──────────────────────────────────────────────────

class TestContextManager:
    def test_add_and_get_messages(self):
        cm = ContextManager(max_tokens=10000)
        cm.add_message("user", "hello")
        cm.add_message("assistant", "world")
        msgs = cm.get_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["content"] == "world"

    def test_count_tokens_empty(self):
        cm = ContextManager(max_tokens=10000)
        count = cm.count_tokens([])
        assert count >= 0

    def test_system_prompt_injection(self):
        cm = ContextManager(max_tokens=10000)
        cm.inject_system_prompt("You are a helpful assistant.")
        cm.add_message("user", "hi")
        msgs = cm.get_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "helpful assistant" in msgs[0]["content"]

    def test_get_stats(self):
        cm = ContextManager(max_tokens=10000)
        cm.add_message("user", "a" * 100)
        stats = cm.get_stats()
        assert stats["total_messages"] == 1
        assert stats["estimated_tokens"] > 0
        assert stats["budget_used_pct"] < 100

    def test_clear(self):
        cm = ContextManager(max_tokens=10000)
        cm.add_message("user", "hello")
        cm.clear()
        assert len(cm.get_messages()) == 0

    def test_keeps_last_n_on_trim(self):
        cm = ContextManager(max_tokens=10000)
        for i in range(20):
            cm.add_message("user", f"msg_{i}")
        before = len(cm.get_messages())
        removed = cm.trim_to_budget(budget=50)  # tiny budget forces aggressive trim
        assert removed >= 0
        # Should keep at least the last K_LAST_N = 5
        remaining = cm.get_messages()
        assert len(remaining) > 0

    def test_token_budget_exceeded(self):
        cm = ContextManager(max_tokens=100)
        with pytest.raises(TokenBudgetExceeded):
            cm.add_message("user", "x" * 20000)


# ── 2. SessionManager ──────────────────────────────────────────────────

class TestSessionManager:
    def test_create_and_load(self, tmp_storage):
        sm = SessionManager(storage_dir=tmp_storage)
        s = sm.create_session(name="test_sesh", description="unit test", tags=["test"])
        assert s.name == "test_sesh"
        loaded = sm.load_session("test_sesh")
        assert loaded is not None
        assert loaded.description == "unit test"
        assert "test" in loaded.tags

    def test_save_updates_timestamp(self, tmp_storage):
        sm = SessionManager(storage_dir=tmp_storage)
        s = sm.create_session(name="ts_test")
        old_updated = s.updated_at
        s.total_tokens = 500
        sm.save_session(s)
        loaded = sm.load_session("ts_test")
        assert loaded.total_tokens == 500
        assert loaded.updated_at >= old_updated

    def test_list_sessions(self, tmp_storage):
        sm = SessionManager(storage_dir=tmp_storage)
        sm.create_session(name="a", tags=["t1"])
        sm.create_session(name="b", tags=["t2"])
        sm.create_session(name="c", tags=["t3"])
        lst = sm.list_sessions()
        names = [s["name"] for s in lst]
        assert "a" in names
        assert "b" in names
        assert "c" in names
        for entry in lst:
            assert "message_count" in entry
            assert "total_tokens" in entry

    def test_delete_session(self, tmp_storage):
        sm = SessionManager(storage_dir=tmp_storage)
        sm.create_session(name="delete_me")
        assert sm.load_session("delete_me") is not None
        assert sm.delete_session("delete_me") is True
        assert sm.load_session("delete_me") is None
        assert sm.delete_session("nonexistent") is False

    def test_export_json(self, tmp_storage):
        sm = SessionManager(storage_dir=tmp_storage)
        s = sm.create_session(name="export_test")
        s.messages.append({"role": "user", "content": "hello"})
        sm.save_session(s)
        exported = sm.export_session("export_test", fmt="json")
        assert exported is not None
        data = json.loads(exported)
        assert data["name"] == "export_test"

    def test_export_markdown(self, tmp_storage):
        sm = SessionManager(storage_dir=tmp_storage)
        s = sm.create_session(name="md_test")
        s.messages.append({"role": "user", "content": "hello"})
        sm.save_session(s)
        md = sm.export_session("md_test", fmt="md")
        assert md is not None
        assert "# Session: md_test" in md
        assert "USER" in md

    def test_get_summary(self, tmp_storage):
        sm = SessionManager(storage_dir=tmp_storage)
        s = sm.create_session(name="summary_test", description="desc")
        s.messages.append({"role": "user", "content": "msg"})
        s.total_tokens = 100
        sm.save_session(s)
        summary = sm.get_session_summary("summary_test")
        assert summary is not None
        assert summary["description"] == "desc"
        assert summary["total_tokens"] == 100
        assert summary["message_count"] == 1


# ── 3. CheckpointManager ──────────────────────────────────────────────

class TestCheckpointManager:
    def test_create_and_list(self, tmp_storage):
        ck = CheckpointManager(storage_dir=os.path.join(tmp_storage, "ckpts"))
        meta = ck.create_checkpoint(label="test_ckpt", agent_state={"mode": "coder"})
        cid = meta["id"]
        assert meta["label"] == "test_ckpt"
        lst = ck.list_checkpoints()
        ids = [c["id"] for c in lst]
        assert cid in ids

    def test_restore_agent_state(self, tmp_storage):
        ck = CheckpointManager(storage_dir=os.path.join(tmp_storage, "ckpts"))
        orig = {"mode": "debugger", "iteration": 5}
        meta = ck.create_checkpoint(label="restore_test", agent_state=orig)
        restored = ck.restore_checkpoint(meta["id"])
        assert restored["agent_state"] == orig

    def test_delete_checkpoint(self, tmp_storage):
        ck = CheckpointManager(storage_dir=os.path.join(tmp_storage, "ckpts"))
        meta = ck.create_checkpoint(label="delete_me")
        assert ck.delete_checkpoint(meta["id"]) is True
        assert ck.delete_checkpoint("nonexistent") is False

    def test_diff_checkpoints(self, tmp_storage):
        ck = CheckpointManager(storage_dir=os.path.join(tmp_storage, "ckpts"))
        m1 = ck.create_checkpoint(label="v1", files_snapshot={"a.py": "print(1)"})
        m2 = ck.create_checkpoint(label="v2", files_snapshot={"a.py": "print(2)"})
        diffs = ck.diff_checkpoints(m1["id"], m2["id"])
        assert len(diffs) >= 1
        assert diffs[0]["file"] == "a.py"
        assert "+print(2)" in diffs[0]["diff"] or "print(2)" in diffs[0]["diff"]

    def test_auto_checkpoint_flag(self, tmp_storage):
        ck = CheckpointManager(storage_dir=os.path.join(tmp_storage, "ckpts"))
        auto_meta = ck.auto_checkpoint(label="auto_test")
        assert auto_meta["auto"] is True
        manual_meta = ck.create_checkpoint(label="manual_test")
        assert manual_meta["auto"] is False

    def test_cleanup_old(self, tmp_storage):
        ck = CheckpointManager(storage_dir=os.path.join(tmp_storage, "ckpts"))
        for i in range(15):
            ck.auto_checkpoint(label=f"auto_{i}")
        removed = ck.cleanup_old(keep_last=5)
        remaining = ck.list_checkpoints()
        auto_count = sum(1 for c in remaining if c.get("auto"))
        assert auto_count <= 5
        assert removed >= 10

    def test_checkpoint_not_found(self, tmp_storage):
        ck = CheckpointManager(storage_dir=os.path.join(tmp_storage, "ckpts"))
        with pytest.raises(CheckpointError):
            ck.restore_checkpoint("nonexistent")


# ── 4. VectorStore ─────────────────────────────────────────────────────

class TestVectorStore:
    def test_add_and_search(self, tmp_storage):
        vs = VectorStore(storage_dir=os.path.join(tmp_storage, "vecdb"))
        did = vs.add_document("def hello(): print('world')", {"file": "greet.py"})
        assert did is not None
        results = vs.search("hello world", k=3)
        assert len(results) >= 1
        assert results[0]["metadata"]["file"] == "greet.py"

    def test_update_document(self, tmp_storage):
        vs = VectorStore(storage_dir=os.path.join(tmp_storage, "vecdb"))
        did = vs.add_document("old content", {"file": "f.py"})
        assert vs.update_document(did, "new content") is True
        assert vs.update_document("nonexistent", "x") is False

    def test_delete_document(self, tmp_storage):
        vs = VectorStore(storage_dir=os.path.join(tmp_storage, "vecdb"))
        did = vs.add_document("content", {"file": "f.py"})
        assert vs.delete_document(did) is True
        assert vs.delete_document("nonexistent") is False

    def test_clear_index(self, tmp_storage):
        vs = VectorStore(storage_dir=os.path.join(tmp_storage, "vecdb"))
        vs.add_document("doc1", {})
        vs.add_document("doc2", {})
        vs.clear_index()
        results = vs.search("anything", k=10)
        assert len(results) == 0

    def test_index_codebase(self, tmp_storage):
        vs = VectorStore(storage_dir=os.path.join(tmp_storage, "vecdb"))
        src = os.path.join(tmp_storage, "src")
        os.makedirs(src)
        Path(os.path.join(src, "math_util.py")).write_text(
            "def add(a, b): return a + b\nclass Calc: pass\n"
        )
        Path(os.path.join(src, "README.md")).write_text("# Test Project\n")
        stats = vs.index_codebase(src)
        assert stats["files_scanned"] >= 2
        assert stats["chunks_added"] >= 2
        assert stats["errors"] == []


# ── 5. MemorySystem facade ─────────────────────────────────────────────

class TestMemorySystemFacade:
    def test_initializes(self):
        from wigent.memory import MemorySystem
        mem = MemorySystem()
        assert mem._context is None  # pre-init
        mem.initialize()
        assert mem.context is not None
        assert mem.sessions is not None
        assert mem.checkpoints is not None
        assert mem.vectors is not None

    def test_shutdown(self):
        from wigent.memory import MemorySystem
        mem = MemorySystem()
        mem.initialize()
        mem.shutdown()
        with pytest.raises(RuntimeError):
            _ = mem.context

    def test_property_guards(self):
        from wigent.memory import MemorySystem
        mem = MemorySystem()
        with pytest.raises(RuntimeError):
            _ = mem.context
        with pytest.raises(RuntimeError):
            _ = mem.sessions
        with pytest.raises(RuntimeError):
            _ = mem.checkpoints
        with pytest.raises(RuntimeError):
            _ = mem.vectors
