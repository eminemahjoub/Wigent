"""
Role: Smart context engineering -- feed the right information at the right time.
Author: Wigent AI
Version: 1.0.0

Optimizes LLM context windows by selecting only relevant information,
compressing history, and prioritizing high-signal content.

Usage:
    from wigent.core.context_packer import ContextPacker

    packer = ContextPacker(vector_store, max_tokens=8000)

    context = packer.pack(
        current_task="Implement user authentication",
        conversation_history=history,
        codebase_files=files,
        rules_files=[".wigent/rules/python.md"],
        mcp_tools=available_tools,
    )
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wigent.memory.vector_store import VectorStore


@dataclass
class ContextStats:
    """Statistics about context packing decisions."""

    original_tokens: int = 0
    packed_tokens: int = 0
    compression_ratio: float = 0.0
    items_included: int = 0
    items_excluded: int = 0
    relevance_scores: dict[str, float] = field(default_factory=dict)


class ContextPacker:
    """
    Intelligently packs context for LLM consumption.

    Principles:
    1. Relevance > Recency -- old but relevant > new but irrelevant
    2. Compression > Truncation -- summarize before cutting
    3. Rules are sacred -- always include active rules
    4. MCP tools are expensive -- only include likely-to-be-used
    5. Codebase context decays -- recent files > old files
    """

    # Token budgets per context type (percentage of total)
    DEFAULT_BUDGETS = {
        "system_prompt": 0.10,
        "rules": 0.15,
        "conversation": 0.25,
        "codebase": 0.30,
        "tools": 0.15,
        "buffer": 0.05,
    }

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        max_tokens: int = 8000,
        budgets: dict[str, float] | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.max_tokens = max_tokens
        self.budgets = budgets or self.DEFAULT_BUDGETS.copy()

        total = sum(self.budgets.values())
        assert 0.99 <= total <= 1.01, f"Budgets must sum to 1.0, got {total}"

        self._cache: dict[str, str] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def pack(
        self,
        current_task: str,
        conversation_history: list[dict[str, str]],
        codebase_files: list[str] | None = None,
        rules_files: list[str] | None = None,
        mcp_tools: list[dict] | None = None,
        skill_prompt: str | None = None,
        session_memory: dict | None = None,
    ) -> tuple[str, ContextStats]:
        """
        Pack all relevant context into a single prompt string.

        Args:
            current_task: Description of what the agent is doing now
            conversation_history: List of {role, content} turns
            codebase_files: Paths to relevant source files
            rules_files: Paths to active rule files
            mcp_tools: Available MCP tool definitions
            skill_prompt: Active skill system prompt
            session_memory: Persistent session state

        Returns:
            Tuple of (packed_context_string, stats)
        """
        stats = ContextStats()

        budgets = {
            key: int(self.max_tokens * pct)
            for key, pct in self.budgets.items()
        }

        sections = []

        # 1. System prompt (skill + role) -- highest priority
        system_section = self._pack_system(
            skill_prompt=skill_prompt,
            max_tokens=budgets["system_prompt"],
        )
        sections.append(("system", system_section))

        # 2. Rules -- always include, compress if needed
        rules_section = self._pack_rules(
            rules_files=rules_files or [],
            max_tokens=budgets["rules"],
        )
        sections.append(("rules", rules_section))

        # 3. Conversation -- summarize old, keep recent verbatim
        conv_section = self._pack_conversation(
            history=conversation_history,
            current_task=current_task,
            max_tokens=budgets["conversation"],
        )
        sections.append(("conversation", conv_section))

        # 4. Codebase -- semantic search for relevance
        code_section = self._pack_codebase(
            files=codebase_files or [],
            query=current_task,
            max_tokens=budgets["codebase"],
        )
        sections.append(("codebase", code_section))

        # 5. Tools -- only include likely-to-be-used
        tools_section = self._pack_tools(
            tools=mcp_tools or [],
            query=current_task,
            max_tokens=budgets["tools"],
        )
        sections.append(("tools", tools_section))

        # 6. Session memory -- compact state
        memory_section = self._pack_memory(
            memory=session_memory or {},
            max_tokens=budgets["buffer"],
        )
        if memory_section:
            sections.append(("memory", memory_section))

        # Assemble final context
        context_parts = []
        for name, content in sections:
            if content.strip():
                context_parts.append(f"## {name.upper()}\n\n{content}\n")

        packed = "\n".join(context_parts)

        stats.packed_tokens = self._estimate_tokens(packed)
        stats.items_included = sum(1 for _, c in sections if c.strip())
        stats.items_excluded = len(sections) - stats.items_included
        stats.compression_ratio = stats.packed_tokens / self.max_tokens

        return packed, stats

    def pack_for_skill(
        self,
        skill_name: str,
        user_input: str,
        conversation_history: list[dict[str, str]],
        context: dict,
    ) -> str:
        """
        Pack context optimized for a specific skill.

        Different skills need different context:
        - interview: full conversation, no codebase
        - spec: interview output, no tools
        - coder: codebase + relevant files, minimal history
        - debugger: error logs, recent changes, no rules
        """
        skill_budgets = {
            "interview-me": {
                "system": 0.15, "rules": 0.05, "conversation": 0.70,
                "codebase": 0.0, "tools": 0.0, "buffer": 0.10,
            },
            "spec-driven-development": {
                "system": 0.15, "rules": 0.10, "conversation": 0.50,
                "codebase": 0.10, "tools": 0.0, "buffer": 0.15,
            },
            "incremental-implementation": {
                "system": 0.10, "rules": 0.10, "conversation": 0.15,
                "codebase": 0.45, "tools": 0.15, "buffer": 0.05,
            },
            "debugging-and-error-recovery": {
                "system": 0.10, "rules": 0.05, "conversation": 0.20,
                "codebase": 0.40, "tools": 0.20, "buffer": 0.05,
            },
            "code-review-and-quality": {
                "system": 0.10, "rules": 0.15, "conversation": 0.10,
                "codebase": 0.50, "tools": 0.10, "buffer": 0.05,
            },
        }

        budgets = skill_budgets.get(skill_name, self.DEFAULT_BUDGETS)

        old_budgets = self.budgets
        self.budgets = budgets

        try:
            packed, _ = self.pack(
                current_task=user_input,
                conversation_history=conversation_history,
                **context,
            )
            return packed
        finally:
            self.budgets = old_budgets

    def summarize_history(
        self,
        history: list[dict[str, str]],
        max_turns: int = 3,
    ) -> str:
        """
        Summarize older conversation turns, keep recent verbatim.

        Strategy:
        - Last N turns: verbatim (full detail)
        - Older turns: summarized to key decisions and facts
        - Very old: omitted entirely
        """
        if not history:
            return ""

        recent = history[-max_turns:]
        older = history[:-max_turns]

        parts = []

        if older:
            summary = self._summarize_turns(older)
            parts.append(f"[Earlier conversation summarized]: {summary}")

        for turn in recent:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if len(content) > 2000:
                content = content[:2000] + "... [truncated]"
            parts.append(f"{role}: {content}")

        return "\n\n".join(parts)

    def get_relevant_files(
        self,
        query: str,
        files: list[str],
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """
        Rank files by relevance to current task using vector search.

        Returns:
            List of (file_path, relevance_score) sorted by score
        """
        if not self.vector_store or not files:
            return self._keyword_rank(query, files, top_k)

        results = []
        for file_path in files:
            cache_key = f"relevance:{query}:{file_path}"
            if cache_key in self._cache:
                score = float(self._cache[cache_key])
                self._cache_hits += 1
            else:
                score = self.vector_store.similarity(query, file_path)
                self._cache[cache_key] = str(score)
                self._cache_misses += 1

            results.append((file_path, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def clear_cache(self) -> None:
        """Clear relevance cache."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    @property
    def cache_stats(self) -> dict[str, int]:
        """Return cache hit/miss statistics."""
        total = self._cache_hits + self._cache_misses
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "total": total,
            "hit_rate": self._cache_hits / total if total > 0 else 0,
        }

    # =================================================================
    # Internal Packing Methods
    # =================================================================

    def _pack_system(
        self,
        skill_prompt: str | None,
        max_tokens: int,
    ) -> str:
        """Pack system prompt and role definition."""
        if not skill_prompt:
            return "You are a helpful AI coding assistant."

        prompt = skill_prompt.strip()
        if self._estimate_tokens(prompt) > max_tokens:
            lines = prompt.split("\n")
            role_line = lines[0] if lines else ""
            prompt = role_line + "\n\n[Instructions truncated for length]"

        return prompt

    def _pack_rules(
        self,
        rules_files: list[str],
        max_tokens: int,
    ) -> str:
        """Pack active rule files, compressing if needed."""
        if not rules_files:
            return ""

        rules_content = []
        total_tokens = 0

        for rules_file in rules_files:
            try:
                content = Path(rules_file).read_text()
                tokens = self._estimate_tokens(content)

                if total_tokens + tokens <= max_tokens:
                    rules_content.append(f"### {Path(rules_file).name}\n{content}")
                    total_tokens += tokens
                else:
                    compressed = self._compress_rules(content, max_tokens - total_tokens)
                    if compressed:
                        rules_content.append(f"### {Path(rules_file).name}\n{compressed}")
                    break

            except FileNotFoundError:
                continue

        return "\n\n".join(rules_content)

    def _pack_conversation(
        self,
        history: list[dict[str, str]],
        current_task: str,
        max_tokens: int,
    ) -> str:
        """Pack conversation with smart summarization."""
        if not history:
            return f"Current task: {current_task}"

        packed = self.summarize_history(history, max_turns=3)
        packed = f"Current task: {current_task}\n\n{packed}"

        if self._estimate_tokens(packed) > max_tokens:
            packed = self._aggressive_truncate(packed, max_tokens)

        return packed

    def _pack_codebase(
        self,
        files: list[str],
        query: str,
        max_tokens: int,
    ) -> str:
        """Pack relevant codebase files with semantic ranking."""
        if not files:
            return ""

        relevant = self.get_relevant_files(query, files, top_k=10)

        parts = []
        total_tokens = 0

        for file_path, score in relevant:
            if score < 0.3:
                continue

            try:
                content = Path(file_path).read_text()
                tokens = self._estimate_tokens(content)

                if total_tokens + tokens <= max_tokens:
                    parts.append(f"### {file_path} (relevance: {score:.2f})\n```\n{content}\n```")
                    total_tokens += tokens
                else:
                    summary = self._summarize_file(content)
                    summary_tokens = self._estimate_tokens(summary)

                    if total_tokens + summary_tokens <= max_tokens:
                        parts.append(f"### {file_path} (summary, relevance: {score:.2f})\n{summary}")
                        total_tokens += summary_tokens
                    else:
                        break

            except (FileNotFoundError, UnicodeDecodeError):
                continue

        return "\n\n".join(parts)

    def _pack_tools(
        self,
        tools: list[dict],
        query: str,
        max_tokens: int,
    ) -> str:
        """Pack MCP tools, prioritizing likely-to-be-used."""
        if not tools:
            return ""

        scored = []
        for tool in tools:
            name = tool.get("name", "")
            description = tool.get("description", "")
            score = self._tool_relevance(query, name, description)
            scored.append((tool, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        parts = []
        total_tokens = 0

        for tool, score in scored:
            tool_str = json.dumps(tool, indent=2)
            tokens = self._estimate_tokens(tool_str)

            if total_tokens + tokens <= max_tokens:
                parts.append(f"### {tool.get('name', 'unknown')} (relevance: {score:.2f})\n{tool_str}")
                total_tokens += tokens
            else:
                mini = {
                    "name": tool.get("name"),
                    "description": tool.get("description"),
                }
                mini_str = json.dumps(mini)
                mini_tokens = self._estimate_tokens(mini_str)

                if total_tokens + mini_tokens <= max_tokens:
                    parts.append(f"### {tool.get('name', 'unknown')}\n{mini_str}")
                    total_tokens += mini_tokens
                else:
                    break

        return "\n\n".join(parts)

    def _pack_memory(
        self,
        memory: dict,
        max_tokens: int,
    ) -> str:
        """Pack session memory compactly."""
        if not memory:
            return ""

        compact = json.dumps(memory, indent=None, separators=(",", ":"))

        if self._estimate_tokens(compact) > max_tokens:
            essential = {
                k: v for k, v in memory.items()
                if k in {"mode", "skill", "project", "last_action"}
            }
            compact = json.dumps(essential, indent=None, separators=(",", ":"))

        return compact

    # =================================================================
    # Summarization Methods
    # =================================================================

    def _summarize_turns(self, turns: list[dict[str, str]]) -> str:
        """Summarize multiple conversation turns to key facts."""
        facts = []

        for turn in turns:
            content = turn.get("content", "")
            if any(word in content.lower() for word in ["agree", "decide", "chose", "will use", "going with"]):
                facts.append(f"Decision: {content[:200]}")
            elif any(word in content.lower() for word in ["must", "need to", "require", "constraint"]):
                facts.append(f"Constraint: {content[:200]}")

        if not facts:
            topics = [turn.get("content", "")[:100] + "..." for turn in turns[-3:]]
            return "Recent topics: " + "; ".join(topics)

        return "; ".join(facts[:5])

    def _summarize_file(self, content: str) -> str:
        """Summarize a code file to its structure."""
        lines = content.split("\n")

        imports = [l for l in lines if l.startswith(("import ", "from "))]

        definitions = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("class ", "def ", "async def ")):
                definitions.append(stripped[:100])

        summary = [
            "Structure:",
            *[f"  {d}" for d in definitions[:10]],
            "",
            f"Imports: {len(imports)} total",
            *[f"  {i}" for i in imports[:5]],
        ]

        return "\n".join(summary)

    def _compress_rules(self, content: str, max_tokens: int) -> str:
        """Compress rules file by keeping structure, removing examples."""
        lines = content.split("\n")

        compressed = []
        in_example = False

        for line in lines:
            if line.startswith("##") or line.startswith("**Rule"):
                compressed.append(line)
                in_example = False
            elif line.startswith("```") and "example" in line.lower():
                in_example = True
            elif line.startswith("```") and in_example:
                in_example = False
            elif not in_example and line.strip() and not line.startswith("#"):
                compressed.append(line)

        result = "\n".join(compressed)

        if self._estimate_tokens(result) > max_tokens:
            headers = [l for l in lines if l.startswith("#")]
            result = "\n".join(headers[:20])

        return result

    # =================================================================
    # Utility Methods
    # =================================================================

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count using rough heuristic.

        More accurate than len(text)/4 for code (which has many short tokens).
        """
        code_ratio = sum(1 for c in text if c in "{}[]();:.,=-><!") / max(len(text), 1)
        chars_per_token = 3.0 if code_ratio > 0.05 else 4.0

        return int(len(text) / chars_per_token)

    def _keyword_rank(self, query: str, files: list[str], top_k: int) -> list[tuple[str, float]]:
        """Fallback keyword-based relevance ranking."""
        query_words = set(query.lower().split())
        scored = []

        for file_path in files:
            try:
                content = Path(file_path).read_text().lower()
                file_words = set(content.split())

                intersection = query_words & file_words
                union = query_words | file_words
                score = len(intersection) / len(union) if union else 0

                if any(word in file_path.lower() for word in query_words):
                    score += 0.2

                scored.append((file_path, min(score, 1.0)))
            except (FileNotFoundError, UnicodeDecodeError):
                continue

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _tool_relevance(self, query: str, tool_name: str, tool_description: str) -> float:
        """Score tool relevance to current task."""
        query_lower = query.lower()
        name_lower = tool_name.lower()
        desc_lower = (tool_description or "").lower()

        score = 0.0

        if name_lower in query_lower:
            score += 0.5

        query_words = set(query_lower.split())
        name_words = set(name_lower.split())
        desc_words = set(desc_lower.split())

        name_overlap = len(query_words & name_words) / len(query_words) if query_words else 0
        desc_overlap = len(query_words & desc_words) / len(query_words) if query_words else 0

        score += name_overlap * 0.3
        score += desc_overlap * 0.2

        return min(score, 1.0)

    def _aggressive_truncate(self, text: str, max_tokens: int) -> str:
        """Last-resort truncation: keep first and last parts."""
        estimated = self._estimate_tokens(text)
        if estimated <= max_tokens:
            return text

        chars = len(text)
        target_chars = int(max_tokens * 3.5)

        start_len = int(target_chars * 0.3)
        end_len = int(target_chars * 0.2)

        start = text[:start_len]
        end = text[-end_len:]

        return f"{start}\n\n... [truncated {estimated - max_tokens} tokens] ...\n\n{end}"
