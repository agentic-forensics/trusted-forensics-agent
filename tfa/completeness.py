"""Completeness in three senses (companion A.2).

Completeness is not a single Boolean. Three distinct senses are assessed:

- Schema completeness: every question is resolved, meaning either answerable from
  present, integrity-verified spans, or recorded as a named gap. Formally
  Schema-complete(S, G) iff for all i in 1..7: resolved(Q_i, S, G).
- Evidential completeness: each answer is supported by adequate, integrity-
  verified evidence.
- Case sufficiency: the evidence is enough for the specific proposition and legal
  standard at issue. This is out of scope to decide (companion A.2); it is
  represented here, not assessed.

Each question carries a per-question classification (questions.Classification),
never a bare true/false.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .questions import Answer, Classification, NamedGap


_ANSWERED = (
    Classification.ANSWERED_DIRECT,
    Classification.ANSWERED_INFERRED,
    Classification.PARTIAL,
)


@dataclass(frozen=True)
class CompletenessAssessment:
    """The three-sense completeness assessment (companion A.2)."""

    schema_complete: bool
    unresolved: Tuple[str, ...]                     # qids left unresolved (should be none)
    evidential_complete: bool
    evidential_by_question: Dict[str, bool]         # qid -> adequately evidenced
    case_sufficiency: str                           # represented, not assessed
    per_question: Dict[str, str]                    # qid -> classification text
    named_gaps: Tuple[Tuple[str, NamedGap], ...]    # (qid, gap)

    def summary(self) -> str:
        gaps = ", ".join(qid for qid, _ in self.named_gaps) or "none"
        return (
            f"schema-complete={self.schema_complete}; "
            f"evidential-complete={self.evidential_complete}; "
            f"named gaps: {gaps}; case sufficiency: not assessed (out of scope)"
        )


def assess(
    answers: Sequence[Answer], chain_verified: bool
) -> CompletenessAssessment:
    """Assess completeness in three senses over the seven answers.

    chain_verified says whether the integrity layer confirmed the spans the
    answers rest on. Evidential completeness requires both adequate evidence and
    that integrity verification held: integrity is a separate property from
    completeness (companion A.2, A.6), and an answer resting on unverified spans
    is not evidentially complete even if it is schema-resolved.
    """
    unresolved = tuple(a.qid for a in answers if not a.resolved)
    schema_complete = not unresolved

    evidential_by_question: Dict[str, bool] = {}
    for a in answers:
        if a.classification in _ANSWERED:
            evidential_by_question[a.qid] = bool(a.evidence) and chain_verified
    evidential_complete = bool(evidential_by_question) and all(
        evidential_by_question.values()
    )

    per_question = {a.qid: a.classification.value for a in answers}
    named_gaps = tuple(
        (a.qid, a.gap) for a in answers if a.gap is not None
    )

    case_sufficiency = (
        "Not assessed. Case sufficiency depends on the specific proposition and "
        "legal standard at issue and is out of scope for this reference "
        "(companion A.2)."
    )

    return CompletenessAssessment(
        schema_complete=schema_complete,
        unresolved=unresolved,
        evidential_complete=evidential_complete,
        evidential_by_question=evidential_by_question,
        case_sufficiency=case_sufficiency,
        per_question=per_question,
        named_gaps=named_gaps,
    )
