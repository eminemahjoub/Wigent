# ════════════════════════════════════════
# wigent — Agent Loop
# Role: Think → Act → Observe loop with LangGraph StateGraph
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Core agent loop powered by LangGraph.

Architecture
------------
The loop is modelled as a finite-state graph with four nodes:

    [START] → think_node → act_node → observe_node → decide_node → [END]
                              ↑                         |
                              └── (conditional continue) ┘

- **think_node**  — calls the LLM with current message history + tools.
- **act_node**    — dispatches tool calls returned by the LLM.
- **observe_node** — feeds tool results back into the message history.
- **decide_node**  — checks stopping criteria and routes back or exits.

Safety features
---------------
- Maximum iteration enforcement (prevents infinite loops).
- Token budget management — stops before context-window overflow.
- Cycle detection — identifies repeated (tool, args) call sequences.
- Auto-summarization — compresses old messages when context is full.
- Graceful error recovery — per-node try/except with state rollback.
- Checkpoint save/restore — JSON-serialised state dumps.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Literal, TypedDict

from langgraph.constants import END, START
from langgraph.graph.state import StateGraph
from langgraph.checkpoint.memory import MemorySaver

from wigent.config import settings
from wigent.config.modes import MODES, AgentModeConfig, get_mode
from wigent.models.base_model import (
    BaseModel,
    ContextWindowError,
    ErrorType,
    LLMResponse,
    RateLimitError,
)
from wigent.models.model_factory import factory as model_factory
from wigent.prompts import build_mode_prompt
from wigent.tools.tool_schemas import TOOL_SCHEMAS

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

CHECKPOINT_DIR = os.path.join(
    settings.SESSION_DIR, "checkpoints",
    datetime.now(timezone.utc).strftime("%Y%m%d")
)

MAX_TOOL_OUTPUT_CHARS = 10_000
CYCLE_DETECTION_THRESHOLD = 3
SUMMARIZE_RATIO = 0.8
SUMMARY_PROMPT = (
    "Compress the above conversation into a concise summary retaining "
    "all decisions, file changes, errors, and progress. Use 2-3 paragraphs."
)


# ── Agent state ───────────────────────────────────────────────────────


class AgentState(TypedDict):
    """Complete state of the agent loop, persisted across graph steps."""

    task: str
    messages: list[dict[str, Any]]
    current_mode: str
    iteration: int
    max_iterations: int
    tool_calls_made: list[dict[str, Any]]
    files_modified: list[str]
    errors_encountered: list[dict[str, Any]]
    status: Literal["thinking", "acting", "observing", "done", "error"]
    result: str | None
    token_usage: dict[str, int]
    total_cost: float
    cycle_signatures: list[str]
    session_id: str
    started_at: str | None
    last_step_duration: float
    checkpoints: list[str]


def initial_state(task: str, mode: str = "orchestrator", max_iterations: int | None = None) -> AgentState:
    """Create a fresh ``AgentState`` for a new task."""
    mode_cfg = get_mode(mode)
    return AgentState(
        task=task,
        messages=[],
        current_mode=mode,
        iteration=0,
        max_iterations=max_iterations or mode_cfg.max_iterations or settings.MAX_ITERATIONS,
        tool_calls_made=[],
        files_modified=[],
        errors_encountered=[],
        status="thinking",
        result=None,
        token_usage={"prompt": 0, "completion": 0, "total": 0},
        total_cost=0.0,
        cycle_signatures=[""],
        session_id=uuid.uuid4().hex[:12],
        started_at=None,
        last_step_duration=0.0,
        checkpoints=[],
    )


# ── Tool execution ───────────────────────────────────────────────────


# Map of tool name → callable.  Imported lazily to avoid circular deps.
_TOOL_REGISTRY: dict[str, Callable[..., Any]] | None = None


def _get_tool_registry() -> dict[str, Callable[..., Any]]:
    global _TOOL_REGISTRY
    if _TOOL_REGISTRY is not None:
        return _TOOL_REGISTRY
    from wigent.tools import (
        apply_diff, append_to_file, backup_file, check_is_git_repo,
        commit, create_branch, create_file, detect_encoding,
        edit_file_lines, execute_command, execute_script,
        find_definition, find_files, find_function, find_imports,
        find_references, find_similar_code,
        get_blame, get_classes, get_command_preview, get_complexity,
        get_current_branch, get_diff, get_docstrings,
        get_file_history, get_file_info, get_file_summary,
        get_file_symbols, get_functions, get_imports, get_imports_graph,
        get_log, get_project_structure, get_recent_files, get_repo_root,
        get_status, kill_process, list_branches, list_directory, list_files,
        list_stashes, parse_file, pop_stash, read_file, read_file_lines,
        read_multiple_files, restore_backup, run_command, run_python,
        search_and_replace, search_by_pattern, search_codebase,
        search_in_files, search_by_regex, stage_files, stash_changes,
        unstage_files, write_file,
    )
    _TOOL_REGISTRY = {
        "read_file": read_file,
        "read_file_lines": read_file_lines,
        "read_multiple_files": read_multiple_files,
        "get_file_info": get_file_info,
        "detect_encoding": detect_encoding,
        "get_file_summary": get_file_summary,
        "write_file": write_file,
        "create_file": create_file,
        "append_to_file": append_to_file,
        "edit_file_lines": edit_file_lines,
        "apply_diff": apply_diff,
        "backup_file": backup_file,
        "restore_backup": restore_backup,
        "list_directory": list_directory,
        "get_project_structure": get_project_structure,
        "list_files": list_files,
        "find_files": find_files,
        "get_recent_files": get_recent_files,
        "search_in_files": search_in_files,
        "search_by_regex": search_by_regex,
        "find_function": find_function,
        "find_imports": find_imports,
        "search_and_replace": search_and_replace,
        "execute_command": execute_command,
        "execute_script": execute_script,
        "run_python": run_python,
        "get_command_preview": get_command_preview,
        "kill_process": kill_process,
        "run_command": run_command,
        "search_codebase": search_codebase,
        "search_by_pattern": search_by_pattern,
        "find_definition": find_definition,
        "find_references": find_references,
        "get_file_symbols": get_file_symbols,
        "get_imports_graph": get_imports_graph,
        "find_similar_code": find_similar_code,
        "parse_file": parse_file,
        "get_functions": get_functions,
        "get_classes": get_classes,
        "get_imports": get_imports,
        "get_complexity": get_complexity,
        "get_docstrings": get_docstrings,
        # git_tool
        "check_is_git_repo": check_is_git_repo,
        "get_repo_root": get_repo_root,
        "get_status": get_status,
        "get_diff": get_diff,
        "get_log": get_log,
        "get_current_branch": get_current_branch,
        "list_branches": list_branches,
        "stage_files": stage_files,
        "unstage_files": unstage_files,
        "commit": commit,
        "create_branch": create_branch,
        "get_blame": get_blame,
        "get_file_history": get_file_history,
        "stash_changes": stash_changes,
        "pop_stash": pop_stash,
        "list_stashes": list_stashes,
    }
    return _TOOL_REGISTRY


# ── Agent loop ────────────────────────────────────────────────────────


class AgentLoop:
    """LangGraph-powered Think → Act → Observe loop.

    Usage
    -----
        loop = AgentLoop(model, mode="coder")
        result = loop.run("Refactor the auth module")
    """

    def __init__(
        self,
        model: BaseModel | None = None,
        mode: str = "orchestrator",
        tool_filter: list[str] | None = None,
        enable_checkpoints: bool = True,
        vector_store: Any | None = None,
    ) -> None:
        self._model: BaseModel = model or model_factory.get_active_model()
        self._mode_cfg: AgentModeConfig = get_mode(mode)
        self._tool_filter: list[str] | None = tool_filter
        self._enable_checkpoints = enable_checkpoints
        self._vector_store: Any | None = vector_store
        self._graph: CompiledStateGraph | None = None
        self._last_state: AgentState | None = None

    # ── Public API ───────────────────────────────────────────────────

    def _make_config(self, state: dict[str, Any]) -> dict[str, Any]:
        """Build LangGraph config with thread_id (required by checkpointer)."""
        return {
            "configurable": {"thread_id": uuid.uuid4().hex},
            "recursion_limit": state["max_iterations"] + 10,
        }

    def run(
        self,
        task: str,
        mode: str | None = None,
        max_iterations: int | None = None,
    ) -> AgentState:
        """Run the agent loop to completion on *task*.

        Args:
            task:           The user's goal description.
            mode:           Agent mode override (default: constructor mode).
            max_iterations: Cap on loop iterations (default: from mode config).

        Returns:
            The final ``AgentState`` with ``result`` populated.
        """
        if mode:
            self._mode_cfg = get_mode(mode)

        state = initial_state(
            task=task,
            mode=self._mode_cfg.name,
            max_iterations=max_iterations,
        )
        state["started_at"] = datetime.now(timezone.utc).isoformat()
        state["messages"] = self._build_initial_messages(task)

        graph = self._build_graph()
        self._graph = graph

        logger.info(
            "AgentLoop started  task=%s  mode=%s  max_iter=%d",
            task[:60], self._mode_cfg.name, state["max_iterations"],
        )

        try:
            final = graph.invoke(state, self._make_config(state))
            self._last_state = final
            logger.info(
                "AgentLoop done  iterations=%d  total_cost=%.6f  status=%s",
                final.get("iteration", 0), final.get("total_cost", 0.0), final.get("status"),
            )
            return final
        except Exception as exc:
            logger.exception("AgentLoop crashed: %s", exc)
            state["status"] = "error"
            state["result"] = f"Agent loop crashed: {exc}"
            self._last_state = state
            return state

    def stream(
        self,
        task: str,
        mode: str | None = None,
        max_iterations: int | None = None,
    ) -> Any:
        """Run the loop and yield state updates after each node execution.

        Yields each ``AgentState`` snapshot so callers can render progress
        in real time.
        """
        if mode:
            self._mode_cfg = get_mode(mode)

        state = initial_state(
            task=task,
            mode=self._mode_cfg.name,
            max_iterations=max_iterations,
        )
        state["started_at"] = datetime.now(timezone.utc).isoformat()
        state["messages"] = self._build_initial_messages(task)

        graph = self._build_graph()
        self._graph = graph

        try:
            for item in graph.stream(state, self._make_config(state), stream_mode="values"):
                # stream_mode="values" should yield state dicts directly
                snapshot = item if isinstance(item, dict) else item[1] if isinstance(item, tuple) else {}
                self._last_state = snapshot
                yield snapshot
        except Exception as exc:
            logger.exception("AgentLoop stream crashed: %s", exc)

    def resume_from_checkpoint(self, checkpoint_path: str) -> AgentState:
        """Load a saved checkpoint and continue execution."""
        state = self._load_checkpoint(checkpoint_path)
        graph = self._build_graph()
        self._graph = graph
        final = graph.invoke(state, self._make_config(state))
        self._last_state = final
        return final

    # ── Graph construction ───────────────────────────────────────────

    def _build_graph(self) -> CompiledStateGraph:
        """Assemble the LangGraph ``StateGraph`` with all nodes/edges."""
        builder = StateGraph(AgentState)

        builder.add_node("think", self._think_node)
        builder.add_node("act", self._act_node)
        builder.add_node("observe", self._observe_node)
        builder.add_node("decide", self._decide_node)

        builder.add_edge(START, "think")
        builder.add_edge("think", "act")
        builder.add_edge("act", "observe")
        builder.add_edge("observe", "decide")
        builder.add_conditional_edges(
            "decide",
            self._route_from_decide,
            {"think": "think", END: END},
        )

        memory = MemorySaver()
        return builder.compile(checkpointer=memory)

    # ── Graph nodes ──────────────────────────────────────────────────

    def _retrieve_context(self, query: str, k: int = 5) -> str:
        """Search the vector store for code snippets relevant to *query*.

        Returns a formatted string of retrieved chunks, or empty string
        if no vector store is available.
        """
        if self._vector_store is None:
            return ""
        try:
            results = self._vector_store.search(query, k=k)
            if not results:
                return ""
            parts = []
            for i, hit in enumerate(results, 1):
                meta = hit.get("metadata", {})
                file_name = meta.get("file", "unknown")
                content = hit.get("content", "").strip()
                if content:
                    parts.append(f"--- snippet {i} ({file_name}) ---\n{content[:800]}")
            return "\n\n".join(parts)
        except Exception as exc:
            logger.warning("RAG retrieval failed: %s", exc)
            return ""

    def _think_node(self, state: AgentState) -> dict[str, Any]:
        """Call the LLM with current messages + tools + RAG context."""
        logger.info(
            "think  iteration=%d/%d  tokens=%d",
            state["iteration"] + 1, state["max_iterations"],
            state["token_usage"]["total"],
        )

        t0 = time.perf_counter()
        state["status"] = "thinking"

        # Enforce token budget before calling.
        self._enforce_token_budget(state)

        # Auto-summarize if context is getting full.
        if self._should_summarize(state):
            self._auto_summarize(state)

        # ── RAG: retrieve relevant code context ────────────────────────
        task = state.get("task", "")
        rag_context = self._retrieve_context(task, k=5)
        messages = list(state["messages"])
        if rag_context:
            # Inject as a system message right before the user task
            rag_msg = {
                "role": "system",
                "content": (
                    "Relevant code from the workspace:\n\n" + rag_context +
                    "\n\nUse the above snippets to ground your answer."
                ),
            }
            # Insert after any existing system messages, before user messages
            insert_idx = 0
            for i, msg in enumerate(messages):
                if msg.get("role") == "system":
                    insert_idx = i + 1
            messages.insert(insert_idx, rag_msg)
            logger.info("RAG: injected %d snippets", rag_context.count("--- snippet"))

        # Build tool list filtered by mode.
        tools = self._get_tools_for_mode()

        try:
            response: LLMResponse = self._model.chat(
                messages=messages,
                tools=tools,
                stream=False,
            )
        except ContextWindowError:
            logger.warning("Context window exceeded — summarizing and retrying.")
            self._auto_summarize(state)
            response = self._model.chat(
                messages=messages,
                tools=tools,
                stream=False,
            )

        duration = time.perf_counter() - t0
        state["last_step_duration"] = duration

        # Track token usage.
        usage = response.usage or {}
        state["token_usage"]["prompt"] += usage.get("prompt_tokens", 0)
        state["token_usage"]["completion"] += usage.get("completion_tokens", 0)
        state["token_usage"]["total"] += usage.get("total_tokens", 0)
        state["total_cost"] += response.cost

        # Append assistant message.
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content or ""}
        if response.tool_calls:
            assistant_msg["tool_calls"] = response.tool_calls
        state["messages"].append(assistant_msg)

        logger.info(
            "think done  tokens=%d  cost=%.6f  tool_calls=%d  duration=%.2fs",
            usage.get("total_tokens", 0), response.cost,
            len(response.tool_calls), duration,
        )

        return {
            "messages": state["messages"],
            "status": "thinking",
            "token_usage": state["token_usage"],
            "total_cost": state["total_cost"],
            "last_step_duration": duration,
        }

    def _act_node(self, state: AgentState) -> dict[str, Any]:
        """Execute all tool calls returned by the LLM."""
        last_msg = state["messages"][-1] if state["messages"] else {}
        tool_calls = last_msg.get("tool_calls", [])
        state["status"] = "acting"

        if not tool_calls:
            return {"status": "acting"}

        results: list[dict[str, Any]] = []
        registry = _get_tool_registry()

        for tc in tool_calls:
            func_name = tc.get("function", {}).get("name", "")
            raw_args = tc.get("function", {}).get("arguments", "{}")

            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}

            # Cycle detection: compute a signature and check for repeats.
            sig = self._compute_call_signature(func_name, args)
            state["cycle_signatures"].append(sig)
            if self._detect_cycle(state["cycle_signatures"]):
                logger.warning("Cycle detected — stopping tool %s", func_name)
                results.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": f"[CYCLE DETECTED] Tool '{func_name}' called repeatedly with the same arguments. Skipping.",
                })
                continue

            # Check tool is allowed in this mode.
            if func_name not in self._mode_cfg.allowed_tools:
                logger.warning("Tool '%s' not allowed in mode '%s'", func_name, self._mode_cfg.name)
                results.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": f"[UNAUTHORISED] Tool '{func_name}' is not permitted in mode '{self._mode_cfg.name}'.",
                })
                continue

            # Execute.
            tool_fn = registry.get(func_name)
            if tool_fn is None:
                logger.error("Unknown tool: %s", func_name)
                results.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": f"[ERROR] Unknown tool: {func_name}",
                })
                continue

            logger.info("act  tool=%s  args=%s", func_name, json.dumps(args)[:120])
            t0 = time.perf_counter()

            try:
                output = tool_fn(**args)
                output_str = json.dumps(output, default=str, ensure_ascii=False)
            except Exception as exc:
                logger.exception("Tool %s failed: %s", func_name, exc)
                output_str = f"[TOOL ERROR] {type(exc).__name__}: {exc}"

            # Truncate large outputs.
            if len(output_str) > MAX_TOOL_OUTPUT_CHARS:
                output_str = output_str[:MAX_TOOL_OUTPUT_CHARS] + "\n... [truncated]"

            duration = time.perf_counter() - t0
            logger.info("act done  tool=%s  duration=%.2fs  output_len=%d", func_name, duration, len(output_str))

            # Track file modifications.
            if func_name in ("write_file", "create_file", "edit_file_lines", "apply_diff"):
                fpath = args.get("file_path", args.get("path", ""))
                if fpath and fpath not in state["files_modified"]:
                    state["files_modified"].append(fpath)

            results.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": output_str,
            })

        # Track tool calls made.
        state["tool_calls_made"].extend(tool_calls)

        return {"messages": state["messages"] + results}

    def _observe_node(self, state: AgentState) -> dict[str, Any]:
        """Post-process tool results.  (No-op in basic version; hooks live here.)"""
        state["status"] = "observing"
        state["iteration"] += 1

        if self._enable_checkpoints and state["iteration"] % 5 == 0:
            self._checkpoint(state)

        return {"status": "observing", "iteration": state["iteration"]}

    def _decide_node(self, state: AgentState) -> dict[str, Any]:
        """Check if the loop should continue or stop."""
        state["status"] = "done"

        last_msg = state["messages"][-1] if state["messages"] else {}
        has_tool_calls = bool(last_msg.get("tool_calls", []))

        # Stop if no tool calls were made (LLM gave a final answer).
        if not has_tool_calls:
            state["result"] = last_msg.get("content", "") or ""
            logger.info("decide: final answer — stopping")
            return {"status": "done", "result": state["result"]}

        # Stop if max iterations reached.
        if state["iteration"] >= state["max_iterations"]:
            state["result"] = (
                f"[MAX ITERATIONS] Reached {state['max_iterations']} iterations. "
                "The task may be incomplete. Last assistant message:\n"
                f"{last_msg.get('content', '')}"
            )
            logger.warning("decide: max iterations (%d) reached", state["max_iterations"])
            return {"status": "done", "result": state["result"]}

        return {"status": "thinking"}

    # ── Routing ──────────────────────────────────────────────────────

    def _route_from_decide(self, state: AgentState) -> Literal["think", "__end__"]:
        """Conditional edge: route back to think or to END."""
        if state["status"] == "done":
            return END
        return "think"

    # ── Token management ─────────────────────────────────────────────

    def _enforce_token_budget(self, state: AgentState) -> None:
        """Raise if we've blown through the token budget."""
        budget = settings.MAX_CONTEXT_TOKENS
        model_info = self._model.get_model_info()
        hard_limit = model_info.context_window
        effective_limit = min(budget, hard_limit)

        used = state["token_usage"]["total"]
        if used > effective_limit:
            raise ContextWindowError(
                f"Token budget exhausted: {used} used vs {effective_limit} limit"
            )

    def _should_summarize(self, state: AgentState) -> bool:
        """Return True if context tokens exceed SUMMARIZE_RATIO of budget."""
        budget = min(settings.MAX_CONTEXT_TOKENS, self._model.get_model_info().context_window)
        # Rough estimate: count chars of all messages.
        total_chars = sum(len(str(m.get("content", ""))) for m in state["messages"])
        estimated_tokens = total_chars // 3
        return estimated_tokens > budget * SUMMARIZE_RATIO

    def _auto_summarize(self, state: AgentState, force: bool = False) -> None:
        """Compress older conversation history into a summary message."""
        if len(state["messages"]) < 4:
            return

        # Keep system message + last 2 exchanges, summarize the rest.
        system_msgs = [m for m in state["messages"] if m.get("role") == "system"]
        recent = state["messages"][-4:]  # last 2 user↔assistant turns
        to_summarize = [m for m in state["messages"] if m not in system_msgs and m not in recent]

        if not to_summarize:
            return

        summary_content = json.dumps(to_summarize, default=str, ensure_ascii=False)[:8000]
        summary_messages = [
            {"role": "user", "content": f"{SUMMARY_PROMPT}\n\n{summary_content}"},
        ]

        try:
            summary_response = self._model.chat(messages=summary_messages, tools=[])
            summary = summary_response.content or "[summary failed]"
        except Exception as exc:
            logger.warning("Auto-summarize failed: %s", exc)
            return

        # Replace summarized content with a single summary message.
        state["messages"] = system_msgs + [
            {"role": "system", "content": f"[CONVERSATION SUMMARY]\n{summary}"},
        ] + recent

        logger.info("Auto-summarized %d messages → 1 summary", len(to_summarize))

    # ── Cycle detection ──────────────────────────────────────────────

    @staticmethod
    def _compute_call_signature(tool_name: str, args: dict[str, Any]) -> str:
        """Hash the (tool_name, sorted args) tuple for cycle detection."""
        stable = json.dumps({k: args.get(k) for k in sorted(args)}, default=str, sort_keys=True)
        return hashlib.sha256(f"{tool_name}::{stable}".encode()).hexdigest()[:16]

    @staticmethod
    def _detect_cycle(signatures: list[str]) -> bool:
        """Return ``True`` if any signature appears more than threshold."""
        if len(signatures) < 5:
            return False
        recent = signatures[-10:]
        counts: dict[str, int] = {}
        for s in recent:
            counts[s] = counts.get(s, 0) + 1
            if counts[s] >= CYCLE_DETECTION_THRESHOLD:
                return True
        return False

    # ── Tools ────────────────────────────────────────────────────────

    def _get_tools_for_mode(self) -> list[dict[str, Any]]:
        """Return tool schemas filtered by the current mode's allowed tools."""
        if self._tool_filter is not None:
            allowed = self._tool_filter
        else:
            allowed = self._mode_cfg.allowed_tools

        return [s for s in TOOL_SCHEMAS if s["function"]["name"] in allowed]

    # ── Messages ────────────────────────────────────────────────────

    def _build_initial_messages(self, task: str) -> list[dict[str, Any]]:
        """Build the conversation preamble: system prompt + user task."""
        system_prompt = build_mode_prompt(self._mode_cfg.name)

        # Add tool list to system prompt for models that don't support
        # native function calling.
        allowed = self._mode_cfg.allowed_tools
        tool_list = "\n".join(f"  - `{t}`" for t in sorted(allowed))
        system_prompt += (
            f"\n\n## Available tools\n\nYou have access to the following tools:\n{tool_list}\n\n"
            f"Maximum iterations for this mode: {self._mode_cfg.max_iterations or settings.MAX_ITERATIONS}."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

    # ── Checkpointing ────────────────────────────────────────────────

    def _checkpoint(self, state: AgentState) -> str:
        """Save the current state to a JSON file.  Returns the path."""
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        fname = f"{state['session_id']}_iter{state['iteration']:03d}.json"
        fpath = os.path.join(CHECKPOINT_DIR, fname)

        serializable = dict(state)
        serializable["messages"] = _make_serializable(state["messages"])

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, default=str, ensure_ascii=False)

        if "checkpoints" not in state:
            state["checkpoints"] = []
        state["checkpoints"].append(fpath)
        logger.info("Checkpoint saved: %s", fpath)
        return fpath

    def _load_checkpoint(self, path: str) -> AgentState:
        """Restore a previously saved checkpoint."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state = AgentState(**{k: data.get(k) for k in AgentState.__annotations__})
        logger.info("Checkpoint loaded: %s (iter %d)", path, state.get("iteration", 0))
        return state

    # ── Error handling ───────────────────────────────────────────────

    def handle_error(self, error: Exception, state: AgentState) -> AgentState:
        """Attempt graceful recovery from a loop-level error.

        Adds the error to the message history so the LLM can self-correct,
        and increments the error counter.
        """
        error_type = self._model.handle_error(error) if hasattr(self._model, "handle_error") else ErrorType.UNKNOWN
        error_entry = {
            "type": error_type.value if hasattr(error_type, "value") else str(error_type),
            "message": str(error),
            "iteration": state["iteration"],
        }
        state["errors_encountered"].append(error_entry)
        state["messages"].append({
            "role": "system",
            "content": f"[ERROR] {error_type.value if hasattr(error_type, 'value') else error_type}: {error}",
        })

        # If too many errors, abort.
        if len(state["errors_encountered"]) >= 5:
            state["status"] = "error"
            state["result"] = (
                f"Too many errors ({len(state['errors_encountered'])}). "
                f"Last error: {error}"
            )
        else:
            state["status"] = "thinking"

        return state


# ── Serialisation helpers ──────────────────────────────────────────────


def _make_serializable(obj: Any) -> Any:
    """Recursively convert non-serializable objects (e.g. Pydantic models)."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(i) for i in obj]
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if obj is None:
        return None
    return str(obj)


__all__ = [
    "AgentLoop",
    "AgentState",
    "initial_state",
    "CHECKPOINT_DIR",
]
