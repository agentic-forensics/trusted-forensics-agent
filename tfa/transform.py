"""The transformation-record ledger (companion D.3).

For every object the agent derives - a parsed span, a correlation, a
reconstructed edge, a score - the ledger records: the inputs consumed by hash,
the version of the code that produced it, the rule or method applied, any model
invocation involved, any human modification, and the hash of the output. This is
what lets a court test not merely what the agent concluded but how it reached the
conclusion from the preserved material (companion D.3).

One rule holds without exception (companion D.3, briefing section 5): where a
model assists the reconstruction, an association it suggests is a lead to be
verified against the evidence, and is never allowed to become an evidential edge
on its own authority. A lead is recorded here with promoted=False and carries no
weight in G unless and until it is independently verified; promote_lead requires
independent evidence and is the only way a lead may change status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

from .canon import canonical_json, digest_hex


@dataclass(frozen=True)
class TransformationRecord:
    """One entry in the transformation-record ledger (companion D.3)."""

    output_id: str
    rule: str                               # the rule or method applied
    code_version: str
    input_hashes: Tuple[str, ...]           # inputs consumed, by hash
    output_hash: str                        # hash of the derived output
    model_invocation: Optional[str] = None  # any model invocation involved
    human_modification: Optional[str] = None
    # A model-suggested association is a lead, never an edge, until verified.
    is_lead: bool = False
    promoted: bool = False
    note: str = ""

    def as_record(self) -> dict:
        return {
            "output_id": self.output_id,
            "rule": self.rule,
            "code_version": self.code_version,
            "input_hashes": list(self.input_hashes),
            "output_hash": self.output_hash,
            "model_invocation": self.model_invocation,
            "human_modification": self.human_modification,
            "is_lead": self.is_lead,
            "promoted": self.promoted,
            "note": self.note,
        }


def hash_input(obj: Any) -> str:
    """Hash an input object by value for the ledger (companion D.3)."""
    return digest_hex(canonical_json(obj))


class TransformationLedger:
    """An append-only ledger of transformation records (companion D.3)."""

    def __init__(self, code_version: str) -> None:
        self._code_version = code_version
        self._records: List[TransformationRecord] = []

    def record(
        self,
        output_id: str,
        rule: str,
        inputs: Sequence[Any],
        output: Any,
        model_invocation: Optional[str] = None,
        human_modification: Optional[str] = None,
        note: str = "",
    ) -> TransformationRecord:
        """Record a derived object, hashing its inputs and output by value."""
        rec = TransformationRecord(
            output_id=output_id,
            rule=rule,
            code_version=self._code_version,
            input_hashes=tuple(hash_input(i) for i in inputs),
            output_hash=hash_input(output),
            model_invocation=model_invocation,
            human_modification=human_modification,
            is_lead=False,
            promoted=False,
            note=note,
        )
        self._records.append(rec)
        return rec

    def record_lead(
        self,
        output_id: str,
        rule: str,
        inputs: Sequence[Any],
        suggestion: Any,
        model_invocation: str,
        note: str = "",
    ) -> TransformationRecord:
        """Record a model-suggested association as an unverified lead.

        The lead is not an evidential edge and carries no weight in G. It can
        only change status through promote_lead, which requires independent
        evidence (companion D.3).
        """
        rec = TransformationRecord(
            output_id=output_id,
            rule=rule,
            code_version=self._code_version,
            input_hashes=tuple(hash_input(i) for i in inputs),
            output_hash=hash_input(suggestion),
            model_invocation=model_invocation,
            human_modification=None,
            is_lead=True,
            promoted=False,
            note=note or "model-suggested association: a lead to be verified, "
                         "never an evidential edge on its own authority.",
        )
        self._records.append(rec)
        return rec

    def promote_lead(
        self, output_id: str, verifying_evidence: Sequence[Any]
    ) -> TransformationRecord:
        """Promote a lead to verified, but only against independent evidence.

        Refuses to promote without verifying evidence: a lead never becomes an
        edge on the model's authority alone (companion D.3).
        """
        if not verifying_evidence:
            raise ValueError(
                "a model-suggested lead cannot be promoted without independent "
                "verifying evidence (companion D.3)"
            )
        for i, rec in enumerate(self._records):
            if rec.output_id == output_id and rec.is_lead:
                promoted = TransformationRecord(
                    output_id=rec.output_id,
                    rule=rec.rule,
                    code_version=rec.code_version,
                    input_hashes=rec.input_hashes
                    + tuple(hash_input(e) for e in verifying_evidence),
                    output_hash=rec.output_hash,
                    model_invocation=rec.model_invocation,
                    human_modification=rec.human_modification,
                    is_lead=True,
                    promoted=True,
                    note="lead verified against independent evidence and promoted.",
                )
                self._records[i] = promoted
                return promoted
        raise KeyError(f"no unpromoted lead with output_id {output_id!r}")

    def leads(self) -> List[TransformationRecord]:
        return [r for r in self._records if r.is_lead]

    def unverified_leads(self) -> List[TransformationRecord]:
        return [r for r in self._records if r.is_lead and not r.promoted]

    def records(self) -> List[dict]:
        return [r.as_record() for r in self._records]

    def __len__(self) -> int:
        return len(self._records)
