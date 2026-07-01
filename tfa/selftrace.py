"""Self-instrumentation: the tool is forensic-by-design about itself (companion D.3).

A forensic agent investigating agents is itself an agent, and is subject to the
same audit-trail paradox and wrongful-attribution risk it exists to resolve. The
TFA must therefore emit every action it takes as DCFP spans, hash-chained and
witnessed by the same independent W, so its own conduct is reconstructable and
challengeable (companion D.3). An investigative tool that cannot satisfy the
integrity requirements it applies to others undermines the evidence it produces.

Design (recorded in the build notes): the tool's own conduct is kept in a
SEPARATE hash chain from the episode evidence, so the evidence chain is not
intermingled with the tool's activity, while BOTH are witnessed by the same W.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import __version__
from .canon import canonical_json, digest_hex
from .integrity import Anchor, HashChain, Witness
from .model import Span

SELFTRACE_SEED = b"tfa-dcfp-selftrace-seed-v1"
SELFTRACE_TRACE_ID = "tfa-selftrace-0001"

# Deterministic clock for the self-trace: a fixed base and a fixed step, so the
# self-trace is reproducible on every run (no wall-clock time).
_BASE_NS = 1_733_000_100_000_000_000
_STEP_NS = 1_000_000


def _summary(obj: Any) -> str:
    """A short, hashable summary of an input or output for the span record."""
    return digest_hex(canonical_json(obj))


class SelfTracer:
    """Emits the tool's own actions as witnessed DCFP spans (companion D.3)."""

    def __init__(
        self,
        witness: Witness,
        seed: bytes = SELFTRACE_SEED,
        trace_id: str = SELFTRACE_TRACE_ID,
    ) -> None:
        self.witness = witness
        self.chain = HashChain(seed)
        self.trace_id = trace_id
        self.seed = seed
        self.spans: List[Span] = []
        self._n = 0

    def record_action(
        self,
        action: str,
        inputs: Optional[Any] = None,
        output: Optional[Any] = None,
        note: str = "",
    ) -> Span:
        """Record one tool action as a DCFP span and extend the self-trace chain."""
        index = self._n
        start = _BASE_NS + index * _STEP_NS
        parent = f"tfa-act-{index - 1:04d}" if index > 0 else None
        attributes: Dict[str, Any] = {
            "gen_ai.operation.name": "dcfp.tfa.action",
            "dcfp.tfa.action": action,
            "dcfp.tfa.code_version": __version__,
        }
        if inputs is not None:
            attributes["dcfp.tfa.input_digest"] = _summary(inputs)
        if output is not None:
            attributes["dcfp.tfa.output_digest"] = _summary(output)
        if note:
            attributes["dcfp.tfa.note"] = note

        span = Span(
            trace_id=self.trace_id,
            span_id=f"tfa-act-{index:04d}",
            parent_span_id=parent,
            operation_name="dcfp.tfa.action",
            start_time=start,
            end_time=start + _STEP_NS // 2,
            attributes=attributes,
            capture_index=index,
        )
        self.chain.append(span)
        self.spans.append(span)
        self._n += 1
        return span

    def witness_head(self) -> Anchor:
        """Have the same W counter-sign the current self-trace chain head."""
        if not self.spans:
            raise ValueError("nothing to witness: no actions recorded")
        return self.witness.attest(len(self.spans) - 1, self.chain.head)
