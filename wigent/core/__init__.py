# ════════════════════════════════════════
# wigent — Core Package
# Role: Agent brain and think-act-observe loop
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Agent orchestration — loop, state management, dispatch, main entry point.

Components
----------
- ``WigentAgent``  — Main entry point for all user interactions.
- ``AgentLoop``    — LangGraph-powered Think → Act → Observe loop.
- ``Orchestrator`` — Mode router / task analyser / multi-mode coordinator.

Sub-modules
-----------
- ``agent.py``        — Public API (``WigentAgent``, ``run_agent``).
- ``loop.py``         — Core loop with StateGraph, token management,
                        cycle detection, auto-summarization, checkpoints.
- ``orchestrator.py`` — Task classification, mode routing, multi-mode plans.
- ``triage_engine.py`` — 5-step systematic debugging pipeline (REPRODUCE -> LOCALIZE -> REDUCE -> FIX -> GUARD).
"""

from wigent.core.agent import Agent, WigentAgent, run_agent
from wigent.core.loop import AgentLoop, AgentState, initial_state
from wigent.core.orchestrator import Orchestrator
from wigent.core.planner import Task, Planner
from wigent.core.executor import CoderAgent
from wigent.core.debugger import DebuggerAgent
from wigent.core.triage_engine import TriageEngine, TriageState, TriageStep, ErrorSignature
from wigent.core.skill_router import Skill, SkillRouter

__all__ = [
    "WigentAgent",
    "Agent",
    "run_agent",
    "AgentLoop",
    "AgentState",
    "initial_state",
    "Orchestrator",
    "Task",
    "Planner",
    "CoderAgent",
    "DebuggerAgent",
    "TriageEngine",
    "TriageState",
    "TriageStep",
    "ErrorSignature",
    "Skill",
    "SkillRouter",
]
