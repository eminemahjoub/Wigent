"""
Secret Scanner — Entropy & Pattern-based Secret Detection

Detects hardcoded secrets, API keys, tokens, passwords, and other
sensitive credentials in source code using:
1. Pattern matching: Known secret formats (AWS keys, GitHub tokens, etc.)
2. Entropy analysis: Shannon entropy for high-randomness strings
3. Allowlist: Configurable false-positive suppression via path/pattern rules

Phase 4, Week 12: Security & Hardening
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class SecretType(Enum):
    """Classifies the kind of secret detected."""
    API_KEY = "api_key"
    ACCESS_TOKEN = "access_token"
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"
    AWS_ACCESS_KEY = "aws_access_key"
    AWS_SECRET_KEY = "aws_secret_key"
    GITHUB_TOKEN = "github_token"
    JWT_TOKEN = "jwt_token"
    CONNECTION_STRING = "connection_string"
    ENCRYPTION_KEY = "encryption_key"
    GENERIC_HIGH_ENTROPY = "generic_high_entropy"


class RiskLevel(Enum):
    """Severity of the detected secret."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SecretMatch:
    """A single secret detection result."""
    type: SecretType
    value_preview: str
    line_number: int
    column: int
    file_path: str
    entropy: float
    risk: RiskLevel
    pattern_name: str
    context: str
    is_allowlisted: bool = False

    @property
    def unique_key(self) -> tuple:
        return (self.file_path, self.line_number, self.type.value, self.value_preview[:30])


@dataclass
class ScanResult:
    """Results from scanning a single file or project."""
    file_path: str
    secrets: list[SecretMatch] = field(default_factory=list)
    duration_ms: float = 0.0
    files_scanned: int = 1

    @property
    def critical_count(self) -> int:
        return sum(1 for s in self.secrets if s.risk == RiskLevel.CRITICAL and not s.is_allowlisted)

    @property
    def high_count(self) -> int:
        return sum(1 for s in self.secrets if s.risk == RiskLevel.HIGH and not s.is_allowlisted)

    @property
    def medium_count(self) -> int:
        return sum(1 for s in self.secrets if s.risk == RiskLevel.MEDIUM and not s.is_allowlisted)

    @property
    def is_clean(self) -> bool:
        return self.critical_count == 0 and self.high_count == 0

    @property
    def active_secrets(self) -> list[SecretMatch]:
        return [s for s in self.secrets if not s.is_allowlisted]


class SecretScanner:
    """
    Multi-strategy secret scanner with entropy analysis and allowlist support.

    Strategies:
    1. Pattern matching — regex for known secret formats (keys, tokens, certs)
    2. Entropy analysis — Shannon entropy threshold for random-looking values
    3. Allowlist filtering — suppress known false positives by path or pattern
    """

    ENTROPY_THRESHOLD = 4.2
    MIN_SECRET_LENGTH = 12
    MAX_SECRET_LENGTH = 2048

    def __init__(self, allowlist: Optional[list[str]] = None):
        self._allowlist_patterns: list[re.Pattern] = []
        for entry in (allowlist or []):
            try:
                self._allowlist_patterns.append(re.compile(entry))
            except re.error:
                pass

    # ─────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────

    def scan_file(self, file_path: str | Path, content: Optional[str] = None) -> ScanResult:
        start = time.perf_counter()
        path = Path(file_path)
        actual_path = str(path.resolve())

        if content is None:
            if not path.exists():
                return ScanResult(file_path=actual_path)
            content = path.read_text()

        secrets: list[SecretMatch] = []

        pattern_matches = self._pattern_based_scan(content, actual_path)
        secrets.extend(pattern_matches)

        entropy_matches = self._entropy_based_scan(content, actual_path)
        for em in entropy_matches:
            already_seen = any(
                s.line_number == em.line_number
                and s.type == em.type
                and abs(s.entropy - em.entropy) < 0.1
                for s in secrets
            )
            if not already_seen:
                secrets.append(em)

        for secret in secrets:
            secret.is_allowlisted = self._is_allowlisted(secret)

        secrets.sort(key=lambda s: (s.line_number, s.column))

        result = ScanResult(
            file_path=actual_path,
            secrets=secrets,
            duration_ms=(time.perf_counter() - start) * 1000,
        )
        return result

    def scan_project(
        self,
        root: str | Path,
        pattern: str = "**/*.py",
        exclude_patterns: Optional[list[str]] = None,
    ) -> list[ScanResult]:
        root_path = Path(root)
        exclude = [re.compile(e) for e in (exclude_patterns or [])]
        results: list[ScanResult] = []
        files_scanned = 0

        for file_path in sorted(root_path.glob(pattern)):
            abs_path = str(file_path.resolve())
            if any(e.search(abs_path) for e in exclude):
                continue
            try:
                result = self.scan_file(file_path)
                result.files_scanned = 1
                results.append(result)
                files_scanned += 1
            except Exception:
                continue

        totals = ScanResult(file_path=str(root_path), files_scanned=files_scanned)
        for r in results:
            totals.secrets.extend(r.secrets)
        totals.duration_ms = sum(r.duration_ms for r in results)

        return results

    def summary(self, results: list[ScanResult]) -> str:
        total = ScanResult(file_path="")
        for r in results:
            total.secrets.extend(r.secrets)
            total.files_scanned += r.files_scanned
            total.duration_ms += r.duration_ms

        active = total.active_secrets
        lines = [
            f"Secret Scan Summary",
            f"{'=' * 60}",
            f"Files scanned: {total.files_scanned}",
            f"Duration: {total.duration_ms:.0f} ms",
            f"",
        ]

        if not active:
            lines.append("  No secrets detected.")
            return "\n".join(lines)

        lines.append(f"  CRITICAL: {total.critical_count}")
        lines.append(f"  HIGH:     {total.high_count}")
        lines.append(f"  MEDIUM:   {total.medium_count}")
        lines.append(f"  LOW:      {sum(1 for s in total.secrets if s.risk == RiskLevel.LOW and not s.is_allowlisted)}")
        lines.append(f"  Allowlisted: {len(total.secrets) - len(active)}")
        lines.append("")

        for s in active:
            icon = {
                RiskLevel.CRITICAL: "CRIT",
                RiskLevel.HIGH: "HIGH",
                RiskLevel.MEDIUM: "MED ",
                RiskLevel.LOW: "LOW ",
            }.get(s.risk, "UNKN")
            masked = s.value_preview[:60]
            lines.append(f"  [{icon}] {s.pattern_name}: {masked}")
            lines.append(f"         {s.file_path}:{s.line_number}:{s.column}")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────
    # PATTERN-BASED DETECTION
    # ─────────────────────────────────────────────────────────────

    def _pattern_based_scan(self, content: str, file_path: str) -> list[SecretMatch]:
        secrets: list[SecretMatch] = []

        secrets.extend(self._find_pattern(content, file_path, "AWS Access Key ID",
            SecretType.AWS_ACCESS_KEY, RiskLevel.HIGH,
            r'(?:AKIA|ASIA)[0-9A-Z]{16}'))
        secrets.extend(self._find_pattern(content, file_path, "AWS Secret Access Key",
            SecretType.AWS_SECRET_KEY, RiskLevel.CRITICAL,
            r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*["\'][A-Za-z0-9\/+=]{40}["\']'))
        secrets.extend(self._find_pattern(content, file_path, "GitHub Token (ghp)",
            SecretType.GITHUB_TOKEN, RiskLevel.CRITICAL,
            r'gh[pousr]_[A-Za-z0-9_]{36,}'))
        secrets.extend(self._find_pattern(content, file_path, "GitHub Token (gh)",
            SecretType.GITHUB_TOKEN, RiskLevel.CRITICAL,
            r'github[_-]?token\s*[=:]\s*["\'][A-Za-z0-9]{35,}["\']'))
        secrets.extend(self._find_pattern(content, file_path, "GitLab Token",
            SecretType.ACCESS_TOKEN, RiskLevel.CRITICAL,
            r'glpat-[A-Za-z0-9\-_]{20,}'))
        secrets.extend(self._find_pattern(content, file_path, "Slack Token",
            SecretType.ACCESS_TOKEN, RiskLevel.CRITICAL,
            r'xox[baprs]-[A-Za-z0-9\-]{10,}'))
        secrets.extend(self._find_pattern(content, file_path, "JWT Token",
            SecretType.JWT_TOKEN, RiskLevel.HIGH,
            r'eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'))
        secrets.extend(self._find_pattern(content, file_path, "Private Key",
            SecretType.PRIVATE_KEY, RiskLevel.CRITICAL,
            r'-----BEGIN\s*(?:RSA|DSA|EC|OPENSSH|PGP)?\s*PRIVATE\s*KEY-----'))
        secrets.extend(self._find_pattern(content, file_path, "Password Assignment",
            SecretType.PASSWORD, RiskLevel.HIGH,
            r'(?i)(?:password|passwd|pwd)\s*[=:]\s*["\'][^"\']{8,}["\']'))
        secrets.extend(self._find_pattern(content, file_path, "Connection String",
            SecretType.CONNECTION_STRING, RiskLevel.HIGH,
            r'(?i)(?:postgres|mysql|mongodb|redis)://[^\s]+'))
        secrets.extend(self._find_pattern(content, file_path, "Heroku API Key",
            SecretType.API_KEY, RiskLevel.CRITICAL,
            r'heroku[_-]?api[_-]?key\s*[=:]\s*["\'][A-Za-z0-9\-]{36,}["\']'))
        secrets.extend(self._find_pattern(content, file_path, "Twilio API Key",
            SecretType.API_KEY, RiskLevel.CRITICAL,
            r'SK[A-Za-z0-9]{32}'))
        secrets.extend(self._find_pattern(content, file_path, "Google API Key",
            SecretType.API_KEY, RiskLevel.HIGH,
            r'AIza[0-9A-Za-z\-_]{35}'))
        secrets.extend(self._find_pattern(content, file_path, "SendGrid API Key",
            SecretType.API_KEY, RiskLevel.CRITICAL,
            r'SG\.[A-Za-z0-9_\-]{22,}\.[A-Za-z0-9_\-]{43,}'))
        secrets.extend(self._find_pattern(content, file_path, "Stripe API Key",
            SecretType.API_KEY, RiskLevel.CRITICAL,
            r'(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{24,}'))
        secrets.extend(self._find_pattern(content, file_path, "Telegram Bot Token",
            SecretType.ACCESS_TOKEN, RiskLevel.HIGH,
            r'\d{8,10}:[A-Za-z0-9_-]{35,}'))
        secrets.extend(self._find_pattern(content, file_path, "npm token",
            SecretType.ACCESS_TOKEN, RiskLevel.CRITICAL,
            r'npm_[A-Za-z0-9]{36,}'))
        secrets.extend(self._find_pattern(content, file_path, "Docker Hub Token",
            SecretType.ACCESS_TOKEN, RiskLevel.CRITICAL,
            r'dckrpat_[A-Za-z0-9]{24,}'))
        secrets.extend(self._find_pattern(content, file_path, "Slack Webhook",
            SecretType.CONNECTION_STRING, RiskLevel.HIGH,
            r'https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+'))
        secrets.extend(self._find_pattern(content, file_path, "Encryption Key (hex 32)",
            SecretType.ENCRYPTION_KEY, RiskLevel.HIGH,
            r'(?i)(?:encrypt|secret|key)\s*[=:]\s*["\']([A-Fa-f0-9]{32,64})["\']'))

        return secrets

    def _find_pattern(
        self,
        content: str,
        file_path: str,
        pattern_name: str,
        secret_type: SecretType,
        risk: RiskLevel,
        regex: str,
    ) -> list[SecretMatch]:
        matches: list[SecretMatch] = []
        for match in re.finditer(regex, content):
            line_num = content[:match.start()].count("\n") + 1
            col = match.start() - content.rfind("\n", 0, match.start()) - 1
            if col < 0:
                col = match.start()

            value = match.group(0)
            if len(value) > self.MAX_SECRET_LENGTH:
                continue

            masked = self._mask_secret(value)
            entropy = self._shannon_entropy(value)
            context = self._extract_context(content, line_num)

            matches.append(SecretMatch(
                type=secret_type,
                value_preview=masked,
                line_number=line_num,
                column=col,
                file_path=file_path,
                entropy=entropy,
                risk=risk,
                pattern_name=pattern_name,
                context=context,
            ))
        return matches

    # ─────────────────────────────────────────────────────────────
    # ENTROPY-BASED DETECTION
    # ─────────────────────────────────────────────────────────────

    def _entropy_based_scan(self, content: str, file_path: str) -> list[SecretMatch]:
        secrets: list[SecretMatch] = []
        seen: set[tuple[int, str]] = set()

        string_patterns = [
            r'["\']([A-Za-z0-9_\-\.\/+=]{' + str(self.MIN_SECRET_LENGTH) + r',64})["\']',
            r'(?<![A-Za-z])[A-Za-z0-9_\-\.\/+=\\x20]{' + str(self.MIN_SECRET_LENGTH) + r',64}(?![A-Za-z])',
        ]

        for pattern in string_patterns:
            for match in re.finditer(pattern, content):
                value = match.group(1) if match.lastindex else match.group(0)

                if len(value) < self.MIN_SECRET_LENGTH or len(value) > self.MAX_SECRET_LENGTH:
                    continue
                if value.startswith("-----BEGIN"):
                    continue

                if not self._looks_like_secret(value):
                    continue

                line_num = content[:match.start()].count("\n") + 1
                col = match.start() - content.rfind("\n", 0, match.start()) - 1

                if (line_num, value[:30]) in seen:
                    continue
                seen.add((line_num, value[:30]))

                entropy = self._shannon_entropy(value)
                if entropy < self.ENTROPY_THRESHOLD:
                    continue

                masked = self._mask_secret(value)
                context = self._extract_context(content, line_num)

                risk = self._classify_entropy_risk(entropy, value)

                secrets.append(SecretMatch(
                    type=SecretType.GENERIC_HIGH_ENTROPY,
                    value_preview=masked,
                    line_number=line_num,
                    column=col,
                    file_path=file_path,
                    entropy=entropy,
                    risk=risk,
                    pattern_name=f"High Entropy ({entropy:.1f})",
                    context=context,
                ))

        return secrets

    def _looks_like_secret(self, value: str) -> bool:
        if value.startswith(("http://", "https://", "ftp://", "data:")):
            return False
        if value.endswith((".py", ".js", ".ts", ".css", ".html", ".json", ".yaml", ".yml", ".md")):
            return False
        if value.startswith(("./", "../", "/tmp", "/var", "/usr", "/etc", "/home", "node_modules")):
            return False
        if re.match(r'^[A-Za-z]+$', value):
            return False
        if re.match(r'^\d+$', value):
            return False
        if re.match(r'^["\']?[A-Za-z_][A-Za-z0-9_]*["\']?$', value):
            return False
        return True

    def _classify_entropy_risk(self, entropy: float, value: str) -> RiskLevel:
        if entropy >= 5.5 and len(value) >= 30:
            return RiskLevel.CRITICAL
        elif entropy >= 4.8:
            return RiskLevel.HIGH
        elif entropy >= self.ENTROPY_THRESHOLD:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    # ─────────────────────────────────────────────────────────────
    # ALLOWLIST
    # ─────────────────────────────────────────────────────────────

    def _is_allowlisted(self, secret: SecretMatch) -> bool:
        for pattern in self._allowlist_patterns:
            candidate = f"{secret.file_path}:{secret.line_number}:{secret.value_preview}"
            if pattern.search(candidate):
                return True
        return False

    def add_allowlist_entry(self, pattern: str) -> None:
        try:
            self._allowlist_patterns.append(re.compile(pattern))
        except re.error:
            pass

    # ─────────────────────────────────────────────────────────────
    # UTILITIES
    # ─────────────────────────────────────────────────────────────

    def _shannon_entropy(self, value: str) -> float:
        if not value:
            return 0.0
        prob = [float(value.count(c)) / len(value) for c in set(value)]
        return -sum(p * math.log2(p) for p in prob)

    def _mask_secret(self, value: str) -> str:
        if len(value) <= 8:
            return "***"
        return value[:4] + "..." + value[-4:]

    def _extract_context(self, content: str, line_num: int, radius: int = 1) -> str:
        lines = content.split("\n")
        start = max(0, line_num - radius - 1)
        end = min(len(lines), line_num + radius)
        return "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))
