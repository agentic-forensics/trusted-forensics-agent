"""The five-plane projection pi (companion A.4).

pi : S -> 2^P maps each span to the plane(s) it furnishes evidence for. A span
may project to more than one plane. The planes are projections of the same
witnessed span stream, not separate stores (companion A.2, A.4).

The mapping follows the A.4 table, driven by the attributes a span actually
carries rather than by its operation name alone, so that a span furnishes a
plane only where it holds the evidence for it:

- Brain (Reasoning and Decisions): inference and invoke_agent spans, and any
  span carrying reasoning or completion content.
- DNA (Identity and Configuration): create_agent spans, resource attributes and
  capability-certificate references (agent id/name/version, system prompt,
  declared tool set, service.*).
- Memory (Knowledge and Memory): retrieval spans and data-source references
  (data_source.id, retrieved documents, memory-store identifiers).
- Ears and Mouth (Inputs and Outputs / Conversation): spans carrying the actual
  input or output messages. gen_ai.conversation.id is treated as a correlation
  key for grouping, not on its own as furnishing this plane.
- Hands (Actions and Effects): execute_tool spans and their downstream child
  spans (tool name, arguments, results, HTTP/DB/network effects).
"""

from __future__ import annotations

from typing import Dict, List, Set

from .model import Plane, Span


def _has_any(span: Span, keys) -> bool:
    return any(k in span.attributes for k in keys)


def project(span: Span) -> Set[Plane]:
    """Return the set of planes a single span furnishes evidence for (A.4)."""
    planes: Set[Plane] = set()
    op = span.operation_name

    # Brain: reasoning and decisions.
    if op in ("inference", "invoke_agent") or _has_any(
        span, ("gen_ai.completion.reasoning", "dcfp.intent.action")
    ):
        planes.add(Plane.BRAIN)

    # DNA: identity and configuration. Driven by configuration content
    # (system prompt, declared tool set, capability cert, service identity, agent
    # name), not by an agent id/version stamp that many spans carry only for
    # correlation. Q2's "and version" is read directly from the inference span
    # regardless of plane.
    if op == "create_agent" or _has_any(
        span,
        (
            "gen_ai.system_instructions",
            "gen_ai.request.tools",
            "gen_ai.agent.name",
            "dcfp.capability.cert_id",
            "service.name",
        ),
    ):
        planes.add(Plane.DNA)

    # Memory: knowledge and memory.
    if op == "retrieval" or _has_any(
        span, ("gen_ai.data_source.id", "gen_ai.retrieval.documents")
    ):
        planes.add(Plane.MEMORY)

    # Ears and Mouth: the actual inputs and outputs.
    if _has_any(span, ("gen_ai.input.messages", "gen_ai.output.messages")):
        planes.add(Plane.EARS_MOUTH)

    # Hands: actions and effects.
    if op in ("execute_tool", "downstream") or _has_any(
        span,
        ("gen_ai.tool.name", "dcfp.effect.observed", "http.request.method"),
    ):
        planes.add(Plane.HANDS)

    return planes


class Projection:
    """The projection pi over a span set (companion A.4)."""

    def __init__(self, spans: List[Span]) -> None:
        self.by_span: Dict[str, Set[Plane]] = {}
        self.by_plane: Dict[Plane, List[str]] = {p: [] for p in Plane}
        for span in spans:
            planes = project(span)
            self.by_span[span.span_id] = planes
            for plane in planes:
                self.by_plane[plane].append(span.span_id)

    def planes_of(self, span_id: str) -> Set[Plane]:
        return self.by_span.get(span_id, set())

    def spans_in(self, plane: Plane) -> List[str]:
        return list(self.by_plane.get(plane, []))
