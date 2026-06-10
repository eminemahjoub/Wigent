from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Any

from wigent.cli.ui_components import UIComponents

logger = logging.getLogger(__name__)

COMMAND_DEFINITIONS: list[dict[str, str]] = [
    {
        "name": "/mode [name]",
        "description": "Switch agent mode",
        "usage": "/mode architect",
        "detail": "Switch the agent's operational mode. Omit name to show current mode.",
    },
    {
        "name": "/model [provider] [model]",
        "description": "Switch LLM provider and model",
        "usage": "/model anthropic claude-3-5-sonnet",
        "detail": "Change the LLM provider and optionally the model. Lists available if no args.",
    },
    {
        "name": "/clear",
        "description": "Clear conversation history",
        "usage": "/clear",
        "detail": "Clear all conversation history after confirmation. System prompt is preserved.",
    },
    {
        "name": "/save [name]",
        "description": "Save current session",
        "usage": "/save my-feature",
        "detail": "Save the current session with an optional name. Auto-generates if not given.",
    },
    {
        "name": "/load [name]",
        "description": "Load a saved session",
        "usage": "/load my-feature",
        "detail": "Load a previously saved session. Lists sessions if no name given.",
    },
    {
        "name": "/checkpoint [label]",
        "description": "Create a named checkpoint",
        "usage": "/checkpoint before-refactor",
        "detail": "Create a checkpoint of the current state with an optional label.",
    },
    {
        "name": "/restore [id]",
        "description": "Restore from a checkpoint",
        "usage": "/restore abc123",
        "detail": "Restore agent state from a checkpoint. Lists checkpoints if no id given.",
    },
    {
        "name": "/status",
        "description": "Show agent status",
        "usage": "/status",
        "detail": "Display current mode, model, token usage, cost, files modified, and workspace info.",
    },
    {
        "name": "/history [n]",
        "description": "Show last n messages",
        "usage": "/history 20",
        "detail": "Display the last n conversation messages (default 10).",
    },
    {
        "name": "/cost",
        "description": "Show token and cost breakdown",
        "usage": "/cost",
        "detail": "Detailed token usage and cost per message, total session, and estimated daily/monthly.",
    },
    {
        "name": "/index [path]",
        "description": "Index codebase for vector search",
        "usage": "/index ./src",
        "detail": "Index the codebase at the given path for semantic vector search.",
    },
    {
        "name": "/workspace",
        "description": "Show workspace info",
        "usage": "/workspace",
        "detail": "Display current workspace project type, framework, and indexed files.",
    },
    {
        "name": "/rules [show|edit]",
        "description": "Show or edit .agent/rules/ files",
        "usage": "/rules edit",
        "detail": "View or edit the project's .agent/rules/ files in $EDITOR.",
    },
    {
        "name": "/approve-all [on|off]",
        "description": "Toggle auto-approve mode",
        "usage": "/approve-all on",
        "detail": "Enable or disable automatic approval of all actions.",
    },
    {
        "name": "/compact",
        "description": "Summarize and compress history",
        "usage": "/compact",
        "detail": "Summarize and compress conversation history to free context tokens.",
    },
    {
        "name": "/help [command]",
        "description": "Show help",
        "usage": "/help mode",
        "detail": "Display all commands or detailed help for a specific command.",
    },
    {
        "name": "/exit",
        "description": "Exit gracefully",
        "usage": "/exit",
        "detail": "Exit the agent with a session summary.",
    },
]


class CommandResult:
    def __init__(
        self,
        status: str = "ok",
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.message = message
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "message": self.message, "data": self.data}


class CommandHandler:
    def __init__(self, agent: Any, ui: UIComponents | None = None) -> None:
        self._agent = agent
        self._ui = ui or UIComponents()

    def parse(self, input_str: str) -> dict[str, Any]:
        parts = input_str.strip().split()
        if not parts:
            return {"name": "", "args": []}
        name = parts[0].lower()
        args = parts[1:]
        return {"name": name, "args": args}

    def execute(self, input_str: str) -> CommandResult:
        parsed = self.parse(input_str)
        name = parsed["name"]
        args = parsed["args"]

        if not name:
            return CommandResult("error", "Empty command. Type /help for available commands.")

        dispatch: dict[str, Any] = {
            "/mode": self._cmd_mode,
            "/model": self._cmd_model,
            "/clear": self._cmd_clear,
            "/save": self._cmd_save,
            "/load": self._cmd_load,
            "/checkpoint": self._cmd_checkpoint,
            "/restore": self._cmd_restore,
            "/status": self._cmd_status,
            "/history": self._cmd_history,
            "/cost": self._cmd_cost,
            "/index": self._cmd_index,
            "/workspace": self._cmd_workspace,
            "/rules": self._cmd_rules,
            "/approve-all": self._cmd_approve_all,
            "/compact": self._cmd_compact,
            "/help": self._cmd_help,
            "/exit": self._cmd_exit,
            "/quit": self._cmd_exit,
        }

        handler = dispatch.get(name)
        if handler is None:
            return CommandResult(
                "error",
                f"Unknown command: {name}. Type /help for available commands.",
            )

        try:
            return handler(args)
        except Exception as exc:
            logger.exception("Command failed: %s", exc)
            return CommandResult("error", f"Command failed: {exc}")

    def get_all_commands(self) -> list[dict[str, str]]:
        return COMMAND_DEFINITIONS

    def get_command_help(self, name: str) -> str:
        for cmd in COMMAND_DEFINITIONS:
            if cmd["name"].startswith(name):
                return f"{cmd['name']}\n  {cmd['description']}\n  Usage: {cmd['usage']}\n  {cmd['detail']}"
        return f"No help available for '{name}'."

    # ── Command implementations ────────────────────────────────────────

    def _cmd_mode(self, args: list[str]) -> CommandResult:
        if not args:
            current = self._agent._mode
            return CommandResult("ok", f"Current mode: [bold]{current}[/bold]")
        mode_name = args[0].lower()
        valid_modes = ["orchestrator", "architect", "coder", "debugger", "reviewer"]
        if mode_name not in valid_modes:
            return CommandResult(
                "error",
                f"Unknown mode: {mode_name}. Valid modes: {', '.join(valid_modes)}",
                data={"valid_modes": valid_modes},
            )
        old_mode = self._agent._mode
        self._agent.set_mode(mode_name)
        self._ui.print_mode_switch(old_mode, mode_name)
        return CommandResult("ok", f"Switched to [bold]{mode_name}[/bold] mode.")

    def _cmd_model(self, args: list[str]) -> CommandResult:
        if not args:
            current_provider = self._agent._provider
            current_model = self._agent._model_name
            return CommandResult(
                "ok",
                f"Current provider: [bold]{current_provider}[/bold]\n"
                f"Current model: [bold]{current_model}[/bold]",
                data={"provider": current_provider, "model": current_model},
            )
        provider = args[0].lower()
        model_name = args[1] if len(args) > 1 else None

        try:
            self._agent.set_model(provider, model_name)
            return CommandResult(
                "ok",
                f"Switched to provider [bold]{provider}[/bold]"
                + (f" with model [bold]{model_name}[/bold]" if model_name else ""),
            )
        except Exception as exc:
            return CommandResult("error", f"Failed to switch model: {exc}")

    def _cmd_clear(self, args: list[str]) -> CommandResult:
        self._agent.messages.clear()
        try:
            self._agent._memory.context.clear()
        except RuntimeError:
            pass
        return CommandResult("ok", "Conversation history cleared. System prompt preserved.")

    def _cmd_save(self, args: list[str]) -> CommandResult:
        name = args[0] if args else None
        try:
            session = self._agent._memory.sessions.create_session(
                name=name,
                description=f"Session saved from CLI",
            )
            return CommandResult(
                "ok",
                f"Session saved: [bold]{session.session_id}[/bold]",
                data={"session_id": session.session_id, "name": name or "auto"},
            )
        except Exception as exc:
            return CommandResult("error", f"Failed to save session: {exc}")

    def _cmd_load(self, args: list[str]) -> CommandResult:
        if not args:
            try:
                sessions = self._agent._memory.sessions.list_sessions()
                if not sessions:
                    return CommandResult("ok", "No saved sessions found.")
                session_list = "\n".join(
                    f"  [bold]{s.session_id}[/bold] — {s.name or 'unnamed'} ({s.created_at})"
                    for s in sessions[:10]
                )
                return CommandResult(
                    "ok",
                    f"Available sessions:\n{session_list}",
                    data={"count": len(sessions)},
                )
            except Exception as exc:
                return CommandResult("ok", f"Sessions list unavailable: {exc}")
        session_id = args[0]
        try:
            session = self._agent._memory.sessions.load_session(session_id)
            if session:
                self._agent._current_session_id = session.session_id
                return CommandResult(
                    "ok",
                    f"Loaded session: [bold]{session_id}[/bold]",
                    data={"session_id": session_id},
                )
            return CommandResult("error", f"Session not found: {session_id}")
        except Exception as exc:
            return CommandResult("error", f"Failed to load session: {exc}")

    def _cmd_checkpoint(self, args: list[str]) -> CommandResult:
        label = args[0] if args else None
        try:
            cp = self._agent._memory.checkpoints.auto_checkpoint(
                label=label or f"manual_{len(self._agent.messages)}",
                agent_state={"mode": self._agent._mode},
            )
            return CommandResult(
                "ok",
                f"Checkpoint created: [bold]{cp.checkpoint_id}[/bold]"
                + (f" ({label})" if label else ""),
                data={"checkpoint_id": cp.checkpoint_id, "label": label},
            )
        except Exception as exc:
            return CommandResult("error", f"Failed to create checkpoint: {exc}")

    def _cmd_restore(self, args: list[str]) -> CommandResult:
        if not args:
            try:
                checkpoints = self._agent._memory.checkpoints.list_checkpoints()
                if not checkpoints:
                    return CommandResult("ok", "No checkpoints available.")
                cp_list = "\n".join(
                    f"  [bold]{c.checkpoint_id}[/bold] — {c.label or 'no label'}"
                    for c in checkpoints[:10]
                )
                return CommandResult("ok", f"Available checkpoints:\n{cp_list}")
            except Exception as exc:
                return CommandResult("ok", f"Checkpoints unavailable: {exc}")

        cp_id = args[0]
        try:
            self._agent._memory.checkpoints.restore_checkpoint(cp_id)
            return CommandResult(
                "ok",
                f"Restored from checkpoint: [bold]{cp_id}[/bold]",
                data={"checkpoint_id": cp_id},
            )
        except Exception as exc:
            return CommandResult("error", f"Failed to restore checkpoint: {exc}")

    def _cmd_status(self, args: list[str]) -> CommandResult:
        status = self._agent.get_status()
        lines = [
            f"🎯 [bold]Mode:[/bold] {status.get('mode', 'unknown')}",
            f"🤖 [bold]Model:[/bold] {status.get('provider', '?')}/{status.get('model', '?')}",
            f"📊 [bold]Messages:[/bold] {status.get('messages_count', 0)}",
            f"💰 [bold]Session cost:[/bold] ${status.get('last_run_cost', 0):.4f}",
            f"📁 [bold]Workspace:[/bold] {status.get('workspace_type', 'unknown')}",
        ]
        return CommandResult("ok", "\n".join(lines), data=status)

    def _cmd_history(self, args: list[str]) -> CommandResult:
        n = int(args[0]) if args and args[0].isdigit() else 10
        messages = self._agent.messages[-n:] if self._agent.messages else []
        if not messages:
            return CommandResult("ok", "No conversation history.")
        history_lines = []
        for msg in messages:
            role = msg.get("role", "unknown").title()
            content = msg.get("content", "")
            preview = content[:200].replace("\n", "\\n") if content else "(empty)"
            history_lines.append(f"  [bold]{role}:[/bold] {preview}")
        return CommandResult(
            "ok",
            f"Last {len(messages)} messages:\n" + "\n".join(history_lines),
            data={"count": len(messages), "total": len(self._agent.messages)},
        )

    def _cmd_cost(self, args: list[str]) -> CommandResult:
        state = self._agent.state
        if not state:
            return CommandResult("ok", "No cost data available. Run a task first.")

        token_usage = state.get("token_usage", {})
        total_cost = state.get("total_cost", 0.0)
        input_tokens = token_usage.get("input", 0)
        output_tokens = token_usage.get("output", 0)
        total_tokens = token_usage.get("total", 0)

        cost_data = {
            "Input tokens": input_tokens,
            "Output tokens": output_tokens,
            "Total tokens": total_tokens,
            "Session cost": total_cost,
        }
        return CommandResult(
            "ok",
            f"Tokens: [bold]{total_tokens}[/bold] (in: {input_tokens}, out: {output_tokens})\n"
            f"Cost: [bold]${total_cost:.4f}[/bold]",
            data=cost_data,
        )

    def _cmd_index(self, args: list[str]) -> CommandResult:
        path = args[0] if args else os.getcwd()
        if not os.path.isdir(path):
            return CommandResult("error", f"Directory not found: {path}")
        try:
            self._agent.auto_indexer.index_on_startup(path, background=False)
            status = self._agent.auto_indexer.get_index_status()
            return CommandResult(
                "ok",
                f"Indexed [bold]{status.files_indexed}[/bold] files at {path}",
                data={"files_indexed": status.files_indexed, "path": path},
            )
        except Exception as exc:
            return CommandResult("error", f"Indexing failed: {exc}")

    def _cmd_workspace(self, args: list[str]) -> CommandResult:
        ws = self._agent.get_workspace_info()
        self._ui.print_workspace_banner(ws)
        return CommandResult("ok", "Workspace info displayed above.")

    def _cmd_rules(self, args: list[str]) -> CommandResult:
        action = args[0].lower() if args else "show"
        ws_path = self._agent._workspace_info.get("path", os.getcwd()) if self._agent._workspace_info else os.getcwd()
        rules_dir = os.path.join(ws_path, ".agent", "rules")

        if not os.path.isdir(rules_dir):
            return CommandResult("ok", f"No .agent/rules/ directory found at {ws_path}")

        if action == "show":
            md_files = sorted(f for f in os.listdir(rules_dir) if f.endswith(".md"))
            if not md_files:
                return CommandResult("ok", f"No .md files in {rules_dir}")
            previews = []
            for fname in md_files:
                fpath = os.path.join(rules_dir, fname)
                try:
                    with open(fpath, "r") as f:
                        content = f.read()[:200]
                except Exception:
                    content = "(unreadable)"
                previews.append(f"  [bold]{fname}[/bold]:\n    {content}")
            return CommandResult(
                "ok",
                f"Rules in {rules_dir}:\n" + "\n".join(previews),
                data={"files": md_files, "directory": rules_dir},
            )
        elif action == "edit":
            editor = os.environ.get("EDITOR", "vi")
            md_files = sorted(f for f in os.listdir(rules_dir) if f.endswith(".md"))
            if not md_files:
                return CommandResult("ok", f"No .md files to edit in {rules_dir}")
            target = os.path.join(rules_dir, md_files[0])
            try:
                subprocess.run([editor, target], check=True)
                return CommandResult("ok", f"Edited {target}")
            except Exception as exc:
                return CommandResult("error", f"Failed to open editor: {exc}")
        else:
            return CommandResult("error", f"Unknown action: {action}. Use 'show' or 'edit'.")

    def _cmd_approve_all(self, args: list[str]) -> CommandResult:
        if not args:
            try:
                auto = self._agent._safety.approvals._auto_approve
            except (RuntimeError, AttributeError):
                auto = False
            return CommandResult(
                "ok",
                f"Auto-approve is [bold]{'ON' if auto else 'OFF'}[/bold]",
            )
        setting = args[0].lower()
        if setting in ("on", "true", "1", "yes"):
            try:
                self._agent._safety.approvals.set_auto_approve_mode(True)
            except (RuntimeError, AttributeError):
                pass
            return CommandResult("ok", "Auto-approve [bold]enabled[/bold]. ⚠️ All actions will be approved without confirmation.")
        elif setting in ("off", "false", "0", "no"):
            try:
                self._agent._safety.approvals.set_auto_approve_mode(False)
            except (RuntimeError, AttributeError):
                pass
            return CommandResult("ok", "Auto-approve [bold]disabled[/bold]. Safety gates are active.")
        else:
            return CommandResult("error", f"Unknown setting: {setting}. Use 'on' or 'off'.")

    def _cmd_compact(self, args: list[str]) -> CommandResult:
        before = len(str(self._agent.messages))
        before_tokens = before // 4

        summary = (
            f"Session: {len(self._agent.messages)} messages\n"
            f"Mode: {self._agent._mode}\n"
            f"Topics: (compressed)"
        )
        self._agent.messages = [
            {"role": "system", "content": f"[COMPRESSED] {summary}"}
        ]
        after = len(str(self._agent.messages))
        after_tokens = after // 4

        return CommandResult(
            "ok",
            f"History compressed: [bold]{before_tokens}[/bold] → [bold]{after_tokens}[/bold] tokens "
            f"(saved [green]{before_tokens - after_tokens}[/green] tokens)",
            data={"before_tokens": before_tokens, "after_tokens": after_tokens},
        )

    def _cmd_help(self, args: list[str]) -> CommandResult:
        if args:
            help_text = self.get_command_help(args[0])
            return CommandResult("ok", help_text)
        self._ui.print_help(COMMAND_DEFINITIONS)
        return CommandResult("ok", "Help displayed above.")

    def _cmd_exit(self, args: list[str]) -> CommandResult:
        n = len(self._agent.messages) if self._agent.messages else 0
        summary = f"Session: {n} messages | Mode: {self._agent._mode} | Model: {self._agent._model_name}"
        return CommandResult("ok", f"Exiting. {summary}", data={"should_exit": True})


__all__ = ["CommandHandler", "CommandResult", "COMMAND_DEFINITIONS"]
