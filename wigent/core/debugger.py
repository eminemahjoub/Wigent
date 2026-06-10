# ════════════════════════════════════════
# wigent — Debugger Mode
# Role: Root-cause analysis, minimal fix, regression prevention
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Debugger mode agent — diagnoses bugs via reproduce→analyse→fix→verify.

Temperature: 0.1 (analytical, precise)
Tools: read, run_command, search — no write tools until root cause found.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from wigent.config import settings
from wigent.config.modes import get_mode
from wigent.core.loop import AgentLoop
from wigent.models.base_model import LLMResponse
from wigent.models.model_factory import factory as model_factory
from wigent.prompts import build_mode_prompt

logger = logging.getLogger(__name__)

DEBUGGER_TEMPERATURE = 0.1


class DebuggerAgent:
    """Debugging agent that follows a reproduce→diagnose→fix→verify pipeline.

    Uses ``AgentLoop`` under the hood for multi-step investigation and
    provides higher-level methods for error analysis, root cause
    identification, and fix verification.

    Usage
    -----
        debugger = DebuggerAgent()
        diagnosis = debugger.analyze_error("TypeError: ...", "Traceback ...")
        rca = debugger.find_root_cause(diagnosis)
        fix = debugger.propose_fix(rca)
        debugger.apply_fix(fix, approve=True)
        debugger.verify_fix()
    """

    MODE = "debugger"

    def __init__(self, model: Any | None = None) -> None:
        self._model = model or model_factory.get_active_model()
        self._mode_cfg = get_mode(self.MODE)
        self._diagnosis_cache: dict[str, Any] = {}
        self._fixes_applied: list[dict[str, Any]] = []
        self._metrics: dict[str, Any] = {
            "bugs_analysed": 0,
            "root_causes_found": 0,
            "fixes_applied": 0,
            "fixes_verified": 0,
            "total_debug_time": 0.0,
        }

    # ── Public API ───────────────────────────────────────────────────

    def analyze_error(
        self,
        error_msg: str,
        trace: str = "",
        context_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Analyse an error message and stack trace to produce a diagnosis.

        Reads relevant source files, searches the codebase for related
        code, and returns a structured diagnosis.

        Args:
            error_msg:     The error message or description.
            trace:         Optional stack trace / full error output.
            context_files: Optional list of files to read for context.

        Returns:
            A dict with ``error_type``, ``symptom``, ``location``,
            ``hypothesis``, and ``suggested_investigation``.
        """
        t0 = time.perf_counter()

        # Read context files if provided.
        context = ""
        if context_files:
            from wigent.tools import read_file
            for fpath in context_files:
                try:
                    r = read_file(file_path=fpath)
                    if isinstance(r, dict) and r.get("success"):
                        content = r.get("content", "")
                        if isinstance(content, str):
                            context += f"\n--- {fpath} ---\n{content[:2000]}\n"
                except Exception:
                    pass

        prompt = (
            "You are an expert debugger. Analyse the following error and "
            "produce a structured diagnosis.\n\n"
            f"Error message:\n```\n{error_msg}\n```\n"
        )
        if trace:
            prompt += f"Stack trace:\n```\n{trace[:4000]}\n```\n"
        if context:
            prompt += f"Context files:\n{context}\n"

        prompt += (
            "Respond in this exact JSON format:\n"
            '{\n'
            '  "error_type": "TypeError | KeyError | ImportError | LogicError | Unknown",\n'
            '  "symptom": "What the user observes (1-2 sentences)",\n'
            '  "location": {"file": "path/to/file.py", "line": 42, "function": "func_name"},\n'
            '  "hypothesis": "Initial theory about the root cause",\n'
            '  "confidence": 0.8,\n'
            '  "suggested_investigation": ["Read file X", "Run command Y", "Check value Z"]\n'
            '}'
        )

        diagnosis = self._llm_json(prompt, {
            "error_type": "Unknown", "symptom": error_msg[:200],
            "location": {}, "hypothesis": "",
            "confidence": 0.0, "suggested_investigation": [],
        })

        duration = time.perf_counter() - t0
        self._metrics["bugs_analysed"] += 1
        self._diagnosis_cache = diagnosis
        logger.info(
            "analyze_error: %s  location=%s  confidence=%.2f  duration=%.1fs",
            diagnosis.get("error_type"), diagnosis.get("location", {}).get("file", "?"),
            diagnosis.get("confidence", 0), duration,
        )

        return diagnosis

    def reproduce_issue(self, steps: str = "") -> dict[str, Any]:
        """Attempt to reproduce a bug by running the relevant command.

        Args:
            steps: Specific commands or reproduction steps. If empty,
                   uses the investigation steps from the last diagnosis.

        Returns:
            A dict with ``success`` (bug reproduced), ``command`` run,
            ``output``, and ``exit_code``.
        """
        # Build reproduction command from diagnosis or user input.
        if not steps:
            investigation = self._diagnosis_cache.get("suggested_investigation", [])
            steps = "\n".join(investigation)

        from wigent.tools import run_command

        # Determine the command to run.
        command = self._extract_command(steps)
        if not command:
            return {
                "success": False,
                "error": "Could not determine a command to run from the input.",
                "input": steps,
            }

        logger.info("reproduce_issue: running %s", command)

        try:
            result = run_command(command=command, timeout=30)
            success = isinstance(result, dict) and result.get("success", False)
            output = result.get("output", "") if isinstance(result, dict) else str(result)
            return {
                "success": success,
                "reproduced": not success,
                "command": command,
                "output": str(result)[:3000] if isinstance(result, dict) else str(result)[:3000],
                "exit_code": result.get("exit_code", -1) if isinstance(result, dict) else -1,
            }
        except Exception as exc:
            return {"success": False, "reproduced": None, "error": str(exc)}

    def find_root_cause(self, analysis: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform deep root cause analysis using the agent loop.

        Runs a focused investigation via the debug loop: reads files,
        runs diagnostic commands, forms and tests hypotheses.

        Args:
            analysis: Optional diagnosis from ``analyze_error()``. Uses
                      the last cached diagnosis if omitted.

        Returns:
            A dict with ``root_cause``, ``evidence``, ``severity``,
            ``fix_strategy``, and ``affected_files``.
        """
        t0 = time.perf_counter()
        analysis = analysis or self._diagnosis_cache

        # Use the agent loop for deep investigation.
        task = (
            f"Investigate and find the root cause of this bug:\n\n"
            f"Error type: {analysis.get('error_type', 'Unknown')}\n"
            f"Symptom: {analysis.get('symptom', '')}\n"
            f"Hypothesis: {analysis.get('hypothesis', '')}\n"
            f"Location: {json.dumps(analysis.get('location', {}))}\n\n"
            "Follow this method:\n"
            "1. READ the failing code and surrounding context\n"
            "2. RUN diagnostic commands to gather evidence\n"
            "3. FORM a hypothesis about the root cause\n"
            "4. TEST the hypothesis\n"
            "5. CONFIRM with evidence\n\n"
            "When you have identified the root cause, produce a structured report."
        )

        loop = self._build_loop()
        state = loop.run(task, mode=self.MODE)

        # Extract structured root cause via one-shot LLM.
        prompt = (
            "Based on the following investigation, produce a structured "
            "root cause analysis.\n\n"
            f"Investigation results:\n{state.get('result', '')[:6000]}\n\n"
            "Respond in JSON:\n"
            '{\n'
            '  "root_cause": "Clear explanation of why the bug occurs",\n'
            '  "evidence": ["Evidence point 1", "Evidence point 2"],\n'
            '  "severity": "Critical | High | Medium | Low",\n'
            '  "fix_strategy": "High-level approach to fix",\n'
            '  "fix_type": "one_line | multi_line | refactor | design_change",\n'
            '  "affected_files": ["path/to/file1.py"],\n'
            '  "regression_risk": "Low | Medium | High"\n'
            '}'
        )

        rca = self._llm_json(prompt, {
            "root_cause": "", "evidence": [], "severity": "Medium",
            "fix_strategy": "", "fix_type": "multi_line",
            "affected_files": [], "regression_risk": "Medium",
        })

        duration = time.perf_counter() - t0
        self._metrics["root_causes_found"] += 1
        logger.info(
            "find_root_cause: %s  severity=%s  files=%s  duration=%.1fs",
            rca.get("root_cause", "")[:80], rca.get("severity"),
            rca.get("affected_files"), duration,
        )

        return rca

    def propose_fix(self, root_cause: dict[str, Any]) -> dict[str, Any]:
        """Produce a detailed fix plan from a root cause analysis.

        Args:
            root_cause: Output from ``find_root_cause()``.

        Returns:
            A dict with ``description``, ``changes`` (list of
            file/change pairs), ``tests_to_add``, and ``risks``.
        """
        prompt = (
            "You are an expert debugger. Propose a minimal fix for the "
            "following root cause.\n\n"
            f"Root cause: {json.dumps(root_cause, indent=2)}\n\n"
            "Rules:\n"
            "- Change the minimum number of lines.\n"
            "- Fix the root cause, not the symptom.\n"
            "- Do not refactor unrelated code.\n\n"
            "Respond in JSON:\n"
            '{\n'
            '  "description": "What the fix does and why",\n'
            '  "changes": [\n'
            '    {"file": "path/to/file.py", "action": "modify | create | delete", '
            '"detail": "What to change"}\n'
            '  ],\n'
            '  "tests_to_add": ["What test should be added to prevent regression"],\n'
            '  "estimated_lines_changed": 3,\n'
            '  "risks": ["Risk 1", "Risk 2"],\n'
            '  "regression_test": "Command to run to verify no regression"\n'
            '}'
        )

        fix_plan = self._llm_json(prompt, {
            "description": "", "changes": [], "tests_to_add": [],
            "estimated_lines_changed": 0, "risks": [], "regression_test": "",
        })

        logger.info(
            "propose_fix: %d changes, ~%d lines  description=%s",
            len(fix_plan.get("changes", [])),
            fix_plan.get("estimated_lines_changed", 0),
            fix_plan.get("description", "")[:60],
        )

        return fix_plan

    def apply_fix(
        self,
        fix_plan: dict[str, Any],
        approve: bool = False,
    ) -> dict[str, Any]:
        """Apply a fix plan using the agent loop.

        Args:
            fix_plan: Output from ``propose_fix()``.
            approve:  If ``True``, applies the fix. If ``False``, returns
                      a preview of the changes.

        Returns:
            The resulting ``AgentState`` from the fix loop.
        """
        t0 = time.perf_counter()

        changes_json = json.dumps(fix_plan.get("changes", []), indent=2)

        task = (
            f"Apply the following bug fix:\n\n"
            f"Description: {fix_plan.get('description', '')}\n\n"
            f"Changes:\n{changes_json}\n\n"
        )

        if not approve:
            task += (
                "DO NOT make any changes. Instead, read the affected files "
                "and report a detailed preview of what would change, line by line."
            )
        else:
            task += (
                "Read each file first, then apply the minimal changes described. "
                f"After applying, run: {fix_plan.get('regression_test', '')}"
            )

        loop = self._build_loop()
        state = loop.run(task, mode=self.MODE)

        duration = time.perf_counter() - t0
        if approve:
            self._metrics["fixes_applied"] += 1
            self._fixes_applied.append({
                "fix_plan": fix_plan,
                "state": state,
                "timestamp": time.time(),
            })

        logger.info(
            "apply_fix: approved=%s  duration=%.1fs",
            approve, duration,
        )

        return state

    def verify_fix(self) -> dict[str, Any]:
        """Verify that the applied fix resolves the original issue.

        Re-runs the reproduction command from the diagnosis and checks
        that the error is gone.

        Returns:
            A dict with ``fix_verified``, ``reproduction_output``,
            ``regression_result``, and ``recommendation``.
        """
        t0 = time.perf_counter()

        # Step 1: re-run the original reproduction command.
        repro_result = self.reproduce_issue()

        # Step 2: run regression tests.
        from wigent.tools import run_command
        regression_output = ""
        try:
            r = run_command(command="python3 -m pytest --no-header -q --tb=short 2>&1 | tail -10")
            regression_output = str(r)[:1000] if isinstance(r, dict) else str(r)[:1000]
        except Exception:
            regression_output = "Could not run regression tests."

        fix_verified = repro_result.get("reproduced") is False

        duration = time.perf_counter() - t0

        if fix_verified:
            self._metrics["fixes_verified"] += 1

        result = {
            "fix_verified": fix_verified,
            "reproduction_output": repro_result.get("output", ""),
            "regression_result": regression_output,
            "duration": round(duration, 2),
            "recommendation": (
                "Fix verified. Bug is resolved."
                if fix_verified
                else "Fix did not resolve the issue. Re-running diagnosis."
            ),
        }

        logger.info(
            "verify_fix: verified=%s  duration=%.1fs",
            fix_verified, duration,
        )

        return result

    def document_fix(self, bug: dict[str, Any], fix: dict[str, Any]) -> dict[str, Any]:
        """Document a bug and its fix for future reference.

        Adds comments to the affected files and produces a debug report.

        Args:
            bug: The diagnosis / root cause analysis.
            fix: The applied fix plan.

        Returns:
            A dict with ``report`` (markdown string) and
            ``comments_added`` (list of files with comments).
        """
        report = (
            "## Debug Report\n\n"
            f"### Bug\n{bug.get('symptom', bug.get('root_cause', 'Unknown'))}\n\n"
            f"### Root Cause\n{bug.get('root_cause', '')}\n\n"
            f"### Fix Applied\n{fix.get('description', '')}\n\n"
            f"### Changes\n"
        )
        for change in fix.get("changes", []):
            report += f"- `{change.get('file', '')}`: {change.get('detail', '')}\n"

        # Add regression comments to affected files.
        comments_added: list[str] = []
        for change in fix.get("changes", []):
            fpath = change.get("file", "")
            if not fpath or not fpath.endswith(".py"):
                continue

            from wigent.tools import read_file, write_file

            try:
                r = read_file(path=fpath)
                if not isinstance(r, dict) or not r.get("success"):
                    continue
                content = r.get("content", "")
                if not isinstance(content, str):
                    continue

                comment = (
                    f"# Regression: {bug.get('symptom', 'bug fix')[:80]}\n\n"
                )
                write_file(path=fpath, content=comment + content)
                comments_added.append(fpath)
            except Exception:
                pass

        logger.info("document_fix: report generated, %d files commented", len(comments_added))

        return {"report": report, "comments_added": comments_added}

    def get_fixes_applied(self) -> list[dict[str, Any]]:
        """Return history of fixes applied in this session."""
        return list(self._fixes_applied)

    def get_metrics(self) -> dict[str, Any]:
        """Return metrics tracked by this agent."""
        return dict(self._metrics)

    # ── Internals ────────────────────────────────────────────────────

    def _build_loop(self) -> AgentLoop:
        return AgentLoop(
            model=self._model,
            mode=self.MODE,
            enable_checkpoints=False,
        )

    def _llm_json(self, prompt: str, default: Any) -> Any:
        """Call the LLM and parse a JSON response."""
        try:
            response: LLMResponse = self._model.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
                temperature=DEBUGGER_TEMPERATURE,
            )
            content = (response.content or "").strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return json.loads(content)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("LLM JSON parse failed: %s", exc)
            return default

    @staticmethod
    def _extract_command(text: str) -> str | None:
        """Extract a shell command from text.

        Looks for code-fenced commands, lines starting with ``$``, or
        raw command-like strings.
        """
        lines = text.strip().splitlines()

        # Look for ```bash ... ``` blocks.
        in_block = False
        for line in lines:
            if line.strip().startswith("```bash") or line.strip().startswith("```sh"):
                in_block = True
                continue
            if line.strip().startswith("```") and in_block:
                break
            if in_block and line.strip():
                return line.strip()

        # Look for $ command lines.
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("$ "):
                return stripped[2:].strip()

        # Take the first non-empty line that looks like a command.
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                return stripped

        return None


__all__ = ["DebuggerAgent"]
