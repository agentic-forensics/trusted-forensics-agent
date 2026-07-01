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

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .model import PartialOrder, Span


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
