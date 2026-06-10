from __future__ import annotations

import base64
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+(instructions|directions|prompts)", re.IGNORECASE),
    re.compile(r"disregard\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+are\s+", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"\bDAN\b"),
    re.compile(r"\bdo\s+anything\s+now\b", re.IGNORECASE),
    re.compile(r"you\s+must\s+ignore\s+", re.IGNORECASE),
    re.compile(r"print\s+your\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"output\s+your\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"repeat\s+(after\s+me|the\s+words|everything)", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"override\s+(mode|persona|behavior)", re.IGNORECASE),
]

ZERO_WIDTH_CHARS: list[str] = [
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\ufeff",  # BOM
    "\u2060",  # word joiner
    "\u2061",  # function application
    "\u2062",  # invisible times
    "\u2063",  # invisible separator
    "\u2064",  # invisible plus
]

BASE64_PATTERN: re.Pattern = re.compile(
    r"(?:[A-Za-z0-9+/]{40,}(?:[AQgw]==?)?)"
)

BLOCKED_PATH_COMPONENTS: list[str] = [
    "/etc", "/sys", "/proc", "/dev",
    "/boot", "/root", "/bin", "/sbin",
    "/usr/lib", "/usr/bin", "/usr/sbin",
    "~", "$HOME",
]

BLOCKED_COMMAND_CHARS: set[str] = {
    "`", "$(", "${", ";", "|", "&", ">", "<",
}


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sanitized_value: Any = None


class InputValidator:
    INJECTION_PATTERNS = INJECTION_PATTERNS
    ZERO_WIDTH_CHARS = ZERO_WIDTH_CHARS
    BASE64_PATTERN = BASE64_PATTERN

    def validate_file_path(self, path: str) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not path or not path.strip():
            errors.append("Path is empty")
            return ValidationResult(valid=False, errors=errors)

        try:
            resolved = Path(path).resolve()
        except (OSError, RuntimeError) as exc:
            errors.append(f"Cannot resolve path: {exc}")
            return ValidationResult(valid=False, errors=errors)

        for blocked in BLOCKED_PATH_COMPONENTS:
            if str(resolved).startswith(blocked) or f"/{blocked.lstrip('/')}" in str(resolved):
                warnings.append(f"Path targets system directory: {blocked}")
                break

        if ".." in path.split(os.sep):
            warnings.append("Path contains '..' traversal")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_value=str(resolved),
        )

    def validate_command(self, cmd: str) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not cmd or not cmd.strip():
            errors.append("Command is empty")
            return ValidationResult(valid=False, errors=errors)

        for char in BLOCKED_COMMAND_CHARS:
            if char in cmd:
                warnings.append(f"Command contains shell metacharacter: {char}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_value=cmd.strip(),
        )

    def validate_code(self, code: str) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not code or not code.strip():
            errors.append("Code is empty")
            return ValidationResult(valid=False, errors=errors)

        if self.detect_prompt_injection(code):
            warnings.append("Code may contain prompt injection patterns")
            code = self.sanitize_llm_output(code)
            sanitized = code
        else:
            sanitized = code

        if len(code) > 100_000:
            warnings.append(f"Code exceeds 100KB ({len(code)} chars)")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_value=sanitized,
        )

    def detect_prompt_injection(self, text: str) -> bool:
        if not text:
            return False

        for pattern in self.INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning("Prompt injection detected: matched %s", pattern.pattern[:60])
                return True

        for char in self.ZERO_WIDTH_CHARS:
            if char in text:
                logger.warning("Prompt injection detected: zero-width char U+%04X", ord(char))
                return True

        stripped = text.strip()
        if self.BASE64_PATTERN.fullmatch(stripped.replace("\n", "").replace(" ", "")):
            try:
                decoded = base64.b64decode(stripped.replace("\n", "").replace(" ", ""))
                decoded_text = decoded.decode("utf-8", errors="ignore")
                for pattern in self.INJECTION_PATTERNS:
                    if pattern.search(decoded_text):
                        logger.warning("Prompt injection detected: base64 encoded")
                        return True
            except (base64.binascii.Error, ValueError):
                pass

        return False

    def sanitize_llm_output(self, text: str) -> str:
        if not text:
            return text

        for pattern in self.INJECTION_PATTERNS:
            text = pattern.sub("[REDACTED]", text)

        for char in self.ZERO_WIDTH_CHARS:
            text = text.replace(char, "")

        return text

    def validate_tool_args(self, tool: str, args: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not isinstance(args, dict):
            errors.append("Arguments must be a dict")
            return ValidationResult(valid=False, errors=errors)

        if tool in ("write_file", "edit_file"):
            content = args.get("content", "")
            if isinstance(content, str) and self.detect_prompt_injection(content):
                warnings.append("Tool argument contains prompt injection patterns")

            file_path = args.get("file_path", "") or args.get("path", "")
            if file_path:
                path_result = self.validate_file_path(file_path)
                if not path_result.valid:
                    errors.extend(path_result.errors)
                warnings.extend(path_result.warnings)

        if tool in ("execute_command", "bash"):
            command = args.get("command", "")
            if command:
                cmd_result = self.validate_command(command)
                if not cmd_result.valid:
                    errors.extend(cmd_result.errors)
                warnings.extend(cmd_result.warnings)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_value=args,
        )


__all__ = [
    "ValidationResult",
    "InputValidator",
]
