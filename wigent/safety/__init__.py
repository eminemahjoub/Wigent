from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from wigent.config import settings

from wigent.safety.approvals import ApprovalGate, ApprovalResult, ActionCategory, RiskLevel
from wigent.safety.diff_viewer import DiffViewer, Diff, ChangeStats
from wigent.safety.sandbox import (
    Sandbox,
    SafetyResult,
    CommandCategory,
    Classification,
    classify_command,
    validate_sandbox_path,
    sanitize_env,
    format_approval_request,
    BLOCKED_PATTERNS,
    WARN_PATTERNS,
    SAFE_PREFIXES,
)
from wigent.safety.validator import InputValidator, ValidationResult

from wigent.safety.owasp_scanner import (
    OwaspScanner,
    ScanResult,
    Vulnerability,
    OwaspCategory,
    Severity,
)

logger = logging.getLogger(__name__)


class SafetySystem:
    def __init__(self) -> None:
        self._approvals: ApprovalGate | None = None
        self._diff_viewer: DiffViewer | None = None
        self._sandbox: Sandbox | None = None
        self._validator: InputValidator | None = None
        self._initialized = False

    def initialize(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        auto_approve = config.get("auto_approve", settings.AUTO_APPROVE)
        audit_path = config.get("audit_path", os.path.join(os.getcwd(), ".agent", "audit.log"))

        self._approvals = ApprovalGate(
            auto_approve=auto_approve,
            audit_path=audit_path,
        )
        self._diff_viewer = DiffViewer()
        self._sandbox = Sandbox()
        self._validator = InputValidator()
        self._initialized = True

        logger.info("SafetySystem initialized (auto_approve=%s)", auto_approve)

    @property
    def approvals(self) -> ApprovalGate:
        if not self._initialized or self._approvals is None:
            raise RuntimeError("SafetySystem not initialized. Call initialize() first.")
        return self._approvals

    @property
    def diff_viewer(self) -> DiffViewer:
        if not self._initialized or self._diff_viewer is None:
            raise RuntimeError("SafetySystem not initialized. Call initialize() first.")
        return self._diff_viewer

    @property
    def sandbox(self) -> Sandbox:
        if not self._initialized or self._sandbox is None:
            raise RuntimeError("SafetySystem not initialized. Call initialize() first.")
        return self._sandbox

    @property
    def validator(self) -> InputValidator:
        if not self._initialized or self._validator is None:
            raise RuntimeError("SafetySystem not initialized. Call initialize() first.")
        return self._validator

    def safe_write(
        self,
        file_path: str,
        content: str,
        original_content: str | None = None,
    ) -> bool:
        path_result = self.validator.validate_file_path(file_path)
        if not path_result.valid:
            logger.error("safe_write: invalid path %s: %s", file_path, path_result.errors)
            return False

        content_result = self.validator.validate_code(content)
        if not content_result.valid:
            logger.error("safe_write: invalid content for %s: %s", file_path, content_result.errors)
            return False

        safe_path = Path(path_result.sanitized_value) if path_result.sanitized_value else Path(file_path)
        actual_original = original_content
        if actual_original is None and safe_path.exists():
            try:
                actual_original = safe_path.read_text(encoding="utf-8")
            except OSError:
                actual_original = ""

        diff = self.diff_viewer.compute_diff(
            original=actual_original or "",
            modified=content,
            file_path=str(safe_path),
        )

        if diff.stats.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH):
            panel = self.diff_viewer.display_diff(diff)
            from rich.console import Console
            Console().print(panel)

        result = self.approvals.request_approval(
            action="write_file",
            args={"file_path": str(safe_path), "size": len(content)},
            risk=diff.stats.risk_level,
        )

        if not result.approved:
            logger.info("safe_write: rejected %s", safe_path)
            return False

        try:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            safe_path.write_text(content, encoding="utf-8")
            logger.info("safe_write: wrote %s (%d bytes)", safe_path, len(content))
            return True
        except OSError as exc:
            logger.error("safe_write: failed to write %s: %s", safe_path, exc)
            return False

    def safe_execute(self, command: str) -> bool:
        cmd_result = self.validator.validate_command(command)
        if not cmd_result.valid:
            logger.error("safe_execute: invalid command: %s", cmd_result.errors)
            return False

        safety = self.sandbox.is_command_safe(command)
        if safety.level == "BLOCKED":
            logger.error("safe_execute: blocked command: %s", safety.reason)
            return False

        if safety.level == "WARN":
            result = self.approvals.request_approval(
                action="execute_command",
                args={"command": command[:200]},
                details=f"{safety.reason}\nSuggestion: {safety.suggestion or 'N/A'}",
            )
            if not result.approved:
                logger.info("safe_execute: rejected command")
                return False

        return True

    def shutdown(self) -> None:
        self._approvals = None
        self._diff_viewer = None
        self._sandbox = None
        self._validator = None
        self._initialized = False
        logger.info("SafetySystem shut down")


__all__ = [
    "SafetySystem",
    "ApprovalGate", "ApprovalResult", "ActionCategory", "RiskLevel",
    "DiffViewer", "Diff", "ChangeStats",
    "Sandbox", "SafetyResult",
    "CommandCategory", "Classification",
    "classify_command", "validate_sandbox_path", "sanitize_env",
    "format_approval_request",
    "BLOCKED_PATTERNS", "WARN_PATTERNS", "SAFE_PREFIXES",
    "InputValidator", "ValidationResult",
    "OwaspScanner", "ScanResult", "Vulnerability",
    "OwaspCategory", "Severity",
]
