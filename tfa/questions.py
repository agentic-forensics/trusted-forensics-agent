"""The seven-question resolvers (companion A.5, method Phase 5).

Each resolver settles one question from the spans and returns an Answer carrying
a classification, the evidence it rests on, and, where it cannot be settled, a
named gap recording the party and data class that would have closed it. A
question is never silently dropped and never guessed (companion A.2, A.5).

Question 5 (auto-approval) follows the model exactly: a positive dcfp.approval.*
record on the decision-to-execution edge answers it; its absence is recorded as
a gap, not read as auto-approval, unless the approval instrumentation has first
been shown complete (companion A.5 Q5). The synthetic trace omits that record on
purpose, so Q5 is a named gap here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from .model import Span


class Classification(str, Enum):
    """Per-question classification (companion A.2).

    A question is 'resolved' when it is either answered (from direct evidence or
    corroborated inference, possibly partially) or explicitly recorded as
    unavailable/lost/contested with a named gap. It is never left unclassified.
    """

    ANSWERED_DIRECT = "answered from direct evidence"
    ANSWERED_INFERRED = "answered by corroborated inference"
    PARTIAL = "partially answered"
    NOT_APPLICABLE = "not applicable"
    UNANSWERED_UNAVAILABLE = "unanswered because the evidence is unavailable"
    UNANSWERED_LOST = "unanswered because evidence known to have existed has been lost"
    CONTESTED = "contested"


@dataclass(frozen=True)
class NamedGap:
    """A named gap: the party and data class that would have closed a question.

    Recording the gap by name is what makes the incompleteness itself defensible
    and actionable (companion A.2, method Phase 5).
    """

    party: str
    data_class: str
    note: str = ""


@dataclass(frozen=True)
class Answer:
    """The resolution of one question."""

    qid: str
    question: str
    classification: Classification
    value: str
    evidence: Tuple[str, ...] = ()          # span ids and/or attribute keys
    gap: Optional[NamedGap] = None

    @property
    def resolved(self) -> bool:
        answered = self.classification in (
            Classification.ANSWERED_DIRECT,
            Classification.ANSWERED_INFERRED,
            Classification.PARTIAL,
            Classification.NOT_APPLICABLE,
            Classification.CONTESTED,
        )
        recorded_gap = (
            self.classification
            in (
                Classification.UNANSWERED_UNAVAILABLE,
                Classification.UNANSWERED_LOST,
            )
            and self.gap is not None
        )
        return answered or recorded_gap


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _first(spans: Sequence[Span], op: str) -> Optional[Span]:
    for s in spans:
        if s.operation_name == op:
            return s
    return None


def _all(spans: Sequence[Span], op: str) -> List[Span]:
    return [s for s in spans if s.operation_name == op]


# --------------------------------------------------------------------------- #
# The seven resolvers
# --------------------------------------------------------------------------- #

def q1_who_set_the_goal(spans: Sequence[Span]) -> Answer:
    """Root span / first message under the conversation; principal identity."""
    invoke = _first(spans, "invoke_agent")
    if invoke is not None:
        principal = invoke.get("dcfp.principal.id") or invoke.get("auth.subject")
        messages = invoke.get("gen_ai.input.messages") or []
        goal = messages[0]["content"] if messages else ""
        if principal:
            return Answer(
                qid="Q1",
                question="Who set the goal?",
                classification=Classification.ANSWERED_DIRECT,
                value=f"{principal}: {goal!r}",
                evidence=(invoke.span_id, "dcfp.principal.id", "gen_ai.input.messages"),
            )
    return Answer(
        qid="Q1",
        question="Who set the goal?",
        classification=Classification.UNANSWERED_UNAVAILABLE,
        value="no root invocation with a principal identity was found",
        gap=NamedGap(
            party="agent runtime / identity provider",
            data_class="root invoke_agent span with principal auth attributes",
        ),
    )


def q2_which_model(spans: Sequence[Span]) -> Answer:
    """gen_ai.request.model, provider.name, agent.version from the inference span."""
    inf = _first(spans, "inference")
    if inf is not None and inf.get("gen_ai.request.model"):
        model = inf.get("gen_ai.request.model")
        provider = inf.get("gen_ai.provider.name", "unknown provider")
        version = inf.get("gen_ai.agent.version", "unknown version")
        return Answer(
            qid="Q2",
            question="Which model and version?",
            classification=Classification.ANSWERED_DIRECT,
            value=f"{model} ({provider}); agent version {version}",
            evidence=(inf.span_id, "gen_ai.request.model", "gen_ai.provider.name",
                      "gen_ai.agent.version"),
        )
    return Answer(
        qid="Q2",
        question="Which model and version?",
        classification=Classification.UNANSWERED_UNAVAILABLE,
        value="no inference span recording the model was found",
        gap=NamedGap(
            party="model provider",
            data_class="inference span with gen_ai.request.model and version",
        ),
    )


def q3_tools_exposed(
    spans: Sequence[Span], certificates: Optional[Dict[str, Dict]] = None
) -> Answer:
    """Declared tool set (create_agent / capability cert) vs observed calls."""
    create = _first(spans, "create_agent")
    declared: List[str] = []
    if create is not None:
        declared = list(create.get("gen_ai.request.tools") or [])
    if certificates:
        for cert in certificates.values():
            for perm in cert.get("permitted", []):
                if perm.get("tool") not in declared:
                    declared.append(perm.get("tool"))
    observed = sorted({s.get("gen_ai.tool.name") for s in _all(spans, "execute_tool")})
    if declared:
        return Answer(
            qid="Q3",
            question="What tools were exposed, and at what scope?",
            classification=Classification.ANSWERED_DIRECT,
            value=f"declared: {sorted(declared)}; observed in use: {observed}",
            evidence=(create.span_id if create else "capability-certificate",
                      "gen_ai.request.tools"),
        )
    return Answer(
        qid="Q3",
        question="What tools were exposed, and at what scope?",
        classification=Classification.UNANSWERED_UNAVAILABLE,
        value="no declared tool set or certificate was found",
        gap=NamedGap(
            party="integrator / platform security",
            data_class="create_agent declared tool set or capability certificate",
        ),
    )


def q4_whose_identity(spans: Sequence[Span]) -> Answer:
    """Auth subject / service principal on tool and downstream spans; agent id."""
    subjects = set()
    agents = set()
    for s in spans:
        subj = s.get("auth.subject") or s.get("dcfp.principal.id")
        if subj:
            subjects.add(subj)
        agent = s.get("gen_ai.agent.id") or s.get("dcfp.agent.id")
        if agent:
            agents.add(agent)
    if subjects:
        return Answer(
            qid="Q4",
            question="Whose identity acted?",
            classification=Classification.ANSWERED_DIRECT,
            value=(
                f"thin attribution: actions ran under {sorted(subjects)} "
                f"via agent {sorted(agents)}. This establishes the identity the "
                "action ran under, not that the principal directed it."
            ),
            evidence=("auth.subject", "dcfp.agent.id"),
        )
    return Answer(
        qid="Q4",
        question="Whose identity acted?",
        classification=Classification.UNANSWERED_UNAVAILABLE,
        value="no auth subject was recorded on the acting spans",
        gap=NamedGap(
            party="identity provider",
            data_class="auth subject / service principal on tool spans",
        ),
    )


def q5_auto_approved(spans: Sequence[Span]) -> Answer:
    """Positive dcfp.approval.* record; absence is a gap, not auto-approval."""
    approvals = []
    for s in spans:
        approval_keys = [k for k in s.attributes if k.startswith("dcfp.approval")]
        if approval_keys:
            approvals.append((s.span_id, approval_keys))
    if approvals:
        span_id, keys = approvals[0]
        return Answer(
            qid="Q5",
            question="What was auto-approved without human review?",
            classification=Classification.ANSWERED_DIRECT,
            value=f"approval record present on {span_id}: {sorted(keys)}",
            evidence=(span_id, *keys),
        )
    # No positive approval record. The model forbids reading absence as
    # auto-approval unless the approval instrumentation has first been shown
    # complete (it has not). Record a named gap.
    return Answer(
        qid="Q5",
        question="What was auto-approved without human review?",
        classification=Classification.UNANSWERED_UNAVAILABLE,
        value=(
            "no dcfp.approval.* record is present on the decision-to-execution "
            "edge. Absence is NOT read as auto-approval; the approval "
            "instrumentation has not been shown to be complete."
        ),
        gap=NamedGap(
            party="agent runtime / approval service",
            data_class="dcfp.approval.* records (required, mode, decision, actor, "
                       "policy id and version)",
            note="closing this requires either the positive approval records or "
                 "a demonstration that approval instrumentation is complete.",
        ),
    )


def q6_context_ingested(spans: Sequence[Span]) -> Answer:
    """Retrieval spans, prior tool-result spans feeding the next inference."""
    sources: List[str] = []
    evidence: List[str] = []
    injected = False
    for s in _all(spans, "retrieval"):
        src = s.get("gen_ai.data_source.id")
        if src:
            sources.append(f"retrieval:{src}")
            evidence.append(s.span_id)
    for s in _all(spans, "execute_tool"):
        result = s.get("gen_ai.tool.result") or {}
        for msg in result.get("messages", []):
            if msg.get("dcfp.injected_instruction"):
                injected = True
            sources.append(f"tool-result:{s.get('gen_ai.tool.name')}")
            evidence.append(s.span_id)
    if sources:
        note = " An injected instruction was present in ingested content." if injected else ""
        return Answer(
            qid="Q6",
            question="What context was ingested, and when?",
            classification=Classification.ANSWERED_DIRECT,
            value=f"ingested from {sorted(set(sources))}.{note}",
            evidence=tuple(dict.fromkeys(evidence)),
        )
    return Answer(
        qid="Q6",
        question="What context was ingested, and when?",
        classification=Classification.UNANSWERED_UNAVAILABLE,
        value="no retrieval or tool-result context was recorded",
        gap=NamedGap(
            party="agent runtime / retrieval source",
            data_class="retrieval spans and tool-result content",
        ),
    )


def q7_what_ran_downstream(spans: Sequence[Span]) -> Answer:
    """execute_tool results and child spans vs the stated intent (Brain)."""
    inf = _first(spans, "inference")
    intent = inf.get("dcfp.intent.action") if inf else None

    effects: List[str] = []
    evidence: List[str] = []
    for s in spans:
        observed_call = s.get("dcfp.effect.observed")
        if observed_call:
            method = s.get("http.request.method", "")
            addr = s.get("server.address", "")
            recipient = s.get("dcfp.egress.recipient", "")
            effects.append(
                f"{method} {addr} (recipient {recipient}) linked to {observed_call}"
            )
            evidence.append(s.span_id)

    if effects:
        stated = intent or "no stated intent recorded"
        return Answer(
            qid="Q7",
            question="What actually ran downstream?",
            classification=Classification.ANSWERED_DIRECT,
            value=(
                f"stated intent (Brain): {stated!r}. Observed effect (Hands): "
                f"{'; '.join(effects)}. The observed effect is linked to the "
                "tool call by dcfp.effect.observed."
            ),
            evidence=tuple(dict.fromkeys(evidence + ([inf.span_id] if inf else []))),
        )
    return Answer(
        qid="Q7",
        question="What actually ran downstream?",
        classification=Classification.UNANSWERED_UNAVAILABLE,
        value="no downstream effect linked by dcfp.effect.observed was found",
        gap=NamedGap(
            party="tool provider / victim infrastructure",
            data_class="downstream child spans linked by dcfp.effect.observed",
        ),
    )


def resolve_all(
    spans: Sequence[Span], certificates: Optional[Dict[str, Dict]] = None
) -> List[Answer]:
    """Resolve Q1 to Q7 in order (companion A.5)."""
    return [
        q1_who_set_the_goal(spans),
        q2_which_model(spans),
        q3_tools_exposed(spans, certificates),
        q4_whose_identity(spans),
        q5_auto_approved(spans),
        q6_context_ingested(spans),
        q7_what_ran_downstream(spans),
    ]
