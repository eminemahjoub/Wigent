# ════════════════════════════════════════
# wigent — Interview Mode
# Role: Structured one-question-at-a-time requirement gathering
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""One-question-at-a-time interview that builds a structured spec document.

Asks targeted questions, scores confidence by detecting technical details,
constraints, and user personas in each answer, and stops when confidence
reaches 95 % or 15 questions have been asked.

Slash command integration
-------------------------
Register ``/interview [project name]`` in the CLI command handler::

    # wigent/cli/commands.py — CommandHandler.execute()
    from wigent.modes.interview import InterviewMode

    _interview_mode: InterviewMode | None = None

    def _cmd_interview(self, args: str) -> CommandResult:
        name = args or "Untitled"
        _interview_mode = InterviewMode(project_name=name)
        return CommandResult(
            output=f\"\"\"Starting interview for **{name}**.
            \\n\\n{_interview_mode.current_question}\"\"\",
            mode="interview",
        )

Then in the main chat handler, when ``mode == "interview"``::

    if _interview_mode and not _interview_mode.is_done:
        response = _interview_mode.submit_answer(user_input)
        if _interview_mode.is_done:
            print(_interview_mode.generate_spec())
        else:
            print(response)

Usage
-----
    mode = InterviewMode("MyApp")
    mode.submit_answer("A REST API for managing invoices")
    mode.submit_answer("Accountants and office managers")
    # … continue …
    print(mode.generate_spec())  # Final document
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class BaseMode(ABC):
    """Abstract base for all Wigent modes.

    Subclasses implement ``execute()`` to run their workflow and return
    structured results.
    """

    @abstractmethod
    def execute(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run the mode with the given task and return results."""
        ...


# ── Compile-once patterns ───────────────────────────────────────────────

_TECH_RE = re.compile(
    r"\b(python|javascript|typescript|react|angular|vue|svelte|node|deno|"
    r"django|flask|fastapi|spring|rails|laravel|gin|echo|"
    r"postgresql|mysql|mongodb|redis|elasticsearch|"
    r"docker|kubernetes|k8s|terraform|ansible|"
    r"aws|gcp|azure|lambda|s3|ec2|rds|cloudfront|"
    r"rest|graphql|grpc|websocket|"
    r"api|database|microservice|message.queue|sql|nosql|orm|"
    r"oauth|jwt|ssl|tls|ci/cd|pipeline|git|"
    r"react\s*native|flutter|swift|kotlin|android|ios)\b",
    re.IGNORECASE,
)

_CONSTRAINT_RE = re.compile(
    r"\b(performance|latency|throughput|concurrent|scalab|"
    r"high.availability|fault.tolerant|disaster.recovery|"
    r"security|compliance|gdpr|hipaa|pci.dss|encrypt|"
    r"auth[ne]?tication|authorization|rate.limit|timeout|"
    r"response.time|99\.\d+|sla|slo|rto|rpo|zero.downtime|"
    r"millions?|billions?|petabytes?|"
    r"p99|p95|p50|qps|rps|tps)\b",
    re.IGNORECASE,
)

_PERSONA_RE = re.compile(
    r"\b(user|persona|customer|stakeholder|admin|developer|"
    r"end.user|client|patient|student|teacher|"
    r"manager|operator|viewer|contributor|role|use.case|"
    r"audience|demographic|segment)\b",
    re.IGNORECASE,
)

_VAGUE_RE = re.compile(
    r"\b(I\s+don'?t\s+know|maybe|whatever|not\s+sure|"
    r"I\s+guess|no\s+idea|anything|doesn'?t\s+matter|"
    r"up\s+to\s+you|I\s+don'?t\s+care)\b",
    re.IGNORECASE,
)


# ── Interview state ────────────────────────────────────────────────────

@dataclass
class _InterviewState:
    question_index: int = 0
    questions: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)
    answers: list[tuple[str, str]] = field(default_factory=list)
    confidence: float = 0.10
    done: bool = False
    project_name: str = "Untitled"
    vague_count: int = 0


# ── Default question bank ──────────────────────────────────────────────

_BASE_QUESTIONS: list[str] = [
    "What problem are you trying to solve?",
    "Who are the users?",
    "What are the must-have features?",
    "What technologies do you prefer or want to avoid?",
    "What are the performance, security, or scale constraints?",
]

_VAGUE_FOLLOW_UPS: dict[int, str] = {
    0: "Can you describe the problem in more detail? What's the main pain point?",
    1: "Can you tell me more about who will use this? Any specific roles?",
    2: "What are the top 2–3 features that absolutely must be included?",
    3: "Are there any languages, frameworks, or tools you already use?",
    4: "Any specific targets for response time, concurrent users, or compliance?",
}


class InterviewMode(BaseMode):
    """One-question-at-a-time interview for structured requirement gathering.

    Attributes
    ----------
    is_done : bool
        ``True`` once confidence reaches 95 % or 15 questions are asked.
    current_question : str | None
        The question to present next, or ``None`` when finished.
    confidence : float
        Current confidence score (0.0 – 1.0).
    """

    MAX_QUESTIONS = 15
    TARGET_CONFIDENCE = 0.95
    MAX_VAGUE_RETRIES = 2

    def __init__(self, project_name: str = "") -> None:
        self._state = _InterviewState(
            project_name=project_name or "Untitled",
            questions=list(_BASE_QUESTIONS),
        )

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def is_done(self) -> bool:
        return self._state.done

    @property
    def current_question(self) -> str | None:
        if self._state.question_index >= len(self._state.questions):
            return None
        return self._state.questions[self._state.question_index]

    @property
    def confidence(self) -> float:
        return self._state.confidence

    # ── BaseMode interface ─────────────────────────────────────────────

    def execute(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return the interview state and spec (if complete).

        Because the interview is interactive (one question at a time),
        use ``submit_answer()`` in a loop instead.
        """
        return {
            "mode": "interview",
            "state": self._state,
            "spec": self.generate_spec() if self._state.done else None,
        }

    # ── Public API ─────────────────────────────────────────────────────

    def submit_answer(self, answer: str) -> str | None:
        """Record the user's answer and return the next question.

        Args:
            answer: The user's response to the current question.

        Returns:
            Next question, or ``None`` if the interview is complete.
        """
        question = self._state.questions[self._state.question_index]
        self._state.asked.append(question)
        self._state.answers.append((question, answer))

        # Vague answers get a more specific re-ask (same question index).
        if _VAGUE_RE.search(answer):
            self._state.vague_count += 1
            retry_q = self._reask_vague()
            if retry_q is not None:
                return retry_q

        self._score_answer(answer)
        total = len(self._state.asked)

        # Stopping conditions.
        if total >= self.MAX_QUESTIONS or self._state.confidence >= self.TARGET_CONFIDENCE:
            self._state.done = True
            pct = round(self._state.confidence * 100)
            logger.info("Interview complete after %d questions (confidence=%d%%)", total, pct)
            return None

        # Advance question index.
        self._state.question_index += 1
        self._state.vague_count = 0

        # Generate follow-up questions once base questions are exhausted.
        if self._state.question_index >= len(self._state.questions):
            self._generate_follow_up()

        if self._state.question_index >= len(self._state.questions):
            self._state.done = True
            return None

        logger.info("Q%d — confidence=%.0f%%", total + 1, self._state.confidence * 100)
        return self._state.questions[self._state.question_index]

    def generate_spec(self) -> str:
        """Produce a structured specification document.

        Returns:
            Markdown spec with sections for problem, users, features,
            constraints, tech stack, out-of-scope, and confidence.
        """
        answers = self._state.answers
        pct = round(self._state.confidence * 100)

        def _get(idx: int) -> str:
            return answers[idx][1].strip() if idx < len(answers) else ""

        follow = ""
        if len(answers) > len(_BASE_QUESTIONS):
            extra = "\n".join(
                f"- **{q}** {a}" for q, a in answers[len(_BASE_QUESTIONS):]
            )
            follow = f"\n\n## Additional Details\n{extra}"

        return (
            f"# Spec: {self._state.project_name}\n\n"
            f"## Problem Statement\n{_get(0) or 'Not specified'}\n\n"
            f"## Users\n{_get(1) or 'Not specified'}\n\n"
            f"## Must-Have Features\n{_get(2) or 'Not specified'}\n\n"
            f"## Technical Constraints\n{_get(4) or 'None specified'}\n\n"
            f"## Preferred Technologies\n{_get(3) or 'None specified'}\n\n"
            f"## Out of Scope\n(Review and update based on the interview)"
            f"{follow}\n\n"
            f"## Confidence: {pct}%\n"
        )

    def reset(self, project_name: str = "") -> None:
        """Reset the interview to its initial state."""
        self._state = _InterviewState(
            project_name=project_name or "Untitled",
            questions=list(_BASE_QUESTIONS),
        )

    # ── Confidence scoring ─────────────────────────────────────────────

    def _score_answer(self, answer: str) -> None:
        """Update confidence based on technical, constraint, and persona signals."""
        tech = _TECH_RE.findall(answer)
        constraints = _CONSTRAINT_RE.findall(answer)
        personas = _PERSONA_RE.findall(answer)

        gain = 0.0
        if tech:
            gain += 0.15
        if constraints:
            gain += 0.10
        if personas:
            gain += 0.05

        self._state.confidence = min(self._state.confidence + gain, 0.95)

        logger.debug(
            "Score: tech=%d constraints=%d personas=%d gain=+%.0f%% → %.0f%%",
            len(tech), len(constraints), len(personas),
            gain * 100, self._state.confidence * 100,
        )

    # ── Vague answer handling ──────────────────────────────────────────

    def _reask_vague(self) -> str | None:
        """Return a more specific rephrase, or ``None`` to give up."""
        idx = self._state.question_index
        if self._state.vague_count >= self.MAX_VAGUE_RETRIES:
            logger.info("Too many vague answers — moving on")
            return None
        return _VAGUE_FOLLOW_UPS.get(idx)

    # ── Follow-up generation ───────────────────────────────────────────

    def _generate_follow_up(self) -> None:
        """Create drill-down questions based on what's still missing."""
        all_text = " ".join(a for _, a in self._state.answers).lower()
        follow_ups: list[str] = []

        if "user" not in all_text and "persona" not in all_text:
            follow_ups.append("Can you describe the target users and their workflow?")
        if "performance" not in all_text and "scalab" not in all_text:
            follow_ups.append("What are your key performance or scalability targets?")
        if "security" not in all_text and "auth" not in all_text:
            follow_ups.append("Are there any security or compliance requirements?")
        if "api" not in all_text and "integrat" not in all_text:
            follow_ups.append("Does this need to integrate with any existing systems?")
        if "deploy" not in all_text and "host" not in all_text:
            follow_ups.append("Any preferences for hosting or deployment?")
        if not follow_ups:
            follow_ups.append("Is there anything else about the requirements?")

        self._state.questions.extend(follow_ups)


__all__ = ["BaseMode", "InterviewMode"]
