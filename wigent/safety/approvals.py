from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from wigent.config import settings

logger = logging.getLogger(__name__)
console = Console()


class ActionCategory(Enum):
    ALWAYS_REQUIRE = "always_require"
    AUTO_APPROVE = "auto_approve"
    ALWAYS_BLOCK = "always_block"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


ALWAYS_REQUIRE_ACTIONS: set[str] = {
    "write_file", "delete_file",
    "execute_command", "git_commit", "git_push",
    "install_package", "modify_config",
    "network_request",
}

AUTO_APPROVE_ACTIONS: set[str] = {
    "read_file", "list_directory",
    "search_code", "get_git_status",
    "count_tokens", "get_file_info",
}

ALWAYS_BLOCK_ACTIONS: set[str] = {
    "rm_root", "format_disk", "credential_exfil", "system_file_mod",
}


@dataclass
class ApprovalResult:
    approved: bool
    reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_response: str = ""


@dataclass
class AuditEntry:
    action: str
    args: dict[str, Any]
    result: ApprovalResult
    risk: RiskLevel
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalGate:
    def __init__(
        self,
        auto_approve: bool | None = None,
        audit_path: str | None = None,
        approval_timeout: int = 60,
    ) -> None:
        self._auto_approve = auto_approve if auto_approve is not None else settings.AUTO_APPROVE
        self._audit_path = audit_path or os.path.join(os.getcwd(), ".agent", "audit.log")
        self._approval_timeout = approval_timeout
        self._lock = threading.Lock()
        self._audit_log: list[AuditEntry] = []
        self._load_audit_log()

    def _load_audit_log(self) -> None:
        audit_file = Path(self._audit_path)
        if audit_file.exists():
            try:
                with open(audit_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                self._audit_log.append(AuditEntry(**data))
                            except (json.JSONDecodeError, TypeError):
                                pass
            except OSError as exc:
                logger.warning("Could not read audit log: %s", exc)

    def classify_action(self, action: str) -> tuple[ActionCategory, RiskLevel]:
        action_lower = action.lower().strip()

        if action_lower in ALWAYS_BLOCK_ACTIONS:
            return ActionCategory.ALWAYS_BLOCK, RiskLevel.HIGH

        if action_lower in ALWAYS_REQUIRE_ACTIONS:
            risk = RiskLevel.HIGH if action_lower in ("delete_file", "git_push", "modify_config") else RiskLevel.MEDIUM
            return ActionCategory.ALWAYS_REQUIRE, risk

        if action_lower in AUTO_APPROVE_ACTIONS:
            return ActionCategory.AUTO_APPROVE, RiskLevel.LOW

        return ActionCategory.ALWAYS_REQUIRE, RiskLevel.MEDIUM

    def auto_approve_check(self, action: str) -> bool:
        category, _ = self.classify_action(action)
        if category == ActionCategory.ALWAYS_BLOCK:
            return False
        if category == ActionCategory.AUTO_APPROVE and self._auto_approve:
            return True
        if category == ActionCategory.ALWAYS_REQUIRE and self._auto_approve:
            return True
        return False

    def request_approval(
        self,
        action: str,
        args: dict[str, Any] | None = None,
        risk: RiskLevel | None = None,
        details: str | None = None,
    ) -> ApprovalResult:
        category, detected_risk = self.classify_action(action)
        effective_risk = risk or detected_risk

        if category == ActionCategory.ALWAYS_BLOCK:
            result = ApprovalResult(
                approved=False,
                reason=f"Action '{action}' is always blocked",
                user_response="blocked",
            )
            self.log_decision(action, args or {}, result, effective_risk)
            return result

        if self.auto_approve_check(action):
            result = ApprovalResult(
                approved=True,
                reason="Auto-approved",
                user_response="auto",
            )
            self.log_decision(action, args or {}, result, effective_risk)
            return result

        display = self.format_approval_ui(action, args or {}, effective_risk, details)
        console.print(display)

        start = time.monotonic()
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= self._approval_timeout:
                console.print("[yellow]⏰ Approval timed out — auto-rejecting.[/yellow]")
                result = ApprovalResult(
                    approved=False,
                    reason="Approval timeout (60s)",
                    user_response="timeout",
                )
                self.log_decision(action, args or {}, result, effective_risk)
                return result

            remaining = int(self._approval_timeout - elapsed)
            answer = Prompt.ask(
                f"[bold]Approve?[/] [green]y[/]/[red]n[/]/[blue]e[/]xplain  "
                f"(timeout: {remaining}s)",
                default="n",
            )
            answer = answer.strip().lower()

            if answer in ("y", "yes"):
                result = ApprovalResult(
                    approved=True,
                    reason="Approved by user",
                    user_response=answer,
                )
                self.log_decision(action, args or {}, result, effective_risk)
                return result

            if answer in ("n", "no"):
                result = ApprovalResult(
                    approved=False,
                    reason="Rejected by user",
                    user_response=answer,
                )
                self.log_decision(action, args or {}, result, effective_risk)
                return result

            if answer in ("e", "explain"):
                console.print(self._build_explanation(action, args or {}, effective_risk))
                continue

            console.print("[red]Invalid input. Enter [green]y[/green], [red]n[/red], or [blue]e[/blue].[/red]")

    def batch_approve(self, actions: list[tuple[str, dict[str, Any]]]) -> list[ApprovalResult]:
        results: list[ApprovalResult] = []
        for action, args in actions:
            result = self.request_approval(action, args)
            results.append(result)
            if not result.approved:
                break
        return results

    def format_approval_ui(
        self,
        action: str,
        args: dict[str, Any],
        risk: RiskLevel | None = None,
        details: str | None = None,
    ) -> Panel:
        risk_display = risk.value.upper() if risk else "UNKNOWN"
        color = {"low": "green", "medium": "yellow", "high": "red"}.get(
            risk.value if risk else "medium", "yellow"
        )

        lines = [
            f"[bold]Action:[/] {action}",
            f"[bold]Risk:[/] [{color}]{risk_display}[/{color}]",
        ]
        if args:
            safe_args = {k: v for k, v in args.items() if k not in ("api_key", "password", "token")}
            lines.append(f"[bold]Arguments:[/] {json.dumps(safe_args, indent=2, default=str)}")
        if details:
            lines.append(f"[bold]Details:[/] {details}")
        lines.append("")
        lines.append("[dim]Options: [green]y[/green] Yes | [red]n[/red] No | [blue]e[/blue] Explain[/dim]")

        return Panel(
            "\n".join(lines),
            title=f"⚠️  Approval Required — {risk_display} Risk",
            border_style=color,
        )

    def _build_explanation(
        self,
        action: str,
        args: dict[str, Any],
        risk: RiskLevel,
    ) -> Panel:
        category, _ = self.classify_action(action)
        lines = [
            f"[bold]Action:[/] {action}",
            f"[bold]Category:[/] {category.value}",
            f"[bold]Risk Level:[/] {risk.value.upper()}",
            "",
            "[bold]Why this matters:[/]",
        ]
        if risk == RiskLevel.HIGH:
            lines.append("  This action can permanently modify or destroy data.")
        elif risk == RiskLevel.MEDIUM:
            lines.append("  This action modifies files or system state.")
        else:
            lines.append("  This action is read-only and generally safe.")

        lines.append("")
        lines.append("[bold]What happens if approved:[/]")
        if action == "write_file":
            lines.append("  The file will be written with the provided content.")
        elif action == "delete_file":
            lines.append("  The specified file will be permanently deleted.")
        elif action == "execute_command":
            lines.append("  The shell command will be executed in the workspace.")
        elif action == "git_push":
            lines.append("  Commits will be pushed to the remote repository.")
        else:
            lines.append(f"  The action '{action}' will be executed with its arguments.")

        return Panel(
            "\n".join(lines),
            title="📋 Detailed Explanation",
            border_style="blue",
        )

    def log_decision(
        self,
        action: str,
        args: dict[str, Any],
        result: ApprovalResult,
        risk: RiskLevel,
    ) -> None:
        safe_args = {k: v for k, v in args.items() if k not in ("api_key", "password", "token")}
        entry = AuditEntry(
            action=action,
            args=safe_args,
            result=result,
            risk=risk,
        )

        with self._lock:
            self._audit_log.append(entry)
            self._append_to_audit_file(entry)

        status = "APPROVED" if result.approved else "REJECTED"
        logger.info(
            "Audit: %s | action=%s | risk=%s | reason=%s",
            status, action, risk.value, result.reason,
        )

    def _append_to_audit_file(self, entry: AuditEntry) -> None:
        audit_path = Path(self._audit_path)
        try:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with open(audit_path, "a") as f:
                f.write(json.dumps({
                    "action": entry.action,
                    "args": entry.args,
                    "result": {
                        "approved": entry.result.approved,
                        "reason": entry.result.reason,
                        "user_response": entry.result.user_response,
                    },
                    "risk": entry.risk.value,
                    "timestamp": entry.timestamp.isoformat(),
                }))
                f.write("\n")
        except OSError as exc:
            logger.error("Failed to write audit log: %s", exc)

    def get_audit_log(self) -> list[AuditEntry]:
        with self._lock:
            return list(self._audit_log)

    def set_auto_approve_mode(self, enabled: bool) -> None:
        self._auto_approve = enabled
        mode = "enabled" if enabled else "disabled"
        logger.info("Auto-approve mode %s", mode)


__all__ = [
    "ActionCategory", "RiskLevel",
    "ApprovalResult", "AuditEntry",
    "ApprovalGate",
]
