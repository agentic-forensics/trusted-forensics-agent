"""Ingest a span set and build the partial order (companion A.2).

Order is recovered from span parentage, trace links, message identifiers and
correlated timestamps, not from wall-clock time alone (companion A.2, A.3). This
module therefore never sorts the whole episode by timestamp: doing so would
impose the single global clock the model forbids.

For the reference episode, precedence is asserted from:

- span parentage (a parent strictly precedes its children), and
- explicit effect links (dcfp.effect.observed on a downstream span points back to
  the tool call whose effect it records).

Timestamps are retained as correlation evidence on the spans but are not used to
totally order the episode. Parentage and links establish technical correlation
only; they do not, on their own, establish delegation (that is graph.py's
concern).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .model import PartialOrder, Span

# Fallback chain seed for a loaded trace that does not carry its own. Any fixed
# value keeps that trace's chain reproducible; the value itself is not secret.
_DEFAULT_LOADED_SEED = b"tfa-dcfp-loaded-trace-seed-v1"


@dataclass
class Ingested:
    """The result of ingesting a span set."""

    partial_order: PartialOrder
    by_id: Dict[str, Span]
    roots: List[str] = field(default_factory=list)
    children: Dict[str, List[str]] = field(default_factory=dict)

    def by_call_id(self, call_id: str) -> Optional[Span]:
        """Return the execute_tool span with the given gen_ai.tool.call.id."""
        for span in self.by_id.values():
            if span.get("gen_ai.tool.call.id") == call_id:
                return span
        return None


def ingest(spans: List[Span]) -> Ingested:
    """Build the partial order and correlation indices from a span set."""
    order = PartialOrder()
    by_id: Dict[str, Span] = {}
    for span in spans:
        by_id[span.span_id] = span
        order.add_span(span)

    children: Dict[str, List[str]] = {sid: [] for sid in by_id}
    roots: List[str] = []

    # Parentage: a parent strictly precedes each of its children.
    for span in spans:
        parent = span.parent_span_id
        if parent is None:
            roots.append(span.span_id)
            continue
        if parent not in by_id:
            # A dangling parent reference is itself evidence (a lost span). Treat
            # the child as a root for ordering, but do not invent the parent.
            roots.append(span.span_id)
            continue
        children[parent].append(span.span_id)
        order.add_precedence(parent, span.span_id)

    # Effect links: a downstream span recording dcfp.effect.observed follows the
    # tool call it observed, even where parentage did not already imply it.
    for span in spans:
        observed_call = span.get("dcfp.effect.observed")
        if not observed_call:
            continue
        tool_span = None
        for candidate in spans:
            if candidate.get("gen_ai.tool.call.id") == observed_call:
                tool_span = candidate
                break
        if tool_span is not None and tool_span.span_id != span.span_id:
            if not order.precedes(tool_span.span_id, span.span_id):
                order.add_precedence(tool_span.span_id, span.span_id)

    return Ingested(
        partial_order=order,
        by_id=by_id,
        roots=roots,
        children=children,
    )


def _span_from_record(raw: Dict) -> Span:
    """Build a Span from one record of a trace file (companion A.2)."""
    required = ("trace_id", "span_id", "operation_name", "start_time", "end_time")
    missing = [k for k in required if k not in raw]
    if missing:
        raise ValueError(
            f"span record is missing required field(s): {', '.join(missing)}"
        )
    return Span(
        trace_id=raw["trace_id"],
        span_id=raw["span_id"],
        parent_span_id=raw.get("parent_span_id"),
        operation_name=raw["operation_name"],
        start_time=int(raw["start_time"]),
        end_time=int(raw["end_time"]),
        attributes=dict(raw.get("attributes", {})),
        events=tuple(raw.get("events", ())),
        capture_index=raw.get("capture_index"),
    )


def load_trace(path: str):
    """Load an episode from a JSON trace file (companion A.2, D.4).

    The file uses the shape of examples/synthetic_trace.json: a top-level object
    with "spans" (a list of span records), and optionally "trace_id",
    "conversation_id", "seed_hex", "capability_certificates" and
    "anchor_indices". This is the supported route for running the model over your
    own collected evidence: shape it into this form and load it, exactly as a
    hand-written fixture (briefing scope).

    Returns a synth.Episode so the rest of the pipeline consumes it unchanged.
    Spans are ordered by capture_index where present, so the hash chain runs over
    the recorded emission order. Where no seed or anchor points are given, a fixed
    seed and a single anchor on the final head are used.
    """
    # Local import avoids any import-time coupling between ingest and synth.
    from .synth import Episode

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("spans")
    if not records:
        raise ValueError(f"trace file {path!r} contains no spans")

    spans = [_span_from_record(r) for r in records]
    if all(s.capture_index is not None for s in spans):
        spans.sort(key=lambda s: s.capture_index)

    seed_hex = data.get("seed_hex")
    seed = bytes.fromhex(seed_hex) if seed_hex else _DEFAULT_LOADED_SEED

    certificates = data.get("capability_certificates", {})

    # Anchor points: use the file's if valid, otherwise anchor the final head.
    n = len(spans)
    given = data.get("anchor_indices")
    if given:
        anchor_indices = tuple(i for i in given if 0 <= i < n)
    else:
        anchor_indices = ()
    if not anchor_indices:
        anchor_indices = (n - 1,)

    return Episode(
        spans=spans,
        capability_certificates=certificates,
        seed=seed,
        trace_id=data.get("trace_id", spans[0].trace_id),
        conversation_id=data.get("conversation_id", ""),
        anchor_indices=anchor_indices,
    )
