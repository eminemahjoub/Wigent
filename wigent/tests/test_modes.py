from __future__ import annotations

import pytest

# Bypass wigent/__init__.py — import mode config directly.
from wigent.config.modes import (
    AgentModeConfig,
    MODES,
    ORCHESTRATOR,
    ARCHITECT,
    CODER,
    DEBUGGER,
    REVIEWER,
    get_mode,
    list_modes,
)


# ── Mode Definitions ────────────────────────────────────────────────────

class TestModeDefinitions:
    def test_five_modes_registered(self):
        assert len(MODES) == 5

    def test_mode_names(self):
        assert set(MODES.keys()) == {"orchestrator", "architect", "coder", "debugger", "reviewer"}

    def test_orchestrator_properties(self):
        assert ORCHESTRATOR.name == "orchestrator"
        assert ORCHESTRATOR.emoji == "🧠"
        assert ORCHESTRATOR.temperature == 0.7
        assert ORCHESTRATOR.max_iterations == 50
        assert "write_file" in ORCHESTRATOR.allowed_tools

    def test_architect_properties(self):
        assert ARCHITECT.name == "architect"
        assert ARCHITECT.emoji == "🏛️"
        assert ARCHITECT.temperature == 0.5
        assert ARCHITECT.max_iterations == 30
        assert "write_file" not in ARCHITECT.allowed_tools
        assert "read_file" in ARCHITECT.allowed_tools

    def test_coder_properties(self):
        assert CODER.name == "coder"
        assert CODER.emoji == "💻"
        assert CODER.temperature == 0.6
        assert CODER.max_iterations == 40
        assert "write_file" in CODER.allowed_tools
        assert "run_command" in CODER.allowed_tools

    def test_debugger_properties(self):
        assert DEBUGGER.name == "debugger"
        assert DEBUGGER.emoji == "🔍"
        assert DEBUGGER.temperature == 0.3
        assert DEBUGGER.max_iterations == 30
        assert "run_command" in DEBUGGER.allowed_tools
        assert "list_files" not in DEBUGGER.allowed_tools

    def test_reviewer_properties(self):
        assert REVIEWER.name == "reviewer"
        assert REVIEWER.emoji == "👁️"
        assert REVIEWER.temperature == 0.4
        assert REVIEWER.max_iterations == 20
        assert "write_file" not in REVIEWER.allowed_tools
        assert "read_file" in REVIEWER.allowed_tools

    def test_all_modes_have_prompt_files(self):
        for name, cfg in MODES.items():
            assert cfg.system_prompt_file == f"{name}.md", f"{name} missing prompt file"

    def test_architect_is_read_only(self):
        write_tools = {"write_file", "run_command"}
        assert not (write_tools & set(ARCHITECT.allowed_tools))

    def test_reviewer_is_read_only(self):
        write_tools = {"write_file", "run_command"}
        assert not (write_tools & set(REVIEWER.allowed_tools))


class TestModeConfigImmutability:
    def test_cannot_modify_name(self):
        with pytest.raises(Exception):
            ARCHITECT.name = "hacker"  # type: ignore[misc]

    def test_cannot_modify_tools(self):
        with pytest.raises(Exception):
            ORCHESTRATOR.allowed_tools = ()  # type: ignore[misc]


# ── Mode Lookup ─────────────────────────────────────────────────────────

class TestGetMode:
    def test_get_mode_known(self):
        cfg = get_mode("coder")
        assert cfg is CODER
        assert cfg.name == "coder"

    def test_get_mode_case_sensitive(self):
        with pytest.raises(KeyError):
            get_mode("Coder")

    def test_get_mode_unknown(self):
        with pytest.raises(KeyError):
            get_mode("hacker")

    def test_get_mode_all_roundtrip(self):
        for name in MODES:
            assert get_mode(name).name == name


class TestListModes:
    def test_list_modes_returns_all(self):
        result = list_modes()
        assert len(result) == 5

    def test_list_modes_keys(self):
        result = list_modes()
        for entry in result:
            assert "name" in entry
            assert "emoji" in entry
            assert "description" in entry
            assert "tools" in entry
            assert isinstance(entry["tools"], list)

    def test_list_modes_no_write_for_architect(self):
        result = list_modes()
        arch = [m for m in result if m["name"] == "architect"][0]
        assert "write_file" not in arch["tools"]


# ── Tool Set Integrity ──────────────────────────────────────────────────

class TestToolSets:
    def test_all_tools_includes_write(self):
        assert "write_file" in ORCHESTRATOR.allowed_tools

    def test_planning_excludes_write(self):
        write_tools = {"write_file", "stage_files", "unstage_files", "commit",
                       "create_branch", "stash_changes", "pop_stash", "run_command"}
        assert not (write_tools & set(ARCHITECT.allowed_tools))

    def test_coding_includes_git_write(self):
        assert "commit" in CODER.allowed_tools
        assert "stage_files" in CODER.allowed_tools

    def test_review_excludes_write(self):
        write_tools = {"write_file", "stage_files", "unstage_files", "commit",
                       "create_branch", "stash_changes", "pop_stash", "run_command"}
        assert not (write_tools & set(REVIEWER.allowed_tools))

    def test_git_read_tools_in_all_modes(self):
        for name, cfg in MODES.items():
            if "get_status" not in cfg.allowed_tools:
                pytest.fail(f"{name} missing get_status")


# ── Settings Default ────────────────────────────────────────────────────

class TestDefaultMode:
    def test_default_mode_is_orchestrator(self):
        from wigent.config import settings
        assert settings.DEFAULT_MODE == "orchestrator"
