from __future__ import annotations

from unittest.mock import MagicMock

from wigent.cli.ui_components import UIComponents
from wigent.cli.commands import CommandHandler, CommandResult, COMMAND_DEFINITIONS
from wigent.cli.input_handler import InputHandler, CommandCompleter
from wigent.cli.cli_args import parse_args
from wigent.cli.diff_display import DiffDisplay


def test_ui_components_imports():
    assert UIComponents is not None


def test_command_handler_imports():
    assert CommandHandler is not None
    assert CommandResult is not None


def test_input_handler_imports():
    assert InputHandler is not None
    assert CommandCompleter is not None


def test_cli_args_parses_version():
    import sys
    try:
        parse_args(["--version"])
    except SystemExit:
        pass


def test_cli_args_parses_help():
    import sys
    try:
        parse_args(["--help"])
    except SystemExit:
        pass


def test_cli_args_parses_no_args():
    result = parse_args([])
    assert result["prompt"] is None
    assert result["mode"] is None
    assert result["no_banner"] is False


def test_cli_args_parses_with_args():
    result = parse_args(["--mode", "coder", "--provider", "anthropic", "do something"])
    assert result["prompt"] == "do something"
    assert result["mode"] == "coder"
    assert result["provider"] == "anthropic"


def test_cli_args_flags():
    result = parse_args(["--no-banner", "--debug", "--yes"])
    assert result["no_banner"] is True
    assert result["debug"] is True
    assert result["yes"] is True


def test_banner_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_banner("0.6.0", "claude-3-5-sonnet", "orchestrator")
    ui.console.print.assert_called_once()


def test_status_bar_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    state = {
        "mode": "orchestrator",
        "model": "claude-3-5-sonnet",
        "tokens_used": 1234,
        "tokens_max": 200000,
        "cost": 0.012,
    }
    ui.print_status_bar(state)
    ui.console.print.assert_called_once()


def test_user_message_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_user_message("Hello")
    ui.console.print.assert_called_once()


def test_agent_message_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_agent_message("Response", "coder")
    ui.console.print.assert_called_once()


def test_error_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_error("Something broke", hint="Try again", recoverable=True)
    ui.console.print.assert_called_once()


def test_approval_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_approval_request("write file", "/tmp/test.txt", "low")
    ui.console.print.assert_called_once()


def test_tool_use_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_tool_use("read_file", {"path": "/tmp/test.txt"})
    ui.console.print.assert_called_once()


def test_tool_result_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_tool_result("read_file", "file contents", True)
    ui.console.print.assert_called_once()


def test_workspace_banner_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    info = {
        "project_type": "python",
        "framework": "fastapi",
        "language": "python",
        "package_manager": "pip",
        "has_git": False,
        "has_tests": True,
        "path": "/tmp/test-project",
    }
    ui.print_workspace_banner(info)
    ui.console.print.assert_called_once()


def test_workspace_banner_unknown():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_workspace_banner({"project_type": "unknown"})
    ui.console.print.assert_called_once()


def test_help_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_help(COMMAND_DEFINITIONS)
    ui.console.print.assert_called_once()


def test_mode_switch_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_mode_switch("orchestrator", "architect")
    ui.console.print.assert_called_once()


def test_interrupt_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_interrupt_message()
    ui.console.print.assert_called_once()


def test_command_result_renders():
    ui = UIComponents()
    ui.console = MagicMock()
    ui.print_command_result({"status": "ok", "message": "Done", "data": {}})
    ui.console.print.assert_called_once()


def test_command_handler_parses_help():
    handler = CommandHandler(MagicMock())
    result = handler.execute("/help")
    assert result.status == "ok"


def test_command_handler_parses_unknown():
    handler = CommandHandler(MagicMock())
    result = handler.execute("/nonexistent")
    assert result.status == "error"


def test_command_handler_mode():
    agent = MagicMock()
    agent._mode = "orchestrator"
    handler = CommandHandler(agent)
    result = handler.execute("/mode")
    assert result.status == "ok"


def test_command_handler_status():
    agent = MagicMock()
    agent.get_status.return_value = {
        "mode": "orchestrator",
        "provider": "openai",
        "model": "gpt-4o",
        "messages_count": 5,
        "last_run_cost": 0.0,
        "workspace_type": "python",
    }
    agent.messages = []
    handler = CommandHandler(agent)
    result = handler.execute("/status")
    assert result.status == "ok"


def test_command_handler_exit():
    agent = MagicMock()
    agent.messages = []
    agent._mode = "test"
    agent._model_name = "test"
    handler = CommandHandler(agent)
    result = handler.execute("/exit")
    assert result.data.get("should_exit") is True


def test_command_handler_clear():
    agent = MagicMock()
    agent.messages = []
    handler = CommandHandler(agent)
    result = handler.execute("/clear")
    assert result.status == "ok"


def test_command_handler_history():
    agent = MagicMock()
    agent.messages = [{"role": "user", "content": "hello"}]
    handler = CommandHandler(agent)
    result = handler.execute("/history")
    assert result.status == "ok"


def test_command_handler_compact():
    agent = MagicMock()
    agent.messages = [{"role": "user", "content": "hello"}]
    agent._mode = "test"
    handler = CommandHandler(agent)
    result = handler.execute("/compact")
    assert result.status == "ok"


def test_command_handler_approve_all():
    agent = MagicMock()
    handler = CommandHandler(agent)
    result = handler.execute("/approve-all")
    assert result.status == "ok"


def test_diff_display_imports():
    assert DiffDisplay is not None


def test_diff_compute():
    dd = DiffDisplay()
    diff = dd.compute_diff("hello\n", "hello world\n", "test.txt")
    assert "test.txt" in diff
    assert "+hello world" in diff


def test_diff_render():
    dd = DiffDisplay()
    diff = "--- a/test.txt\n+++ b/test.txt\n@@ -1 +1 @@\n-hello\n+hello world\n"
    panel = dd.render_diff(diff, "test.txt", "low")
    assert panel is not None
    assert hasattr(panel, "renderable")


def test_commands_defined():
    assert len(COMMAND_DEFINITIONS) == 17


def test_completer_works():
    completer = CommandCompleter(
        [{"name": "/mode", "description": ""}, {"name": "/model", "description": ""}]
    )

    class MockDoc:
        text_before_cursor = "/m"

    completions = list(completer.get_completions(MockDoc(), None))
    assert len(completions) == 2
    names = [c.text for c in completions]
    assert "/mode" in names
    assert "/model" in names
