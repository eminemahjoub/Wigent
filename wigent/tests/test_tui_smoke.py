# ════════════════════════════════════════
# wigent — TUI Smoke Tests
# Role: Quick sanity checks for Textual TUI
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Smoke tests for the Textual TUI components."""

from __future__ import annotations


def test_tui_imports():
    """Smoke: TUI app and widgets can be imported."""
    from wigent.cli.tui_app import WigentTUI
    from wigent.cli.tui_widgets.status_bar import StatusBar
    from wigent.cli.tui_widgets.file_tree import WigentFileTree
    from wigent.cli.tui_widgets.help_modal import HelpModal
    assert WigentTUI is not None
    assert StatusBar is not None
    assert WigentFileTree is not None
    assert HelpModal is not None


def test_tui_bindings():
    """Smoke: TUI has keyboard bindings defined."""
    from wigent.cli.tui_app import WigentTUI
    bindings = WigentTUI.BINDINGS
    assert len(bindings) > 0
    keys = [b.key for b in bindings]
    assert "f1" in keys
    assert "f3" in keys


def test_status_bar_widget():
    """Smoke: Status bar widget initializes and updates."""
    from wigent.cli.tui_widgets.status_bar import StatusBar
    bar = StatusBar()
    assert bar.mode == "orchestrator"
    bar.update_info(mode="coder", model="gpt-4o", tokens=100, cost=0.01)
    assert bar.mode == "coder"
    assert bar.model == "gpt-4o"
    assert bar.tokens == 100
    assert bar.cost == 0.01


def test_file_tree_widget():
    """Smoke: File tree widget initializes."""
    from wigent.cli.tui_widgets.file_tree import WigentFileTree
    tree = WigentFileTree(".")
    assert tree is not None


def test_help_modal():
    """Smoke: Help modal has content."""
    from wigent.cli.tui_widgets.help_modal import HelpModal
    assert "F1" in HelpModal.HELP_TEXT
    assert "/help" in HelpModal.HELP_TEXT


def test_app_reactive_state():
    """Smoke: TUI reactive state attributes exist."""
    from wigent.cli.tui_app import WigentTUI
    assert hasattr(WigentTUI, "sidebar_visible")
    assert hasattr(WigentTUI, "current_mode")
    assert hasattr(WigentTUI, "current_model")
    assert hasattr(WigentTUI, "token_count")
    assert hasattr(WigentTUI, "session_cost")


__all__: list[str] = []
