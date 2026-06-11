# ════════════════════════════════════════
# wigent — Skill Router
# Role: LLM-powered skill classification and routing
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""LLM-powered skill classification and routing for phase-based development.

Replaces the keyword-only ``_MODE_SIGNALS`` routing with a trainable skill
system backed by few-shot LLM classification, keyword fallback, and
confidence-based dispatch.

Usage
-----
    from wigent.models.openai_model import OpenAIModel
    from wigent.core.skill_router import Skill, SkillRouter

    router = SkillRouter(llm_client=OpenAIModel())

    router.register_skill(Skill(
        name="interview-me",
        phase="meta",
        description="Simulates a technical interview for practice",
        triggers=["interview", "mock interview", "practice interview", "quiz"],
        prompt_template="skills/interview.md",
    ))

    skill, confidence = router.classify_intent(
        "Run a mock frontend interview",
        ["I want to practice", "Focus on React"],
    )
    # → (Skill(name="interview-me", ...), 0.92)

    best = router.route(
        "Run a mock frontend interview",
        ["I want to practice", "Focus on React"],
    )
    # → Skill(name="interview-me", ...)  if confidence >= threshold
    # → Skill(name="clarification", ...) if confidence < 0.5
    # → best guess (caller should confirm) if 0.5 <= confidence < threshold
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from wigent.models.base_model import BaseModel, LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A named, phase-scoped capability that the router can dispatch to.

    Attributes
    ----------
    name : str
        Unique identifier (e.g. ``"interview-me"``, ``"spec-driven-development"``).
    phase : str
        Development phase — one of ``"meta"``, ``"define"``, ``"plan"``,
        ``"build"``, ``"verify"``, ``"review"``, ``"ship"``.
    description : str
        Human-readable summary of what this skill does.
    triggers : list[str]
        Keywords and phrases that suggest this skill is relevant.
    confidence_threshold : float
        Minimum confidence required to auto-route (default ``0.7``).
    prompt_template : str
        Path to the skill's system prompt template file.
    """

    name: str
    phase: str
    description: str
    triggers: list[str] = field(default_factory=list)
    confidence_threshold: float = 0.7
    prompt_template: str = ""


_CLARIFICATION_SKILL = Skill(
    name="clarification",
    phase="meta",
    description="Ask the user clarifying questions to determine intent",
    triggers=["unsure", "clarify", "help", "what can you do", "options"],
    confidence_threshold=0.5,
    prompt_template="",
)


class SkillRouter:
    """Routes user intents to the most appropriate skill.

    Classification uses a two-stage pipeline:

    1. **LLM few-shot classification** — a prompt listing all registered
       skills, the last 3 conversation turns, and 3 worked examples.
    2. **Keyword fallback** — if the LLM call fails or returns invalid JSON,
       scores each skill by counting trigger-phrase hits.

    The ``route()`` method then applies the skill's confidence threshold to
    decide whether to auto-dispatch, ask for confirmation, or request
    clarification.
    """

    def __init__(self, llm_client: BaseModel) -> None:
        """Initialise the router with an LLM provider.

        Args:
            llm_client: Any ``BaseModel`` subclass (OpenAI, Anthropic, etc.).
        """
        self._client = llm_client
        self._skills: dict[str, Skill] = {}

    # ── Public API ─────────────────────────────────────────────────────

    def register_skill(self, skill: Skill) -> None:
        """Add a skill to the registry.

        Args:
            skill: The ``Skill`` instance to register.
        """
        self._skills[skill.name] = skill
        logger.info("Registered skill: %s (phase=%s)", skill.name, skill.phase)

    def classify_intent(
        self,
        user_input: str,
        conversation_history: list[str],
    ) -> tuple[Skill | None, float]:
        """Classify user intent into the best-matching skill.

        Uses LLM few-shot prompting with the full skill registry, the last
        3 conversation turns, and 3 worked examples.  Falls back to plain
        keyword matching when the LLM is unavailable or returns garbage.

        Args:
            user_input:            The user's latest message.
            conversation_history:  Prior messages (only the last 3 are used).

        Returns:
            A ``(Skill | None, confidence)`` pair.  ``None`` is returned
            when even the keyword fallback cannot find a match.
        """
        skill, confidence = self._llm_classify(user_input, conversation_history[-3:])

        if skill is not None:
            return skill, confidence

        # LLM failed — fall back to keyword scoring.
        return self._keyword_fallback(user_input)

    def route(
        self,
        user_input: str,
        conversation_history: list[str],
    ) -> Skill:
        """Route the user's input to the appropriate skill.

        Decision logic
        --------------
        * **confidence >= threshold** → return the classified skill.
        * **confidence < 0.5**        → return a built-in clarification skill.
        * **0.5 <= confidence < threshold** → return the skill anyway; the
          caller should prompt the user to confirm before dispatching.

        Args:
            user_input:           The user's latest message.
            conversation_history: Prior messages for context.

        Returns:
            The ``Skill`` that best matches the user's intent.
        """
        skill, confidence = self.classify_intent(user_input, conversation_history)

        if skill is None or confidence < 0.5:
            return _CLARIFICATION_SKILL

        if confidence >= skill.confidence_threshold:
            return skill

        # 0.5 <= confidence < threshold — caller should confirm.
        logger.info(
            "Low confidence (%.2f) for skill '%s' — returning for confirmation",
            confidence, skill.name,
        )
        return skill

    def get_skill_by_name(self, name: str) -> Skill | None:
        """Look up a registered skill by name.

        Args:
            name: The skill's unique identifier.

        Returns:
            The ``Skill`` instance, or ``None`` if not found.
        """
        return self._skills.get(name)

    def list_skills(self, phase: str | None = None) -> list[Skill]:
        """Return all registered skills, optionally filtered by phase.

        Args:
            phase: If provided, only skills in this phase are returned.

        Returns:
            A list of matching ``Skill`` instances.
        """
        if phase is None:
            return list(self._skills.values())
        return [s for s in self._skills.values() if s.phase == phase]

    # ── Internals ──────────────────────────────────────────────────────

    def _build_classification_prompt(
        self,
        user_input: str,
        history: list[str],
    ) -> str:
        """Construct the few-shot classification prompt."""
        skills_block = "\n\n".join(
            f"  - {s.name} (phase: {s.phase})\n"
            f"    description: {s.description}\n"
            f"    triggers: {s.triggers}"
            for s in self._skills.values()
        )

        history_block = "\n".join(
            f"  [{i}] {msg}"
            for i, msg in enumerate(history[-3:])
        ) if history else "  (none)"

        return (
            "You are a skill router. Given a user request and conversation "
            "history, select the single best skill from the list below.\n\n"
            f"Registered skills:\n{skills_block}\n\n"
            f"Conversation history (last {min(len(history), 3)} messages):\n"
            f"{history_block}\n\n"
            "---\n\n"
            "Examples:\n\n"
            '1. User: "Run a mock frontend interview"\n'
            '   History: ["I want to practice React"]\n'
            '   Output: {"skill": "interview-me", "confidence": 0.92, '
            '"reasoning": "Explicit mention of interview with frontend focus"}\n\n'
            '2. User: "Add user authentication to the API"\n'
            '   History: ["We need login", "Use JWT tokens"]\n'
            '   Output: {"skill": "spec-driven-development", "confidence": 0.85, '
            '"reasoning": "Clear feature request with technical details"}\n\n'
            '3. User: "What time is it?"\n'
            '   History: []\n'
            '   Output: {"skill": "clarification", "confidence": 0.15, '
            '"reasoning": "Unrelated to any registered skill"}\n\n'
            "---\n\n"
            "Respond with ONLY a JSON object in this exact format:\n"
            '{"skill": "<skill-name>", "confidence": <0.0-1.0>, '
            '"reasoning": "<brief explanation>"}\n\n'
            f"User: {user_input}\n\n"
            "Output:"
        )

    def _llm_classify(
        self,
        user_input: str,
        history: list[str],
    ) -> tuple[Skill | None, float]:
        """Ask the LLM to classify the user's intent."""
        if not self._skills:
            logger.warning("No skills registered — cannot classify")
            return None, 0.0

        prompt = self._build_classification_prompt(user_input, history)

        try:
            response: LLMResponse = self._client.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning("LLM classification call failed: %s", exc)
            return None, 0.0

        content = (response.content or "").strip()
        return self._parse_llm_response(content)

    def _parse_llm_response(
        self,
        content: str,
    ) -> tuple[Skill | None, float]:
        """Parse the LLM's JSON response into a (Skill, confidence) pair."""
        try:
            # Strip markdown fences if present.
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("\n", 1)[0] if content.endswith("```") else content

            data: dict[str, Any] = json.loads(content)
            skill_name = str(data.get("skill", ""))
            confidence = float(data.get("confidence", 0.0))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse LLM response: %s — content=%s", exc, content[:200])
            return None, 0.0

        skill = self._skills.get(skill_name)
        if skill is None:
            logger.warning("LLM returned unknown skill: %s", skill_name)
            return None, 0.0

        return skill, min(max(confidence, 0.0), 1.0)

    def _keyword_fallback(
        self,
        user_input: str,
    ) -> tuple[Skill | None, float]:
        """Score skills by counting trigger-phrase matches."""
        if not self._skills:
            return None, 0.0

        input_lower = user_input.lower()
        best_skill: Skill | None = None
        best_score = 0

        for skill in self._skills.values():
            score = sum(1 for t in skill.triggers if t.lower() in input_lower)
            if score > best_score:
                best_score = score
                best_skill = skill

        if best_skill is None or best_score == 0:
            return None, 0.0

        # Convert raw match count to a pseudo-confidence in [0, 1].
        max_possible = max((len(s.triggers) for s in self._skills.values()), default=1)
        confidence = min(best_score / max(max_possible, 1), 1.0)
        logger.info(
            "Keyword fallback: skill=%s  score=%d  confidence=%.2f",
            best_skill.name, best_score, confidence,
        )
        return best_skill, confidence


__all__ = ["Skill", "SkillRouter"]
