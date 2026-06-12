"""
OWASP Scanner — Top 10 Vulnerability Detection Engine

Automated security analysis that finds the vulnerabilities
that make headlines: injection, broken auth, exposed data,
misconfiguration, and more.

Integrates with:
- Review engine (security axis findings)
- Safety validator (pre-execution blocking)
- Ship engine (pre-deployment gate)

Phase 4, Week 12: Security & Hardening
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Optional

from wigent.core.llm_client import LLMClient
from wigent.safety.validator import SafetyValidator


class OwaspCategory(Enum):
    """OWASP Top 10 2021 categories."""
    A01_BROKEN_ACCESS_CONTROL = "A01:2021-Broken Access Control"
    A02_CRYPTOGRAPHIC_FAILURES = "A02:2021-Cryptographic Failures"
    A03_INJECTION = "A03:2021-Injection"
    A04_INSECURE_DESIGN = "A04:2021-Insecure Design"
    A05_SECURITY_MISCONFIG = "A05:2021-Security Misconfiguration"
    A06_VULNERABLE_COMPONENTS = "A06:2021-Vulnerable and Outdated Components"
    A07_ID_AUTH_FAILURES = "A07:2021-Identification and Authentication Failures"
    A08_SOFTWARE_DATA_INTEGRITY = "A08:2021-Software and Data Integrity Failures"
    A09_LOGGING_MONITORING = "A09:2021-Security Logging and Monitoring Failures"
    A10_SSRF = "A10:2021-Server-Side Request Forgery"


class Severity(Enum):
    """Vulnerability severity."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Vulnerability:
    """A detected security vulnerability."""
    owasp_id: OwaspCategory
    cwe_id: str
    severity: Severity
    confidence: float
    file_path: str
    line_number: int
    end_line: int
    code_snippet: str
    description: str
    remediation: str
    references: list[str] = field(default_factory=list)
    false_positive_likelihood: float = 0.0

    @property
    def unique_id(self) -> str:
        return hashlib.sha256(
            f"{self.file_path}:{self.line_number}:{self.cwe_id}:{self.code_snippet[:50]}".encode()
        ).hexdigest()[:16]


@dataclass
class ScanResult:
    """Complete scan results for a target."""
    target: str
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    scanned_files: int = 0
    scan_duration_seconds: float = 0.0

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.MEDIUM)

    @property
    def is_clean(self) -> bool:
        return self.critical_count == 0 and self.high_count == 0


class OwaspScanner:
    """
    Multi-layer security scanner implementing OWASP Top 10 detection.

    Layers:
    1. Pattern-based: Fast regex/AST detection for known vulnerability signatures
    2. Semantic: AST analysis for data flow and taint tracking
    3. LLM-assisted: Deep analysis for business logic vulnerabilities
    """

    BLOCK_ON_SEVERITY = {Severity.CRITICAL, Severity.HIGH}
    WARN_ON_SEVERITY = {Severity.MEDIUM}

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        safety_validator: Optional[SafetyValidator] = None,
    ):
        self.llm = llm_client
        self.safety = safety_validator

    # ─────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────

    def scan_file(self, file_path: str | Path) -> ScanResult:
        """Scan a single file for all OWASP categories."""
        import time
        start = time.time()

        path = Path(file_path)
        result = ScanResult(target=str(path))

        if not path.exists():
            return result

        content = path.read_text()
        language = self._detect_language(path)

        # Layer 1: Pattern-based detection (fast)
        pattern_vulns = self._pattern_scan(content, str(path), language)
        result.vulnerabilities.extend(pattern_vulns)

        # Layer 2: Semantic analysis (AST-based)
        if language == "python":
            semantic_vulns = self._semantic_scan_python(content, str(path))
            result.vulnerabilities.extend(semantic_vulns)

        # Layer 3: LLM-assisted (slow, high accuracy)
        if self.llm and self._should_deep_scan(result):
            llm_vulns = self._llm_deep_scan(content, str(path), language)
            result.vulnerabilities.extend(llm_vulns)

        result.scanned_files = 1
        result.scan_duration_seconds = time.time() - start

        result.vulnerabilities = self._deduplicate(result.vulnerabilities)

        return result

    def scan_project(
        self,
        root: str | Path,
        pattern: str = "**/*.py",
    ) -> ScanResult:
        """Scan entire project."""
        import time
        start = time.time()

        root_path = Path(root)
        result = ScanResult(target=str(root_path))

        for file_path in root_path.glob(pattern):
            try:
                file_result = self.scan_file(file_path)
                result.vulnerabilities.extend(file_result.vulnerabilities)
                result.scanned_files += 1
            except Exception as e:
                print(f"Warning: Could not scan {file_path}: {e}")

        result.scan_duration_seconds = time.time() - start
        result.vulnerabilities = self._deduplicate(result.vulnerabilities)

        return result

    def scan_diff(self, diff_text: str) -> ScanResult:
        """Scan a git diff for newly introduced vulnerabilities."""
        added_lines = self._extract_added_lines(diff_text)

        result = ScanResult(target="diff")

        by_file: dict[str, list[tuple[int, str]]] = {}
        for line_num, content, file_path in added_lines:
            by_file.setdefault(file_path, []).append((line_num, content))

        for file_path, lines in by_file.items():
            content = "\n".join(l[1] for l in sorted(lines, key=lambda x: x[0]))
            file_result = self.scan_file(file_path)
            result.vulnerabilities.extend(file_result.vulnerabilities)
            result.scanned_files += 1

        return result

    def is_safe_to_deploy(self, result: ScanResult) -> tuple[bool, list[str]]:
        """Check if scan results pass deployment gate."""
        blockers: list[str] = []

        for v in result.vulnerabilities:
            if v.severity in self.BLOCK_ON_SEVERITY:
                blockers.append(
                    f"{v.severity.value.upper()}: {v.owasp_id.value} "
                    f"at {v.file_path}:{v.line_number} ({v.cwe_id})"
                )

        return len(blockers) == 0, blockers

    # ─────────────────────────────────────────────────────────────
    # LAYER 1: PATTERN-BASED DETECTION
    # ─────────────────────────────────────────────────────────────

    def _pattern_scan(
        self,
        content: str,
        file_path: str,
        language: str,
    ) -> list[Vulnerability]:
        """Fast regex-based vulnerability detection."""
        vulns: list[Vulnerability] = []

        vulns.extend(self._scan_sql_injection(content, file_path))
        vulns.extend(self._scan_xss(content, file_path))
        vulns.extend(self._scan_command_injection(content, file_path))
        vulns.extend(self._scan_path_traversal(content, file_path))
        vulns.extend(self._scan_ldap_injection(content, file_path))

        vulns.extend(self._scan_weak_crypto(content, file_path))
        vulns.extend(self._scan_hardcoded_secrets(content, file_path))

        vulns.extend(self._scan_auth_issues(content, file_path))

        vulns.extend(self._scan_misconfiguration(content, file_path))

        vulns.extend(self._scan_logging_issues(content, file_path))

        return vulns

    def _scan_sql_injection(self, content: str, file_path: str) -> list[Vulnerability]:
        """Detect SQL injection vulnerabilities."""
        vulns: list[Vulnerability] = []

        patterns = [
            r'(execute|query|raw|cursor\.execute)\s*\(\s*[f"\'"]',
            r'(execute|query|raw)\s*\(\s*[^,]*\.format\s*\(',
            r'(SELECT|INSERT|UPDATE|DELETE).*[+\'].*\+',
            r'f["\'].*\{.*(?:request|user|input|param|args|kwargs)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE):
                line_num = content[:match.start()].count("\n") + 1
                snippet = self._get_snippet(content, line_num)

                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A03_INJECTION,
                    cwe_id="CWE-89",
                    severity=Severity.CRITICAL,
                    confidence=0.85,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 2,
                    code_snippet=snippet,
                    description="Potential SQL injection: user input concatenated into SQL query",
                    remediation="Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
                    references=[
                        "https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html",
                    ],
                ))

        return vulns

    def _scan_xss(self, content: str, file_path: str) -> list[Vulnerability]:
        """Detect Cross-Site Scripting vulnerabilities."""
        vulns: list[Vulnerability] = []

        patterns = [
            r'render\s*\([^)]*(?:request|user|input|param)',
            r'\.html\s*\(.*(?:request|user|input)',
            r'Markup\s*\(\s*[f"\'"]',
            r'innerHTML\s*=\s*.*(?:request|user|input)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1
                snippet = self._get_snippet(content, line_num)

                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A03_INJECTION,
                    cwe_id="CWE-79",
                    severity=Severity.HIGH,
                    confidence=0.80,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 2,
                    code_snippet=snippet,
                    description="Potential XSS: user input rendered without escaping",
                    remediation="Use auto-escaping templates or bleach.clean() before rendering",
                    references=[
                        "https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html",
                    ],
                ))

        return vulns

    def _scan_command_injection(self, content: str, file_path: str) -> list[Vulnerability]:
        """Detect command injection vulnerabilities."""
        vulns: list[Vulnerability] = []

        patterns = [
            r'os\.system\s*\(.*(?:request|user|input|param)',
            r'subprocess\.\w+\s*\([^)]*shell\s*=\s*True[^)]*(?:request|user|input)',
            r'eval\s*\(.*(?:request|user|input)',
            r'exec\s*\(.*(?:request|user|input)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1
                snippet = self._get_snippet(content, line_num)

                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A03_INJECTION,
                    cwe_id="CWE-78",
                    severity=Severity.CRITICAL,
                    confidence=0.90,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 2,
                    code_snippet=snippet,
                    description="Command injection: user input passed to shell execution",
                    remediation="Use subprocess with list args and shell=False: subprocess.run(['command', arg1, arg2], check=True)",
                    references=[
                        "https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html",
                    ],
                ))

        return vulns

    def _scan_path_traversal(self, content: str, file_path: str) -> list[Vulnerability]:
        """Detect path traversal vulnerabilities."""
        vulns: list[Vulnerability] = []

        patterns = [
            r'open\s*\([^)]*(?:request|user|input|param)',
            r'os\.path\.join\s*\([^)]*(?:request|user|input)',
            r'send_file\s*\([^)]*(?:request|user|input)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1
                snippet = self._get_snippet(content, line_num)

                if "abspath" in snippet or "realpath" in snippet or "normpath" in snippet:
                    continue

                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A01_BROKEN_ACCESS_CONTROL,
                    cwe_id="CWE-22",
                    severity=Severity.HIGH,
                    confidence=0.75,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 2,
                    code_snippet=snippet,
                    description="Path traversal: user input used in file path without validation",
                    remediation="Validate with os.path.realpath() and check against allowlist",
                    references=[
                        "https://cheatsheetseries.owasp.org/cheatsheets/Path_Traversal_Cheat_Sheet.html",
                    ],
                ))

        return vulns

    def _scan_ldap_injection(self, content: str, file_path: str) -> list[Vulnerability]:
        """Detect LDAP injection vulnerabilities."""
        vulns: list[Vulnerability] = []

        patterns = [
            r'ldap3\.Connection\s*\([^)]*search',
            r'\.search_s\s*\([^)]*(?:request|user|input)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1
                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A03_INJECTION,
                    cwe_id="CWE-90",
                    severity=Severity.HIGH,
                    confidence=0.70,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 2,
                    code_snippet=self._get_snippet(content, line_num),
                    description="Potential LDAP injection",
                    remediation="Use parameterized LDAP filters",
                ))

        return vulns

    def _scan_weak_crypto(self, content: str, file_path: str) -> list[Vulnerability]:
        """Detect weak cryptographic practices."""
        vulns: list[Vulnerability] = []

        weak_patterns = {
            "md5": (r'\bmd5\b', "MD5 is cryptographically broken"),
            "sha1": (r'\bsha1\b', "SHA-1 is deprecated for security use"),
            "des": (r'\bDES\b', "DES has insufficient key length (56 bits)"),
            "rc4": (r'\bRC4\b', "RC4 is broken and deprecated"),
            "ecb": (r'\bECB\b', "ECB mode leaks data patterns"),
            "ssl": (r'\bssl\.(?!SSLContext\b)', "SSL is deprecated, use TLS"),
        }

        for name, (pattern, message) in weak_patterns.items():
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1

                snippet = self._get_snippet(content, line_num)
                if "deprecated" in snippet.lower() or "do not use" in snippet.lower():
                    continue

                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A02_CRYPTOGRAPHIC_FAILURES,
                    cwe_id="CWE-327",
                    severity=Severity.HIGH,
                    confidence=0.85,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 1,
                    code_snippet=snippet,
                    description=message,
                    remediation=f"Replace {name.upper()} with modern alternative (SHA-256, AES-GCM, TLS 1.3)",
                    references=[
                        "https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html",
                    ],
                ))

        iv_patterns = [
            r'iv\s*=\s*b?["\'][^"\']{8,16}["\']',
            r'nonce\s*=\s*b?["\'][^"\']{8,16}["\']',
        ]
        for pattern in iv_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1
                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A02_CRYPTOGRAPHIC_FAILURES,
                    cwe_id="CWE-329",
                    severity=Severity.MEDIUM,
                    confidence=0.70,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 1,
                    code_snippet=self._get_snippet(content, line_num),
                    description="Hardcoded IV/nonce: reduces security of encryption",
                    remediation="Generate random IV/nonce for each encryption operation",
                ))

        return vulns

    def _scan_hardcoded_secrets(self, content: str, file_path: str) -> list[Vulnerability]:
        """Detect hardcoded secrets and credentials."""
        vulns: list[Vulnerability] = []

        secret_patterns = [
            (r'api[_-]?key\s*[=:]\s*["\'][a-zA-Z0-9]{16,}["\']', "API Key", "CWE-798"),
            (r'secret[_-]?key\s*[=:]\s*["\'][a-zA-Z0-9]{16,}["\']', "Secret Key", "CWE-798"),
            (r'password\s*[=:]\s*["\'][^"\']{8,}["\']', "Password", "CWE-798"),
            (r'token\s*[=:]\s*["\'][a-zA-Z0-9]{20,}["\']', "Token", "CWE-798"),
            (r'aws_access_key_id\s*[=:]\s*["\']AKIA[0-9A-Z]{16}["\']', "AWS Access Key", "CWE-798"),
            (r'private[_-]?key\s*[=:]\s*["\']-----BEGIN', "Private Key", "CWE-798"),
            (r'github[_-]?token\s*[=:]\s*["\']gh[pousr]_[a-zA-Z0-9]{36}["\']', "GitHub Token", "CWE-798"),
        ]

        for pattern, secret_type, cwe in secret_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1

                if "test" in file_path.lower() or "example" in file_path.lower():
                    continue

                matched_text = match.group(0)
                masked = re.sub(r'["\'][^"\']+["\']', '"***REDACTED***"', matched_text)

                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A02_CRYPTOGRAPHIC_FAILURES,
                    cwe_id=cwe,
                    severity=Severity.CRITICAL,
                    confidence=0.90,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 1,
                    code_snippet=masked,
                    description=f"Hardcoded {secret_type} detected in source code",
                    remediation=f"Move {secret_type} to environment variables or secret manager (Vault, AWS Secrets Manager, etc.)",
                    references=[
                        "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
                    ],
                ))

        return vulns

    def _scan_auth_issues(self, content: str, file_path: str) -> list[Vulnerability]:
        """Detect authentication and authorization flaws."""
        vulns: list[Vulnerability] = []

        weak_password = [
            r'len\s*\(\s*password\s*\)\s*[<>=]+\s*\d',
            r'password\s*==\s*["\']',
        ]

        for pattern in weak_password:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1
                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A07_ID_AUTH_FAILURES,
                    cwe_id="CWE-521",
                    severity=Severity.MEDIUM,
                    confidence=0.60,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 2,
                    code_snippet=self._get_snippet(content, line_num),
                    description="Weak password policy or hardcoded password validation",
                    remediation="Enforce NIST 800-63B password guidelines (min 8 chars, check against breached passwords)",
                ))

        return vulns

    def _scan_misconfiguration(self, content: str, file_path: str) -> list[Vulnerability]:
        """Detect security misconfigurations."""
        vulns: list[Vulnerability] = []

        debug_patterns = [
            r'DEBUG\s*=\s*True',
            r'FLASK_DEBUG\s*=\s*True',
            r'app\.run\s*\([^)]*debug\s*=\s*True',
        ]

        for pattern in debug_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1

                if "test" in file_path.lower() or "dev" in file_path.lower():
                    continue

                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A05_SECURITY_MISCONFIG,
                    cwe_id="CWE-489",
                    severity=Severity.HIGH,
                    confidence=0.95,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 1,
                    code_snippet=self._get_snippet(content, line_num),
                    description="Debug mode enabled in production code",
                    remediation="Set DEBUG=False in production. Use environment-based configuration.",
                ))

        cors_patterns = [
            r'CORS\s*\([^)]*origins\s*=\s*["\']\*["\']',
            r'@cross_origin\s*\([^)]*origins\s*=\s*["\']\*["\']',
        ]

        for pattern in cors_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1
                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A05_SECURITY_MISCONFIG,
                    cwe_id="CWE-942",
                    severity=Severity.MEDIUM,
                    confidence=0.80,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 1,
                    code_snippet=self._get_snippet(content, line_num),
                    description="Overly permissive CORS: allows any origin to access resources",
                    remediation="Specify exact allowed origins instead of wildcard '*'",
                ))

        return vulns

    def _scan_logging_issues(self, content: str, file_path: str) -> list[Vulnerability]:
        """Detect logging and monitoring failures."""
        vulns: list[Vulnerability] = []

        log_patterns = [
            r'(?:log|logger)\.\w+\s*\([^)]*password',
            r'(?:log|logger)\.\w+\s*\([^)]*token',
            r'(?:log|logger)\.\w+\s*\([^)]*secret',
            r'(?:log|logger)\.\w+\s*\([^)]*credit_card',
            r'(?:log|logger)\.\w+\s*\([^)]*ssn',
        ]

        for pattern in log_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1
                vulns.append(Vulnerability(
                    owasp_id=OwaspCategory.A09_LOGGING_MONITORING,
                    cwe_id="CWE-532",
                    severity=Severity.HIGH,
                    confidence=0.85,
                    file_path=file_path,
                    line_number=line_num,
                    end_line=line_num + 1,
                    code_snippet=self._get_snippet(content, line_num),
                    description="Sensitive data may be logged",
                    remediation="Redact or hash sensitive fields before logging. Use structured logging with field allowlists.",
                ))

        except_pass = r'except\s+[^:]*:\s*\n\s*pass'
        for match in re.finditer(except_pass, content):
            line_num = content[:match.start()].count("\n") + 1
            vulns.append(Vulnerability(
                owasp_id=OwaspCategory.A09_LOGGING_MONITORING,
                cwe_id="CWE-390",
                severity=Severity.LOW,
                confidence=0.70,
                file_path=file_path,
                line_number=line_num,
                end_line=line_num + 2,
                code_snippet=self._get_snippet(content, line_num),
                description="Exception silently swallowed: no logging or handling",
                remediation="Log exceptions with appropriate severity: logger.exception('Context')",
            ))

        return vulns

    # ─────────────────────────────────────────────────────────────
    # LAYER 2: SEMANTIC ANALYSIS
    # ─────────────────────────────────────────────────────────────

    def _semantic_scan_python(self, content: str, file_path: str) -> list[Vulnerability]:
        """AST-based semantic analysis for Python."""
        vulns: list[Vulnerability] = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return vulns

        taint_sources = {
            "request.args", "request.form", "request.json", "request.data",
            "request.headers", "request.cookies", "request.files",
            "input", "sys.argv", "os.environ.get",
        }

        taint_sinks = {
            "execute": "SQL injection",
            "raw": "SQL injection",
            "system": "Command injection",
            "popen": "Command injection",
            "eval": "Code injection",
            "exec": "Code injection",
            "render_template_string": "XSS",
            "Markup": "XSS",
            "send_file": "Path traversal",
            "open": "Path traversal",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in taint_sinks:
                    for arg in node.args:
                        if self._is_tainted(arg, taint_sources):
                            line_num = node.lineno
                            vulns.append(Vulnerability(
                                owasp_id=OwaspCategory.A03_INJECTION,
                                cwe_id="CWE-94" if "injection" in taint_sinks[func_name] else "CWE-78",
                                severity=Severity.CRITICAL,
                                confidence=0.90,
                                file_path=file_path,
                                line_number=line_num,
                                end_line=node.end_lineno,
                                code_snippet=self._get_snippet(content, line_num),
                                description=f"{taint_sinks[func_name]}: tainted data reaches sink '{func_name}'",
                                remediation="Validate and sanitize input before passing to sensitive functions",
                            )))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in ("pickle.loads", "yaml.load", "marshal.loads"):
                    if func_name == "yaml.load":
                        has_safe = any(
                            isinstance(kw, ast.keyword) and kw.arg == "Loader"
                            and self._get_attr_name(kw.value) == "SafeLoader"
                            for kw in node.keywords
                        )
                        if has_safe:
                            continue

                    line_num = node.lineno
                    vulns.append(Vulnerability(
                        owasp_id=OwaspCategory.A08_SOFTWARE_DATA_INTEGRITY,
                        cwe_id="CWE-502",
                        severity=Severity.CRITICAL,
                        confidence=0.85,
                        file_path=file_path,
                        line_number=line_num,
                        end_line=node.end_lineno,
                        code_snippet=self._get_snippet(content, line_num),
                        description=f"Insecure deserialization: {func_name} can execute arbitrary code",
                        remediation="Use yaml.safe_load(), json.loads(), or restrict pickle with allowlist",
                    ))

        return vulns

    def _is_tainted(self, node: ast.AST, sources: set[str]) -> bool:
        """Check if an AST node contains tainted data."""
        if isinstance(node, ast.Name):
            return node.id in sources
        elif isinstance(node, ast.Attribute):
            attr_chain = self._get_attr_chain(node)
            return attr_chain in sources or any(s in attr_chain for s in sources)
        elif isinstance(node, ast.BinOp):
            return self._is_tainted(node.left, sources) or self._is_tainted(node.right, sources)
        elif isinstance(node, ast.JoinedStr):
            return any(self._is_tainted(v, sources) for v in node.values)
        elif isinstance(node, ast.Call):
            return any(self._is_tainted(arg, sources) for arg in node.args)
        return False

    def _get_call_name(self, node: ast.Call) -> str:
        """Get full function name from Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return self._get_attr_chain(node.func)
        return ""

    def _get_attr_name(self, node: ast.AST) -> str:
        """Get attribute name from Attribute or Name node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return ""

    def _get_attr_chain(self, node: ast.Attribute) -> str:
        """Get full attribute chain (e.g., 'request.args.get')."""
        parts: list[str] = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    # ─────────────────────────────────────────────────────────────
    # LAYER 3: LLM-ASSISTED DEEP SCAN
    # ─────────────────────────────────────────────────────────────

    def _should_deep_scan(self, result: ScanResult) -> bool:
        """Determine if LLM deep scan is warranted."""
        if not result.vulnerabilities:
            return True
        avg_confidence = sum(v.confidence for v in result.vulnerabilities) / len(result.vulnerabilities)
        return avg_confidence < 0.8

    def _llm_deep_scan(
        self,
        content: str,
        file_path: str,
        language: str,
    ) -> list[Vulnerability]:
        """Use LLM for business logic and complex vulnerability detection."""
        if not self.llm:
            return []

        if not self._is_security_relevant(content):
            return []

        prompt = f"""Analyze this {language} code for security vulnerabilities that automated tools miss.

Focus on:
- Business logic flaws (race conditions, TOCTOU, business rule bypass)
- Authorization bypasses (missing checks, IDOR)
- Data exposure (over-fetching, missing field-level auth)
- Complex injection (second-order, stored, blind)
- Cryptographic misuse (key reuse, weak randomness)

File: {file_path}

```python
{content[:2000]}
```

For each vulnerability found, output:
```
SEVERITY: [CRITICAL|HIGH|MEDIUM|LOW]
CWE: CWE-XXX
LINE: <line_number>
DESCRIPTION: <specific vulnerability>
REMEDIATION: <concrete fix>
CONFIDENCE: 0.0-1.0
```

If no vulnerabilities: "PASS: No security concerns identified."
"""

        try:
            response = self.llm.complete(prompt, temperature=0.1)
            return self._parse_llm_findings(response, file_path)
        except Exception:
            return []

    def _is_security_relevant(self, content: str) -> bool:
        """Quick check if file handles security-sensitive operations."""
        keywords = [
            "auth", "login", "password", "token", "session", "permission",
            "role", "admin", "user", "account", "payment", "billing",
            "encrypt", "hash", "sign", "verify", "validate",
        ]
        content_lower = content.lower()
        return any(kw in content_lower for kw in keywords)

    def _parse_llm_findings(self, response: str, file_path: str) -> list[Vulnerability]:
        """Parse LLM vulnerability findings."""
        vulns: list[Vulnerability] = []

        raw_findings = re.split(r'\n(?=SEVERITY:)', response.strip())
        for raw in raw_findings:
            if "PASS:" in raw:
                continue

            sev_match = re.search(r'SEVERITY:\s*(\w+)', raw)
            cwe_match = re.search(r'CWE:\s*(CWE-\d+)', raw)
            line_match = re.search(r'LINE:\s*(\d+)', raw)
            desc_match = re.search(r'DESCRIPTION:\s*(.+?)(?=REMEDIATION:|$)', raw, re.DOTALL)
            rem_match = re.search(r'REMEDIATION:\s*(.+?)(?=CONFIDENCE:|$)', raw, re.DOTALL)
            conf_match = re.search(r'CONFIDENCE:\s*(\d+\.?\d*)', raw)

            if not sev_match or not desc_match:
                continue

            try:
                severity = Severity(sev_match.group(1).lower())
            except ValueError:
                severity = Severity.MEDIUM

            line_num = int(line_match.group(1)) if line_match else 1

            vulns.append(Vulnerability(
                owasp_id=OwaspCategory.A04_INSECURE_DESIGN,
                cwe_id=cwe_match.group(1) if cwe_match else "CWE-Unknown",
                severity=severity,
                confidence=float(conf_match.group(1)) if conf_match else 0.5,
                file_path=file_path,
                line_number=line_num,
                end_line=line_num + 2,
                code_snippet="",
                description=desc_match.group(1).strip(),
                remediation=rem_match.group(1).strip() if rem_match else "Review and fix manually",
                false_positive_likelihood=0.3,
            ))

        return vulns

    # ─────────────────────────────────────────────────────────────
    # UTILITIES
    # ─────────────────────────────────────────────────────────────

    def _get_snippet(self, content: str, line_num: int, context: int = 2) -> str:
        """Extract code snippet around a line."""
        lines = content.split("\n")
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)
        return "\n".join(f"{i + 1:4d}: {lines[i]}" for i in range(start, end))

    def _deduplicate(self, vulns: list[Vulnerability]) -> list[Vulnerability]:
        """Remove duplicate vulnerabilities."""
        seen: set[tuple] = set()
        unique: list[Vulnerability] = []
        for v in vulns:
            key = (v.file_path, v.line_number, v.cwe_id, v.description[:50])
            if key not in seen:
                seen.add(key)
                unique.append(v)
        return unique

    def _extract_added_lines(self, diff_text: str) -> list[tuple[int, str, str]]:
        """Extract added lines from git diff."""
        added: list[tuple[int, str, str]] = []
        current_file = ""

        for line in diff_text.split("\n"):
            if line.startswith("+++"):
                current_file = line[6:]
            elif line.startswith("+") and not line.startswith("+++"):
                line_num = len(added) + 1
                added.append((line_num, line[1:], current_file))

        return added

    def _detect_language(self, file_path: Path) -> str:
        """Detect language from file extension."""
        ext = file_path.suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
        }
        return mapping.get(ext, "unknown")

    # ─────────────────────────────────────────────────────────────
    # REPORTING
    # ─────────────────────────────────────────────────────────────

    def generate_report(self, result: ScanResult) -> str:
        """Generate SARIF-like JSON report."""
        data = {
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Wigent OWASP Scanner",
                        "version": "1.0.0",
                    }
                },
                "results": [
                    {
                        "ruleId": v.cwe_id,
                        "message": {"text": v.description},
                        "locations": [{
                            "physicalLocation": {
                                "artifactLocation": {"uri": v.file_path},
                                "region": {
                                    "startLine": v.line_number,
                                    "endLine": v.end_line,
                                    "snippet": {"text": v.code_snippet},
                                }
                            }
                        }],
                        "properties": {
                            "owasp": v.owasp_id.value,
                            "severity": v.severity.value,
                            "confidence": v.confidence,
                            "remediation": v.remediation,
                        }
                    }
                    for v in result.vulnerabilities
                ],
            }]
        }
        return json.dumps(data, indent=2)

    def export_sarif(self, result: ScanResult, path: Path) -> None:
        """Export results as SARIF for GitHub/CodeQL integration."""
        path.write_text(self.generate_report(result))

    def print_summary(self, result: ScanResult) -> None:
        """Print console summary."""
        print(f"\n{'=' * 60}")
        print(f"  OWASP SCAN RESULTS: {result.target}")
        print(f"{'=' * 60}")
        print(f"  Files scanned: {result.scanned_files}")
        print(f"  Duration: {result.scan_duration_seconds:.1f}s")
        print()

        if result.is_clean:
            print("  ✅ NO VULNERABILITIES FOUND")
        else:
            print(f"  🔴 CRITICAL: {result.critical_count}")
            print(f"  🟠 HIGH: {result.high_count}")
            print(f"  🟡 MEDIUM: {result.medium_count}")
            print()

            for v in sorted(result.vulnerabilities, key=lambda x: x.confidence, reverse=True)[:10]:
                icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}.get(v.severity.value, "⚪")
                print(f"  {icon} {v.cwe_id} | {v.file_path}:{v.line_number}")
                print(f"     {v.description[:80]}")
                print()

        print(f"{'=' * 60}")
