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

from .model import MissingSegment, Span


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


def _affecting(
    missing_segments: Optional[Sequence[MissingSegment]], qid: str
) -> List[MissingSegment]:
    """Return declared missing segments that bear on this question."""
    return [m for m in (missing_segments or ()) if qid in m.affects]


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


def q2_which_model(
    spans: Sequence[Span],
    missing_segments: Optional[Sequence[MissingSegment]] = None,
) -> Answer:
    """gen_ai.request.model, provider.name, agent.version from the inference span."""
    inferences = _all(spans, "inference")
    affecting = _affecting(missing_segments, "Q2")
    known = [s for s in inferences if s.get("gen_ai.request.model")]
    evidence = tuple(s.span_id for s in known)
    descriptions = list(dict.fromkeys(
        f"{s.get('gen_ai.request.model')} ({s.get('gen_ai.provider.name', 'unknown provider')}); "
        f"agent version {s.get('gen_ai.agent.version', 'unknown version')}"
        for s in known
    ))
    incomplete = len(known) != len(inferences) or any(
        not s.get("gen_ai.provider.name") or not s.get("gen_ai.agent.version")
        for s in known
    )
    gap = None
    if affecting:
        gap = NamedGap(
            party="; ".join(dict.fromkeys(m.party for m in affecting)),
            data_class="; ".join(dict.fromkeys(m.data_class for m in affecting)),
            note="; ".join(m.note for m in affecting if m.note),
        )
    elif incomplete or not known:
        gap = NamedGap("model provider / agent runtime",
                       "inference spans with model, provider and agent version")
    value = " | ".join(descriptions) if known else "no inference span recording the model was found"
    if gap:
        value += ". The model picture is incomplete; see the named gap."
    return Answer(
        "Q2", "Which model and version?",
        (Classification.PARTIAL if gap else Classification.ANSWERED_DIRECT)
        if known else Classification.UNANSWERED_UNAVAILABLE,
        value, evidence, gap,
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
    acting = [s for s in spans if s.operation_name in ("execute_tool", "downstream")]
    recorded = [s for s in acting if s.get("auth.subject")]
    missing = [s.span_id for s in acting if not s.get("auth.subject")]
    subjects = sorted({s.get("auth.subject") for s in recorded})
    agents = sorted({s.get("dcfp.agent.id") or s.get("gen_ai.agent.id")
                     for s in recorded
                     if s.get("dcfp.agent.id") or s.get("gen_ai.agent.id")})
    gap = None
    if missing or not recorded:
        gap = NamedGap(
            "identity provider / executing service",
            "auth subject / service principal on tool and downstream spans",
            "unidentified acting spans: " + ", ".join(missing) if missing else "no acting identity records",
        )
    value = (
        f"thin attribution: recorded actions ran under {subjects} via agent {agents}. "
        "This establishes the recorded acting identity, not that the principal directed it."
        if recorded else "no auth subject was recorded on the acting spans"
    )
    return Answer(
        "Q4", "Whose identity acted?",
        (Classification.PARTIAL if gap else Classification.ANSWERED_DIRECT)
        if recorded else Classification.UNANSWERED_UNAVAILABLE,
        value, tuple(s.span_id for s in recorded), gap,
    )


def q5_auto_approved(spans: Sequence[Span]) -> Answer:
    """Require a positive, complete approval record on an execution (A.5 Q5).

    This reference accepts inline records on tool calls. An unlinked approval
    elsewhere is not evidence that the recorded execution was approved.
    """
    fields = ("required", "mode", "decision", "actor", "policy_id", "policy_version")
    calls = _all(spans, "execute_tool")
    approvals = []
    missing = []
    for span in calls:
        values = {key: span.get("dcfp.approval." + key) for key in fields}
        complete = (
            isinstance(values["required"], bool)
            and values["mode"] in ("auto", "automatic", "manual", "human")
            and values["decision"] in ("approved", "denied")
            and all(isinstance(values[k], str) and values[k].strip()
                    for k in ("actor", "policy_id", "policy_version"))
        )
        if complete:
            approvals.append((span, values))
        else:
            missing.append(span.span_id)
    gap = None
    if missing or not calls:
        gap = NamedGap(
            "agent runtime / approval service",
            "dcfp.approval.* records (required, mode, decision, actor, policy id and version)",
            "complete inline approval records required for: " + (", ".join(missing) or "executions"),
        )
    if approvals:
        value = "; ".join(
            f"{span.span_id}: " + ", ".join(f"{k}={v!r}" for k, v in values.items())
            for span, values in approvals
        )
    else:
        value = ("no complete dcfp.approval.* record is present on the decision-to-execution "
                 "edge. Absence is NOT read as auto-approval; the approval "
                 "instrumentation has not been shown to be complete.")
    return Answer(
        "Q5", "What was auto-approved without human review?",
        (Classification.PARTIAL if gap else Classification.ANSWERED_DIRECT)
        if approvals else Classification.UNANSWERED_UNAVAILABLE,
        value, tuple(span.span_id for span, _ in approvals), gap,
    )


def q6_context_ingested(
    spans: Sequence[Span],
    missing_segments: Optional[Sequence[MissingSegment]] = None,
) -> Answer:
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

    affecting = _affecting(missing_segments, "Q6")
    if sources:
        note = " An injected instruction was present in ingested content." if injected else ""
        if affecting:
            seg = affecting[0]
            return Answer(
                qid="Q6",
                question="What context was ingested, and when?",
                classification=Classification.PARTIAL,
                value=(
                    f"ingested from {sorted(set(sources))}.{note} Context from an "
                    f"uncaptured segment is unavailable ({seg.data_class}; party: "
                    f"{seg.party})."
                ),
                evidence=tuple(dict.fromkeys(evidence)),
                gap=NamedGap(party=seg.party, data_class=seg.data_class,
                             note=seg.note),
            )
        return Answer(
            qid="Q6",
            question="What context was ingested, and when?",
            classification=Classification.ANSWERED_DIRECT,
            value=f"ingested from {sorted(set(sources))}.{note}",
            evidence=tuple(dict.fromkeys(evidence)),
        )
    if affecting:
        seg = affecting[0]
        return Answer(
            qid="Q6",
            question="What context was ingested, and when?",
            classification=Classification.UNANSWERED_UNAVAILABLE,
            value="the ingested context lies in an uncaptured segment",
            gap=NamedGap(party=seg.party, data_class=seg.data_class, note=seg.note),
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
    spans: Sequence[Span],
    certificates: Optional[Dict[str, Dict]] = None,
    missing_segments: Optional[Sequence[MissingSegment]] = None,
) -> List[Answer]:
    """Resolve Q1 to Q7 in order (companion A.5).

    Declared missing segments (companion C.2/C.3) let the resolvers classify a
    question as partial where they hold some but not all of its evidence.
    """
    return [
        q1_who_set_the_goal(spans),
        q2_which_model(spans, missing_segments),
        q3_tools_exposed(spans, certificates),
        q4_whose_identity(spans),
        q5_auto_approved(spans),
        q6_context_ingested(spans, missing_segments),
        q7_what_ran_downstream(spans),
    ]
