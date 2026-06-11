# ════════════════════════════════════════
# wigent — Skills Configuration
# Role: Default skill registry based on the Addy Osmani agent-skills pack
# Author: wigent team
# Version: 0.1.0
# ════════════════════════════════════════

"""Default skill definitions for the Wigent skill router.

Provides the full 24-skill roster from the Addy Osmani agent-skills pack,
organised across seven phases (meta → define → plan → build → verify →
review → ship).  Each skill ships with curated trigger phrases and
confidence thresholds tuned for production use.

Usage
-----
    from wigent.config.skills import load_default_skills, get_skill_prompt_path

    skills = load_default_skills()
    for s in skills:
        print(f"{s.name} ({s.phase}) — {s.description}")

    path = get_skill_prompt_path("interview-me")
    # → Path("wigent/prompts/interview-me.md")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from wigent.core.skill_router import Skill

__all__ = [
    "load_default_skills",
    "get_skill_prompt_path",
]

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

_VALID_PHASES = frozenset({
    "meta", "define", "plan", "build", "verify", "review", "ship",
})


class _SkillDef(BaseModel):
    """Internal validated skill definition.

    Used at load time to validate all skill metadata before constructing
    the ``Skill`` dataclass instances consumed by the router.
    """

    name: str = Field(pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
    phase: str = Field(min_length=3)
    description: str = Field(min_length=10)
    triggers: list[str] = Field(default_factory=list, min_length=3)
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    prompt_template: str = ""

    @field_validator("phase")
    @classmethod
    def _check_phase(cls, v: str) -> str:
        if v not in _VALID_PHASES:
            msg = f"phase must be one of {sorted(_VALID_PHASES)}, got {v!r}"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _fill_prompt_template(self) -> _SkillDef:
        if not self.prompt_template and self.name:
            self.prompt_template = f"prompts/{self.name}.md"
        return self

    def to_skill(self) -> Skill:
        return Skill(
            name=self.name,
            phase=self.phase,
            description=self.description,
            triggers=list(self.triggers),
            confidence_threshold=self.confidence_threshold,
            prompt_template=self.prompt_template,
        )


# ---------------------------------------------------------------------------
# Default skill definitions — Addy Osmani agent-skills pack
# ---------------------------------------------------------------------------
# Each entry is a dict consumed by _SkillDef for Pydantic validation.

_DEFAULT_SKILL_DEFS: list[dict[str, Any]] = [
    # ── META ────────────────────────────────────────────────────────────
    {
        "name": "using-agent-skills",
        "phase": "meta",
        "description": "Maps incoming work to the right skill workflow",
        "triggers": [
            "choose skill", "pick a workflow", "which skill", "how to start",
            "suggest approach", "guide me", "what should I use",
            "recommend a skill", "what can you do", "show skills",
        ],
        "confidence_threshold": 0.6,
    },
    # ── DEFINE ──────────────────────────────────────────────────────────
    {
        "name": "interview-me",
        "phase": "define",
        "description": "One-question-at-a-time interview until 95% confidence",
        "triggers": [
            "interview", "mock interview", "practice interview", "quiz me",
            "test my knowledge", "technical screen", "coding interview",
            "interview prep", "ask me questions", "drill me",
        ],
        "prompt_template": "prompts/interview.md",
    },
    {
        "name": "idea-refine",
        "phase": "define",
        "description": "Divergent/convergent thinking for vague ideas",
        "triggers": [
            "brainstorm", "vague idea", "rough concept", "ideate",
            "explore options", "divergent thinking", "converge on",
            "refine idea", "what if", "spitball",
        ],
        "prompt_template": "prompts/ideate.md",
    },
    {
        "name": "spec-driven-development",
        "phase": "define",
        "description": "Write PRD before any code",
        "triggers": [
            "spec", "prd", "requirements doc", "product spec", "technical spec",
            "specification", "write prd", "define requirements", "feature spec",
            "functional spec",
        ],
    },
    # ── PLAN ────────────────────────────────────────────────────────────
    {
        "name": "planning-and-task-breakdown",
        "phase": "plan",
        "description": "Decompose specs into atomic tasks",
        "triggers": [
            "plan", "break down", "task list", "decompose", "estimate",
            "ticket", "backlog", "sprint", "roadmap", "milestone",
            "work breakdown", "story points",
        ],
    },
    # ── BUILD ───────────────────────────────────────────────────────────
    {
        "name": "incremental-implementation",
        "phase": "build",
        "description": "Thin vertical slices",
        "triggers": [
            "vertical slice", "thin slice", "incremental", "iterate",
            "small step", "working increment", "gradual build", "slice",
            "end to end", "walking skeleton",
        ],
    },
    {
        "name": "test-driven-development",
        "phase": "build",
        "description": "Red-Green-Refactor",
        "triggers": [
            "tdd", "red green refactor", "test first", "write test",
            "unit test", "test driven", "test coverage", "test before code",
            "failing test", "make it green",
        ],
    },
    {
        "name": "context-engineering",
        "phase": "build",
        "description": "Feed right info at right time",
        "triggers": [
            "context window", "token limit", "too much context", "prune context",
            "relevant files", "load context", "manage context", "prompt budget",
            "context size", "trim context",
        ],
    },
    {
        "name": "source-driven-development",
        "phase": "build",
        "description": "Ground decisions in official docs",
        "triggers": [
            "official docs", "documentation", "specs", "standard",
            "spec driven", "following docs", "ground in docs",
            "source of truth", "reference", "authoritative",
        ],
    },
    {
        "name": "doubt-driven-development",
        "phase": "build",
        "description": "Adversarial review before commit",
        "triggers": [
            "adversarial review", "self review", "what could go wrong",
            "edge case", "hidden risk", "doubt", "verify assumption",
            "challenge this", "worst case", "think critically",
        ],
    },
    {
        "name": "frontend-ui-engineering",
        "phase": "build",
        "description": "Component architecture, WCAG 2.1 AA",
        "triggers": [
            "ui component", "frontend", "react component", "css",
            "responsive", "accessibility", "wcag", "design system",
            "storybook", "component library", "ui engineering",
        ],
    },
    {
        "name": "api-and-interface-design",
        "phase": "build",
        "description": "Contract-first design",
        "triggers": [
            "rest api", "api design", "endpoint", "contract", "openapi",
            "swagger", "grpc", "graphql schema", "interface design",
            "api spec", "api versioning",
        ],
    },
    # ── VERIFY ──────────────────────────────────────────────────────────
    {
        "name": "browser-testing-with-devtools",
        "phase": "verify",
        "description": "Chrome DevTools MCP",
        "triggers": [
            "devtools", "browser test", "console error", "network request",
            "dom", "elements panel", "debug in browser", "chrome devtools",
            "inspect element", "console debug",
        ],
    },
    {
        "name": "debugging-and-error-recovery",
        "phase": "verify",
        "description": "5-step triage",
        "triggers": [
            "bug", "error", "crash", "stack trace", "exception",
            "debug", "root cause", "triage", "reproduce", "fix bug",
            "not working", "unexpected behaviour",
        ],
    },
    # ── REVIEW ──────────────────────────────────────────────────────────
    {
        "name": "code-review-and-quality",
        "phase": "review",
        "description": "5-axis review",
        "triggers": [
            "code review", "review my code", "pull request review",
            "pr review", "quality check", "review changes", "code quality",
            "review this", "peer review", "approve pr",
        ],
    },
    {
        "name": "code-simplification",
        "phase": "review",
        "description": "Chesterton's Fence, Rule of 500",
        "triggers": [
            "simplify", "complex code", "too nested", "duplicated",
            "over engineered", "chesterton", "simplification",
            "refactor for clarity", "reduce complexity", "too many lines",
        ],
    },
    {
        "name": "security-and-hardening",
        "phase": "review",
        "description": "OWASP Top 10",
        "triggers": [
            "security", "owasp", "vulnerability", "xss", "sql injection",
            "csrf", "hardening", "threat model", "audit security",
            "secure code", "cve",
        ],
        "confidence_threshold": 0.8,
    },
    {
        "name": "performance-optimization",
        "phase": "review",
        "description": "Measure-first approach",
        "triggers": [
            "performance", "slow", "optimize", "bottleneck", "latency",
            "load time", "profiling", "benchmark", "render performance",
            "memory leak", "cpu usage",
        ],
    },
    # ── SHIP ────────────────────────────────────────────────────────────
    {
        "name": "git-workflow-and-versioning",
        "phase": "ship",
        "description": "Trunk-based dev",
        "triggers": [
            "git", "branch", "commit", "merge", "rebase", "trunk based",
            "version control", "push", "pull request", "git workflow",
            "squash", "cherry pick",
        ],
    },
    {
        "name": "ci-cd-and-automation",
        "phase": "ship",
        "description": "Shift Left",
        "triggers": [
            "ci/cd", "continuous integration", "deploy", "pipeline",
            "github actions", "automation", "build pipeline",
            "release process", "rollback", "deployment",
        ],
    },
    {
        "name": "deprecation-and-migration",
        "phase": "ship",
        "description": "Code-as-liability",
        "triggers": [
            "migrate", "deprecate", "upgrade", "migration path",
            "sunset", "legacy", "transition", "version upgrade",
            "backward compat", "breaking change", "phase out",
        ],
        "confidence_threshold": 0.8,
    },
    {
        "name": "documentation-and-adrs",
        "phase": "ship",
        "description": "ADRs and API docs",
        "triggers": [
            "documentation", "adr", "architecture decision", "readme",
            "api docs", "wiki", "docstring", "technical writing",
            "changelog", "contributing guide",
        ],
    },
    {
        "name": "observability-and-instrumentation",
        "phase": "ship",
        "description": "Structured logging, RED metrics",
        "triggers": [
            "monitoring", "logging", "metrics", "alert", "observability",
            "telemetry", "structured logging", "grafana", "prometheus",
            "datadog", "tracing",
        ],
    },
    {
        "name": "shipping-and-launch",
        "phase": "ship",
        "description": "Pre-launch checklist",
        "triggers": [
            "launch", "ship", "release", "deploy to prod", "go live",
            "production release", "rollout", "cutover",
            "pre launch checklist", "release plan",
        ],
        "confidence_threshold": 0.8,
    },
]


def load_default_skills() -> list[Skill]:
    """Return all 24 skills from the Addy Osmani agent-skills pack.

    Each skill definition is validated through a Pydantic model before
    being converted to the ``Skill`` dataclass expected by ``SkillRouter``.

    Returns:
        A list of 24 ``Skill`` instances covering all seven phases.
    """
    skills: list[Skill] = []
    for raw in _DEFAULT_SKILL_DEFS:
        validated = _SkillDef(**raw)
        skills.append(validated.to_skill())
    return skills


def get_skill_prompt_path(skill_name: str) -> Path:
    """Return the expected filesystem path to a skill's prompt template.

    Args:
        skill_name: The skill's unique identifier (e.g. ``"interview-me"``).

    Returns:
        A ``Path`` object — e.g. ``wigent/prompts/interview-me.md``.
    """
    return _PROMPT_DIR / f"{skill_name}.md"
