"""
Role: Doubt-driven development -- adversarial review before every commit.
Author: Wigent AI
Version: 1.0.0

Implements the CLAIM -> EXTRACT -> DOUBT -> RECONCILE -> STOP workflow.
Every non-trivial decision is challenged by a fresh-context reviewer.

Usage:
    from wigent.core.doubt_engine import DoubtEngine, DoubtResult

    engine = DoubtEngine(llm_client)

    result = engine.review(
        claim="We should use Redis for session storage",
        context=codebase_context,
        stakes="high"
    )

    if result.risk_score > 0.7:
        pass
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wigent.models.base_model import BaseModel


class StakesLevel(Enum):
    """Risk level of the decision being reviewed."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DoubtSeverity(Enum):
    """Severity of identified doubt."""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    NONE = "none"


@dataclass(frozen=True)
class DoubtItem:
    """A single identified doubt with evidence and recommendation."""

    category: str
    severity: DoubtSeverity
    doubt_statement: str
    evidence: str
    recommendation: str
    confidence: float


@dataclass
class DoubtResult:
    """Complete result of a doubt-driven review."""

    claim: str
    stakes: StakesLevel
    risk_score: float
    doubts: list[DoubtItem] = field(default_factory=list)
    extracted_assumptions: list[str] = field(default_factory=list)
    reconciled_claim: str | None = None
    proceed: bool = False
    escalation_recommended: bool = False
    cross_model_review: bool = False

    @property
    def critical_count(self) -> int:
        return sum(1 for d in self.doubts if d.severity == DoubtSeverity.CRITICAL)

    @property
    def major_count(self) -> int:
        return sum(1 for d in self.doubts if d.severity == DoubtSeverity.MAJOR)

    def to_markdown(self) -> str:
        """Render review as markdown report."""
        status = "PROCEED" if self.proceed else "BLOCKED"
        if self.escalation_recommended:
            status = "ESCALATE"

        lines = [
            f"# Doubt-Driven Review: {self.claim[:60]}...",
            f"",
            f"**Stakes:** {self.stakes.value.upper()}",
            f"**Risk Score:** {self.risk_score:.2f}/1.0",
            f"**Status:** {status}",
            f"",
            f"## Assumptions Extracted ({len(self.extracted_assumptions)})",
        ]

        for i, assumption in enumerate(self.extracted_assumptions, 1):
            lines.append(f"{i}. {assumption}")

        lines.extend([
            f"",
            f"## Doubts Raised ({len(self.doubts)})",
            f"",
        ])

        for doubt in sorted(self.doubts, key=lambda d: d.severity.value):
            icon = {
                DoubtSeverity.CRITICAL: "*",
                DoubtSeverity.MAJOR: "+",
                DoubtSeverity.MINOR: "-",
            }.get(doubt.severity, "o")

            lines.extend([
                f"### {icon} {doubt.category.upper()}: {doubt.doubt_statement}",
                f"",
                f"**Severity:** {doubt.severity.value}",
                f"**Confidence:** {doubt.confidence:.0%}",
                f"",
                f"**Evidence:** {doubt.evidence}",
                f"",
                f"**Recommendation:** {doubt.recommendation}",
                f"",
                "---",
                f"",
            ])

        if self.reconciled_claim:
            lines.extend([
                f"## Reconciled Claim",
                f"",
                f"{self.reconciled_claim}",
                f"",
            ])

        lines.extend([
            f"## Decision",
            f"",
            f"- **Proceed:** {'Yes' if self.proceed else 'No'}",
            f"- **Escalation Recommended:** {'Yes' if self.escalation_recommended else 'No'}",
            f"- **Cross-Model Review:** {'Yes' if self.cross_model_review else 'No'}",
        ])

        return "\n".join(lines)


class DoubtEngine:
    """
    Adversarial review engine that challenges every non-trivial decision.

    Workflow: CLAIM -> EXTRACT -> DOUBT -> RECONCILE -> STOP

    Principles:
    1. Fresh context -- reviewer has no memory of original reasoning
    2. Specific doubts -- not "this might be wrong" but "what if X happens"
    3. Evidence-based -- every doubt needs a concrete reason
    4. Actionable -- every doubt needs a mitigation or acceptance
    5. Proportionate -- high stakes = more scrutiny, more escalation
    """

    RISK_THRESHOLDS = {
        StakesLevel.LOW: 0.8,
        StakesLevel.MEDIUM: 0.6,
        StakesLevel.HIGH: 0.4,
    }

    CROSS_MODEL_THRESHOLD = 0.5

    def __init__(
        self,
        llm_client: BaseModel,
        cross_model_client: BaseModel | None = None,
        max_doubts: int = 10,
    ) -> None:
        self.primary_llm = llm_client
        self.cross_model = cross_model_client
        self.max_doubts = max_doubts

        self.reviews_completed = 0
        self.doubts_found = 0
        self.escalations_triggered = 0
        self.cross_model_reviews = 0

    def review(
        self,
        claim: str,
        context: dict,
        stakes: StakesLevel | str = StakesLevel.MEDIUM,
        author_reasoning: str = "",
    ) -> DoubtResult:
        """
        Execute full doubt-driven review workflow.

        Args:
            claim: The decision or statement being reviewed
            context: Relevant codebase, requirements, constraints
            stakes: Risk level (low/medium/high)
            author_reasoning: Original author's justification

        Returns:
            DoubtResult with full analysis and proceed/deny recommendation
        """
        if isinstance(stakes, str):
            stakes = StakesLevel(stakes.lower())

        # Step 1: EXTRACT
        assumptions = self._extract_assumptions(claim, context, author_reasoning)

        # Step 2: DOUBT
        doubts = self._generate_doubts(claim, assumptions, context, stakes)

        # Step 3: RECONCILE
        reconciled, risk_score = self._reconcile(claim, doubts, stakes)

        # Step 4: STOP
        proceed, escalate, cross_model = self._decide(
            risk_score=risk_score,
            stakes=stakes,
            critical_count=sum(1 for d in doubts if d.severity == DoubtSeverity.CRITICAL),
        )

        if cross_model and self.cross_model:
            doubts = self._cross_model_review(claim, doubts, context)
            risk_score = self._recalculate_risk(doubts)
            proceed, escalate, _ = self._decide(risk_score, stakes, 0)

        self.reviews_completed += 1
        self.doubts_found += len(doubts)
        if escalate:
            self.escalations_triggered += 1
        if cross_model:
            self.cross_model_reviews += 1

        return DoubtResult(
            claim=claim,
            stakes=stakes,
            risk_score=risk_score,
            doubts=doubts,
            extracted_assumptions=assumptions,
            reconciled_claim=reconciled,
            proceed=proceed,
            escalation_recommended=escalate,
            cross_model_review=cross_model,
        )

    def quick_check(self, claim: str) -> bool:
        """
        Fast check for obvious red flags. Returns True if no major issues.

        Use for low-stakes decisions or as pre-filter before full review.
        """
        red_flags = [
            r"never.*test",
            r"just.*temp",
            r"TODO.*later",
            r"hard.*code",
            r"should.*work",
            r"probably.*fine",
            r"trust.*me",
            r"no.*need.*doc",
            r"only.*internal",
            r"can.*refactor.*later",
        ]

        claim_lower = claim.lower()
        for flag in red_flags:
            if re.search(flag, claim_lower):
                return False

        return True

    def get_stats(self) -> dict[str, int | float]:
        """Return review statistics."""
        return {
            "reviews_completed": self.reviews_completed,
            "doubts_found": self.doubts_found,
            "avg_doubts_per_review": (
                self.doubts_found / self.reviews_completed
                if self.reviews_completed > 0 else 0
            ),
            "escalations_triggered": self.escalations_triggered,
            "escalation_rate": (
                self.escalations_triggered / self.reviews_completed
                if self.reviews_completed > 0 else 0
            ),
            "cross_model_reviews": self.cross_model_reviews,
        }

    # =================================================================
    # Workflow Steps
    # =================================================================

    def _extract_assumptions(
        self,
        claim: str,
        context: dict,
        author_reasoning: str,
    ) -> list[str]:
        """
        EXTRACT: Pull out unstated assumptions from the claim.
        """
        prompt = f"""You are a skeptical reviewer examining a technical decision.

## Claim
{claim}

## Author's Reasoning
{author_reasoning or "Not provided"}

## Context
{json.dumps(context, indent=2)[:2000]}

## Task
Extract ALL unstated assumptions in this claim. Look for:
1. Implicit constraints ("we'll use X" assumes X is available)
2. Hidden dependencies (Y requires Z, but Z isn't mentioned)
3. Temporal assumptions ("this works" assumes current conditions persist)
4. Scale assumptions ("fast enough" assumes specific load)
5. Security assumptions ("only internal" assumes no attacker)
6. Compatibility assumptions ("works with" assumes versions match)

## Output Format
Return ONLY a JSON array of assumption strings. No explanation.

```json
[
  "Assumes Redis is already deployed and accessible",
  "Assumes user session data fits in memory (<512MB)",
  ...
]
```
"""

        response = self.primary_llm.generate(prompt, temperature=0.3, max_tokens=2000)

        try:
            match = re.search(r"\[.*\]", response, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

        lines = [l.strip("- *") for l in response.split("\n") if l.strip().startswith(("-", "*"))]
        return lines[:10] if lines else ["No explicit assumptions found"]

    def _generate_doubts(
        self,
        claim: str,
        assumptions: list[str],
        context: dict,
        stakes: StakesLevel,
    ) -> list[DoubtItem]:
        """
        DOUBT: Challenge each assumption with specific scenarios.
        """
        prompt = f"""You are an adversarial reviewer challenging a technical decision.

## Claim
{claim}

## Stakes
{stakes.value.upper()}: {"Low risk, reversible" if stakes == StakesLevel.LOW else "Medium risk, some cleanup" if stakes == StakesLevel.MEDIUM else "HIGH RISK: Production, security, or irreversible"}

## Assumptions to Challenge
{chr(10).join(f"- {a}" for a in assumptions)}

## Context
{json.dumps(context, indent=2)[:1500]}

## Task
For each assumption, generate specific doubts using "WHAT IF" format.

Rules:
- Be specific: "WHAT IF Redis fails?" not "What about reliability?"
- Include evidence: Why is this doubt valid?
- Suggest mitigation: How to address or accept the risk?
- Severity: critical (must fix), major (should fix), minor (note)

## Output Format
Return ONLY a JSON array:

```json
[
  {{
    "category": "reliability",
    "severity": "major",
    "doubt": "WHAT IF Redis becomes unavailable? All sessions are lost and users are logged out.",
    "evidence": "Redis is single point of failure. No fallback to database mentioned.",
    "recommendation": "Add Redis Sentinel for HA or fallback to database sessions",
    "confidence": 0.85
  }}
]
```

Maximum {self.max_doubts} doubts.
"""

        response = self.primary_llm.generate(prompt, temperature=0.4, max_tokens=3000)

        doubts = []
        try:
            match = re.search(r"\[.*\]", response, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                for item in data[:self.max_doubts]:
                    severity = DoubtSeverity(item.get("severity", "minor"))
                    if stakes == StakesLevel.HIGH and severity == DoubtSeverity.MINOR:
                        severity = DoubtSeverity.MAJOR

                    doubts.append(DoubtItem(
                        category=item.get("category", "general"),
                        severity=severity,
                        doubt_statement=item.get("doubt", ""),
                        evidence=item.get("evidence", ""),
                        recommendation=item.get("recommendation", ""),
                        confidence=float(item.get("confidence", 0.5)),
                    ))
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

        return doubts

    def _reconcile(
        self,
        claim: str,
        doubts: list[DoubtItem],
        stakes: StakesLevel,
    ) -> tuple[str | None, float]:
        """
        RECONCILE: Address doubts or accept risk.
        """
        if not doubts:
            return claim, 0.0

        critical_weight = 1.0
        major_weight = 0.5
        minor_weight = 0.1

        weighted_score = sum(
            d.confidence * {
                DoubtSeverity.CRITICAL: critical_weight,
                DoubtSeverity.MAJOR: major_weight,
                DoubtSeverity.MINOR: minor_weight,
            }.get(d.severity, 0)
            for d in doubts
        )

        max_possible = len(doubts) * critical_weight
        risk_score = min(weighted_score / max(max_possible, 1), 1.0)

        if stakes == StakesLevel.HIGH:
            risk_score = min(risk_score * 1.5, 1.0)

        if risk_score < 0.5:
            mitigations = [d.recommendation for d in doubts if d.severity != DoubtSeverity.MINOR]
            reconciled = f"{claim}\n\nMitigations:\n" + "\n".join(f"- {m}" for m in mitigations)
            return reconciled, risk_score

        return None, risk_score

    def _decide(
        self,
        risk_score: float,
        stakes: StakesLevel,
        critical_count: int,
    ) -> tuple[bool, bool, bool]:
        """
        STOP: Decide whether to proceed, escalate, or cross-model review.
        """
        threshold = self.RISK_THRESHOLDS[stakes]

        if critical_count > 0:
            return False, True, risk_score > self.CROSS_MODEL_THRESHOLD

        if risk_score >= threshold:
            if stakes == StakesLevel.HIGH:
                return False, True, True
            else:
                return False, True, False

        if risk_score > self.CROSS_MODEL_THRESHOLD:
            return True, False, True

        return True, False, False

    def _cross_model_review(
        self,
        claim: str,
        doubts: list[DoubtItem],
        context: dict,
    ) -> list[DoubtItem]:
        """
        Get second opinion from different LLM model.
        """
        if not self.cross_model:
            return doubts

        prompt = f"""You are reviewing another AI's doubt analysis.

## Original Claim
{claim}

## Doubts Found
{chr(10).join(f"- [{d.severity.value}] {d.doubt_statement}" for d in doubts)}

## Context
{json.dumps(context, indent=2)[:1000]}

## Task
Review these doubts. Are they valid? Are any missing? Are any overblown?

Return ONLY a JSON array of doubts to ADD or MODIFY. Empty array if all doubts are valid.
"""

        response = self.cross_model.generate(prompt, temperature=0.3, max_tokens=2000)

        try:
            match = re.search(r"\[.*\]", response, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                for item in data:
                    doubts.append(DoubtItem(
                        category=item.get("category", "cross-model"),
                        severity=DoubtSeverity(item.get("severity", "minor")),
                        doubt_statement=f"[CROSS-MODEL] {item.get('doubt', '')}",
                        evidence=item.get("evidence", ""),
                        recommendation=item.get("recommendation", ""),
                        confidence=float(item.get("confidence", 0.5)),
                    ))
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

        return doubts

    def _recalculate_risk(self, doubts: list[DoubtItem]) -> float:
        """Recalculate risk after cross-model review."""
        if not doubts:
            return 0.0

        critical = sum(1 for d in doubts if d.severity == DoubtSeverity.CRITICAL)
        major = sum(1 for d in doubts if d.severity == DoubtSeverity.MAJOR)

        return min(critical * 0.5 + major * 0.2, 1.0)
