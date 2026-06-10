from __future__ import annotations

import logging
import threading
from typing import Any

from wigent.config import settings
from wigent.models.base_model import LLMResponse

logger = logging.getLogger(__name__)

RESPONSE_RESERVE_RATIO = 0.20
CONVERSATION_LIMIT_RATIO = 0.60
SYSTEM_CONTEXT_LIMIT_RATIO = 0.20
AUTO_SUMMARIZE_RATIO = 0.70
HARD_STOP_RATIO = 0.95
KEEP_LAST_N = 5

SUMMARY_PROMPT = (
    "Compress the above conversation into a concise summary retaining "
    "all decisions, file changes, errors, and progress. Use 2-3 paragraphs."
)


class TokenBudgetExceeded(Exception):
    """Raised when total tokens exceed the hard stop (95 %) threshold."""


class ContextManager:
    """Manages message history with strict token budget enforcement.

    Budget allocation (configurable via module-level constants):
      - 20 % response reserve
      - 60 % conversation history
      - 20 % system prompt + project context

    Thread-safe for concurrent ``add_message`` / ``get_messages`` access.
    """

    def __init__(self, max_tokens: int | None = None) -> None:
        self._max_tokens: int = max_tokens or settings.MAX_CONTEXT_TOKENS
        self._lock = threading.Lock()
        self._messages: list[dict[str, Any]] = []
        self._system_prompt: str = ""
        self._project_context: str = ""
        self._model = None

    # ── Public API ───────────────────────────────────────────────────────

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Append a message and enforce token budget.

        Args:
            role: ``system``, ``user``, ``assistant``, or ``tool``.
            content: Message text content.
            **kwargs: Extra fields (``tool_calls``, ``tool_call_id``, etc.).
        """
        msg: dict[str, Any] = {"role": role, "content": content}
        msg.update(kwargs)

        with self._lock:
            self._messages.append(msg)
            self._enforce_budget()

    def get_messages(self) -> list[dict[str, Any]]:
        """Return the current (trimmed) message list.

        Includes system prompt and project context as the first messages.
        """
        with self._lock:
            preamble = []
            if self._system_prompt:
                preamble.append({"role": "system", "content": self._system_prompt})
            if self._project_context:
                preamble.append({"role": "system", "content": self._project_context})
            return preamble + list(self._messages)

    def _get_model(self):
        """Lazy-init the model reference; may return None if unavailable."""
        if self._model is None:
            try:
                from wigent.models.model_factory import factory as mf
                self._model = mf.get_active_model()
            except Exception as exc:
                logger.debug("Model unavailable for token counting: %s", exc)
        return self._model

    def count_tokens(self, messages: list[dict[str, Any]] | None = None) -> int:
        """Estimate token count for a list of messages.

        Delegates to the active model's ``count_tokens()`` for accuracy.
        Falls back to a 4-char-per-token heuristic when the model is
        unavailable (e.g. no API key configured).
        """
        msgs = messages if messages is not None else self._messages
        model = self._get_model()
        if model is not None:
            try:
                return model.count_tokens(msgs)
            except Exception:
                pass
        total_chars = sum(len(str(m.get("content", ""))) for m in msgs)
        return total_chars // 4

    def trim_to_budget(self, budget: int | None = None) -> int:
        """Trim messages to fit within the conversation budget.

        Args:
            budget: Max tokens for conversation (default: 60 % of max).

        Returns:
            Number of messages removed.
        """
        limit = budget if budget is not None else int(self._max_tokens * CONVERSATION_LIMIT_RATIO)
        removed = 0

        with self._lock:
            while self._messages and self.count_tokens(self._messages) > limit:
                # Keep the last K messages; drop from the front.
                if len(self._messages) <= KEEP_LAST_N:
                    break
                self._messages.pop(0)
                removed += 1

            # Hard check after trimming.
            if self.count_tokens(self._messages) > int(self._max_tokens * HARD_STOP_RATIO):
                raise TokenBudgetExceeded(
                    f"Token budget exhausted after trim "
                    f"({self.count_tokens(self._messages)} > "
                    f"{int(self._max_tokens * HARD_STOP_RATIO)})"
                )

        if removed:
            logger.info("trim_to_budget: removed %d messages", removed)
        return removed

    def summarize_old_messages(self, force: bool = False) -> str | None:
        """Compress older conversation history into an LLM-generated summary.

        Keeps the last 5 messages intact; summarizes everything before
        that.  Returns the summary text, or ``None`` if there's nothing
        to summarize.
        """
        with self._lock:
            if len(self._messages) <= KEEP_LAST_N + 1:
                return None

            recent = self._messages[-KEEP_LAST_N:]
            to_summarize = self._messages[:-KEEP_LAST_N]

            summary_content = self._serialize_for_summary(to_summarize)

        model = self._get_model()
        if model is None:
            logger.warning("summarize_old_messages: no model available, skipping")
            return None

        summary_messages = [
            {"role": "user", "content": f"{SUMMARY_PROMPT}\n\n{summary_content}"},
        ]

        try:
            response: LLMResponse = model.chat(
                messages=summary_messages,
                tools=[],
                temperature=0.3,
            )
            summary = (response.content or "").strip()
            if not summary:
                logger.warning("summarize_old_messages: LLM returned empty summary")
                return None
        except Exception as exc:
            logger.warning("summarize_old_messages failed: %s", exc)
            return None

        with self._lock:
            self._messages = [
                {"role": "system", "content": f"[SUMMARY]\n{summary}"},
            ] + recent

        logger.info(
            "summarize_old_messages: compressed %d messages → 1 summary",
            len(to_summarize),
        )
        return summary

    def inject_system_prompt(self, prompt: str) -> None:
        """Set the system prompt for subsequent ``get_messages()`` calls."""
        with self._lock:
            self._system_prompt = prompt

    def inject_project_context(self, context: str) -> None:
        """Set the project context string.

        Reads from the in-memory value.  Callers should load from
        ``.agent/rules/`` or similar before calling this.
        """
        with self._lock:
            self._project_context = context

    def get_stats(self) -> dict[str, Any]:
        """Return usage statistics for the current state.

        Returns:
            Dict with keys: ``total_messages``, ``estimated_tokens``,
            ``budget_used_pct``, ``system_tokens``, ``context_tokens``,
            ``conversation_tokens``, ``preamble_tokens``.
        """
        with self._lock:
            preamble = []
            if self._system_prompt:
                preamble.append({"role": "system", "content": self._system_prompt})
            if self._project_context:
                preamble.append({"role": "system", "content": self._project_context})

            total_tokens = self.count_tokens(preamble + self._messages)
            preamble_tokens = self.count_tokens(preamble) if preamble else 0
            conversation_tokens = self.count_tokens(self._messages)

        return {
            "total_messages": len(self._messages),
            "estimated_tokens": total_tokens,
            "budget_used_pct": round(total_tokens / self._max_tokens * 100, 1) if self._max_tokens else 0,
            "preamble_tokens": preamble_tokens,
            "conversation_tokens": conversation_tokens,
            "system_prompt_size": len(self._system_prompt),
            "project_context_size": len(self._project_context),
        }

    def clear(self) -> None:
        """Reset all state — messages, system prompt, and project context."""
        with self._lock:
            self._messages.clear()
            self._system_prompt = ""
            self._project_context = ""
        logger.info("ContextManager cleared")

    # ── Budget enforcement ──────────────────────────────────────────────

    def _enforce_budget(self) -> None:
        """Check budgets after adding a message; trim or summarize if needed."""
        total_tokens = self.count_tokens(self._messages)
        hard_limit = int(self._max_tokens * HARD_STOP_RATIO)
        summarize_at = int(self._max_tokens * AUTO_SUMMARIZE_RATIO)

        if total_tokens >= hard_limit:
            raise TokenBudgetExceeded(
                f"Hard stop: {total_tokens} >= {hard_limit} tokens "
                f"({HARD_STOP_RATIO * 100:.0f}% of {self._max_tokens})"
            )

        if total_tokens >= summarize_at:
            logger.info(
                "Token usage at %.1f%% — auto-summarizing",
                total_tokens / self._max_tokens * 100,
            )
            self.summarize_old_messages(force=True)
            self.trim_to_budget()

    # ── Serialization helpers ───────────────────────────────────────────

    @staticmethod
    def _serialize_for_summary(messages: list[dict[str, Any]]) -> str:
        """Convert a message list to a compact string for the summary LLM."""
        lines: list[str] = []
        for m in messages:
            role = m.get("role", "?")
            content = str(m.get("content", ""))[:2000]
            lines.append(f"[{role.upper()}]\n{content}")
        return "\n\n".join(lines)


__all__ = ["ContextManager", "TokenBudgetExceeded"]
