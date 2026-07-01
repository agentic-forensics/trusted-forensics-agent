"""Span, plane, node and edge types, and the partial-order container.

Implements the data model of companion A.2 (the recorded spans S, the
delegation-chain graph G) and A.4 (the five-plane projection). This module holds
type definitions only; population happens in ingest.py, planes.py and graph.py.

Design notes that follow the model:

- Spans are partially ordered, never globally time-ordered (companion A.2). The
  PartialOrder container records a precedence relation explicitly; it does not
  sort by wall-clock time.
- Each span carries a capture_index recording its position in the captured
  emission stream. The hash chain (integrity.py) runs over that emission order,
  which is a separate property from the reconstructed partial order of the
  episode.
- Edges are typed by the relation they assert and annotated with their source
  artefact, integrity status, confidence and whether they were observed or
  inferred (companion A.2, A.3). Span parentage establishes technical
  correlation only; it never, on its own, establishes delegation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


# --------------------------------------------------------------------------- #
# OTel GenAI operation names (companion A.1, A.4)
# --------------------------------------------------------------------------- #

class Operation(str, Enum):
    """gen_ai.operation.name values the model reconstructs from."""

    INFERENCE = "inference"
    EXECUTE_TOOL = "execute_tool"
    CREATE_AGENT = "create_agent"
    INVOKE_AGENT = "invoke_agent"
    RETRIEVAL = "retrieval"
    # A generic downstream span (HTTP/DB/network) hanging off an execute_tool
    # span, recording an actual effect (companion A.4 Hands plane).
    DOWNSTREAM = "downstream"


# --------------------------------------------------------------------------- #
# The five planes (companion A.4)
# --------------------------------------------------------------------------- #

class Plane(str, Enum):
    """The five-plane Agent Artefact Taxonomy (companion A.4)."""

    BRAIN = "reasoning_and_decisions"        # Reasoning and Decisions
    DNA = "identity_and_configuration"       # Identity and Configuration
    MEMORY = "knowledge_and_memory"          # Knowledge and Memory
    EARS_MOUTH = "inputs_and_outputs"        # Inputs and Outputs / Conversation
    HANDS = "actions_and_effects"            # Actions and Effects


# --------------------------------------------------------------------------- #
# Span (companion A.2 "the recorded spans S")
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Span:
    """An OpenTelemetry-shaped GenAI span.

    Attributes use the flat dotted OTel keys (for example
    "gen_ai.request.model") so the model stays a profile of the conventions
    rather than a new schema (companion A.1, A.7). Timestamps are unix
    nanoseconds (integers) to keep canonicalisation deterministic.

    capture_index is the span's position in the captured emission stream. It is
    deliberately excluded from canonicalisation (see canon.py): the hash chain
    binds position through chaining order, not through a content field.
    """

    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: int                     # unix nanoseconds
    end_time: int                       # unix nanoseconds
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: Sequence[Dict[str, Any]] = field(default_factory=tuple)
    capture_index: Optional[int] = None

    def content_dict(self) -> Dict[str, Any]:
        """The content of the span for canonicalisation.

        Excludes capture_index. Everything that is part of the recorded fact of
        the span is included; the stream position is not.
        """
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "attributes": dict(self.attributes),
            "events": [dict(e) for e in self.events],
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Convenience accessor for an OTel attribute."""
        return self.attributes.get(key, default)


# --------------------------------------------------------------------------- #
# Nodes and edges of the delegation-chain graph G (companion A.2, A.3)
# --------------------------------------------------------------------------- #

class NodeType(str, Enum):
    """The actors and resources that are vertices of G (companion A.2, A.3).

    Companion A.2 names the human principal, the agent(s), the model(s), the
    tools and the target systems; A.3/A.4 and Q6 additionally require retrieval
    and memory sources, so they are first-class node types here.
    """

    PRINCIPAL = "principal"
    AGENT = "agent"
    MODEL = "model"
    TOOL = "tool"
    TARGET = "target"
    RETRIEVAL_SOURCE = "retrieval_source"


@dataclass(frozen=True)
class Node:
    """A vertex of G."""

    node_id: str
    node_type: NodeType
    label: str = ""


class EdgeType(str, Enum):
    """The relation an edge asserts (companion A.2).

    The agent-to-model relation is an INVOKED / inference operation, never "the
    decision" (companion A.2). The relations that assert delegation or authority
    (INSTRUCTED, AUTHORISED, AUTHENTICATED_AS, APPROVED) must rest on identity,
    authorisation, approval or policy evidence, never on span parentage alone.
    """

    INSTRUCTED = "instructed"
    INVOKED = "invoked"
    AUTHORISED = "authorised"
    AUTHENTICATED_AS = "authenticated_as"
    SUPPLIED_CONTEXT_TO = "supplied_context_to"
    RETRIEVED_FROM = "retrieved_from"
    EXECUTED_ON = "executed_on"
    PRODUCED_EFFECT_ON = "produced_effect_on"
    APPROVED = "approved"


class IntegrityStatus(str, Enum):
    """Integrity status carried by an edge or finding."""

    VERIFIED = "verified"            # rests on integrity-verified spans
    UNVERIFIED = "unverified"        # not yet checked against the chain
    BROKEN = "broken"               # rests on a span whose integrity failed


class Confidence(str, Enum):
    """Confidence in an asserted edge. Deliberately coarse and declared."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Observation(str, Enum):
    """Whether the edge was directly observed or inferred (companion A.2)."""

    OBSERVED = "observed"
    INFERRED = "inferred"


@dataclass(frozen=True)
class Edge:
    """A typed, evidence-backed edge of G (companion A.2, A.3).

    The annotations are not optional decoration: source, integrity_status,
    confidence and observation are part of what makes an edge defensible. A
    delegation edge (see EdgeType) constructed without identity/authorisation/
    approval/policy evidence is a modelling error and graph.py rejects it.
    """

    source: str                      # source node_id
    target: str                      # target node_id
    edge_type: EdgeType
    # The artefact the edge rests on: typically the span_id(s) and attribute(s).
    source_artefact: Tuple[str, ...] = ()
    integrity_status: IntegrityStatus = IntegrityStatus.UNVERIFIED
    confidence: Confidence = Confidence.MEDIUM
    observation: Observation = Observation.INFERRED
    note: str = ""


# --------------------------------------------------------------------------- #
# Partial order over spans (companion A.2 "partially ordered, not globally
# time-ordered")
# --------------------------------------------------------------------------- #

class PartialOrder:
    """A partial order over spans, recovered from evidence, not from a clock.

    Precedence is asserted explicitly from span parentage, trace links, message
    identifiers and correlated timestamps (companion A.2, A.3). This container
    deliberately offers no "sort the whole episode by timestamp" operation: that
    would impose a global clock the model forbids. It can produce a linear
    extension for display, but a linear extension is one consistent ordering,
    not the order.
    """

    def __init__(self) -> None:
        self._spans: Dict[str, Span] = {}
        # precedence[a] is the set of spans that come strictly before a.
        self._predecessors: Dict[str, set] = {}

    def add_span(self, span: Span) -> None:
        self._spans[span.span_id] = span
        self._predecessors.setdefault(span.span_id, set())

    def add_precedence(self, before_span_id: str, after_span_id: str) -> None:
        """Assert that before strictly precedes after."""
        if before_span_id not in self._spans or after_span_id not in self._spans:
            raise KeyError("both spans must be added before asserting precedence")
        if before_span_id == after_span_id:
            raise ValueError("a span cannot precede itself")
        self._predecessors[after_span_id].add(before_span_id)

    def spans(self) -> List[Span]:
        return list(self._spans.values())

    def predecessors(self, span_id: str) -> set:
        return set(self._predecessors.get(span_id, set()))

    def precedes(self, a_span_id: str, b_span_id: str) -> bool:
        """True if a precedes b through the transitive closure of precedence."""
        seen: set = set()
        stack = list(self._predecessors.get(b_span_id, set()))
        while stack:
            current = stack.pop()
            if current == a_span_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self._predecessors.get(current, set()))
        return False

    def concurrent(self, a_span_id: str, b_span_id: str) -> bool:
        """True if neither span precedes the other (they are unordered)."""
        if a_span_id == b_span_id:
            return False
        return not self.precedes(a_span_id, b_span_id) and not self.precedes(
            b_span_id, a_span_id
        )

    def linear_extension(self) -> List[Span]:
        """One ordering consistent with the partial order, for display only.

        Ties are broken by span_id so the extension is deterministic. This is
        not "the order of the episode"; callers must not treat it as such.
        """
        result: List[str] = []
        placed: set = set()
        remaining = set(self._spans.keys())
        while remaining:
            ready = sorted(
                sid
                for sid in remaining
                if self._predecessors.get(sid, set()) <= placed
            )
            if not ready:
                # A cycle in the asserted precedence. The model permits logical
                # cycles in G but a precedence relation used for ordering must be
                # acyclic; surface it rather than loop forever.
                raise ValueError("precedence relation contains a cycle")
            for sid in ready:
                result.append(sid)
                placed.add(sid)
                remaining.discard(sid)
        return [self._spans[sid] for sid in result]
