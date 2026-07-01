"""The delegation-chain graph G = (V, E) (companion A.2, A.3).

Nodes are the actors and resources of the episode; edges are typed by the
relation they assert and annotated with their source artefact, integrity status,
confidence and whether they were observed or inferred (companion A.2).

Two rules from the model are enforced here, not merely documented:

1. Span parentage establishes technical correlation only. A delegation or
   authority edge (instructed, authorised, authenticated-as, approved) is
   asserted only from identity, authorisation, approval or policy evidence,
   never from nesting alone. add_delegation_edge refuses an edge that cites no
   such evidence.

2. The agent-to-model edge is an invocation / inference operation, never "the
   decision" (companion A.2). There is no "decision" edge type; the relation is
   EdgeType.INVOKED.

G may contain logical cycles; acyclic_projection derives a bounded acyclic view,
treating acyclicity as a property of the projection, not an assumption about the
system (companion A.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .model import (
    Confidence,
    Edge,
    EdgeType,
    IntegrityStatus,
    Node,
    NodeType,
    Observation,
    Span,
)

# Edge types that assert delegation or authority and therefore require identity/
# authorisation/approval/policy evidence, never parentage alone (companion A.2).
DELEGATION_EDGE_TYPES = frozenset(
    {
        EdgeType.INSTRUCTED,
        EdgeType.AUTHORISED,
        EdgeType.AUTHENTICATED_AS,
        EdgeType.APPROVED,
    }
)


class DelegationEvidenceError(ValueError):
    """Raised when a delegation edge is asserted without qualifying evidence."""


@dataclass
class Graph:
    """The reconstructed delegation-chain graph."""

    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        self.nodes.setdefault(node.node_id, node)

    def add_edge(self, edge: Edge) -> None:
        """Add a non-delegation (technical/correlation) edge.

        For delegation or authority relations use add_delegation_edge, which
        enforces the evidence rule.
        """
        if edge.edge_type in DELEGATION_EDGE_TYPES:
            raise DelegationEvidenceError(
                f"{edge.edge_type.value} is a delegation/authority edge; "
                "use add_delegation_edge with explicit evidence"
            )
        self._require_endpoints(edge)
        self.edges.append(edge)

    def add_delegation_edge(self, edge: Edge, evidence_keys: Sequence[str]) -> None:
        """Add a delegation/authority edge, requiring qualifying evidence.

        evidence_keys names the identity/authorisation/approval/policy
        attributes the edge rests on (for example auth.subject,
        dcfp.principal.id, dcfp.approval.decision). The edge must cite at least
        one such attribute and must carry its source artefact; an edge derived
        from parentage alone is refused (companion A.2, A.3).
        """
        if edge.edge_type not in DELEGATION_EDGE_TYPES:
            raise DelegationEvidenceError(
                f"{edge.edge_type.value} is not a delegation/authority edge"
            )
        if not evidence_keys:
            raise DelegationEvidenceError(
                f"delegation edge {edge.edge_type.value} requires identity/"
                "authorisation/approval/policy evidence, not parentage alone"
            )
        if not edge.source_artefact:
            raise DelegationEvidenceError(
                "delegation edge must cite its source artefact"
            )
        self._require_endpoints(edge)
        self.edges.append(edge)

    def _require_endpoints(self, edge: Edge) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise KeyError("both endpoints must be added as nodes before the edge")

    def edges_of_type(self, edge_type: EdgeType) -> List[Edge]:
        return [e for e in self.edges if e.edge_type == edge_type]

    # --- bounded acyclic projection (companion A.2) -------------------------- #

    def acyclic_projection(self) -> Tuple[List[Edge], List[Edge]]:
        """Return (kept_edges, removed_edges) forming a DAG over the nodes.

        Edges are considered in insertion order; any edge that would close a
        cycle in the projection is set aside and reported. Acyclicity is a
        property of this projection, not a claim about the system.
        """
        kept: List[Edge] = []
        removed: List[Edge] = []
        adjacency: Dict[str, set] = {nid: set() for nid in self.nodes}

        def reachable(start: str, goal: str) -> bool:
            seen: set = set()
            stack = [start]
            while stack:
                cur = stack.pop()
                if cur == goal:
                    return True
                if cur in seen:
                    continue
                seen.add(cur)
                stack.extend(adjacency.get(cur, set()))
            return False

        for edge in self.edges:
            # Adding source -> target closes a cycle iff target already reaches
            # source.
            if reachable(edge.target, edge.source):
                removed.append(edge)
                continue
            kept.append(edge)
            adjacency[edge.source].add(edge.target)
        return kept, removed


# --------------------------------------------------------------------------- #
# Reconstruction from spans
# --------------------------------------------------------------------------- #

def _node_id(node_type: NodeType, key: str) -> str:
    return f"{node_type.value}:{key}"


def build_graph(spans: Sequence[Span]) -> Graph:
    """Reconstruct G from a span set (companion A.2, A.3).

    Delegation and authority edges are asserted only where identity/
    authorisation/approval/policy attributes are present. The agent-to-model
    edge is an invocation. Absence of an approval record does NOT produce an
    approved edge; it is left for questions.py to record as a named gap.
    """
    graph = Graph()

    # --- nodes ----------------------------------------------------------- #
    for span in spans:
        principal = span.get("dcfp.principal.id") or span.get("auth.subject")
        if principal:
            graph.add_node(
                Node(_node_id(NodeType.PRINCIPAL, principal), NodeType.PRINCIPAL, principal)
            )
        agent = span.get("gen_ai.agent.id") or span.get("dcfp.agent.id")
        if agent:
            graph.add_node(Node(_node_id(NodeType.AGENT, agent), NodeType.AGENT, agent))
        model = span.get("gen_ai.request.model")
        if model:
            graph.add_node(Node(_node_id(NodeType.MODEL, model), NodeType.MODEL, model))
        tool = span.get("gen_ai.tool.name")
        if tool:
            graph.add_node(Node(_node_id(NodeType.TOOL, tool), NodeType.TOOL, tool))
        source = span.get("gen_ai.data_source.id")
        if source:
            graph.add_node(
                Node(_node_id(NodeType.RETRIEVAL_SOURCE, source), NodeType.RETRIEVAL_SOURCE, source)
            )
        target = span.get("dcfp.tool.target") or span.get("dcfp.egress.recipient")
        if target:
            graph.add_node(Node(_node_id(NodeType.TARGET, target), NodeType.TARGET, target))

    # --- edges ----------------------------------------------------------- #
    for span in spans:
        op = span.operation_name
        agent = span.get("gen_ai.agent.id") or span.get("dcfp.agent.id")

        if op == "invoke_agent":
            principal = span.get("dcfp.principal.id") or span.get("auth.subject")
            if principal and agent:
                # instructed: a delegation edge, resting on principal identity
                # (auth) plus the goal message, not on parentage.
                graph.add_delegation_edge(
                    Edge(
                        source=_node_id(NodeType.PRINCIPAL, principal),
                        target=_node_id(NodeType.AGENT, agent),
                        edge_type=EdgeType.INSTRUCTED,
                        source_artefact=(span.span_id,),
                        integrity_status=IntegrityStatus.UNVERIFIED,
                        confidence=Confidence.HIGH,
                        observation=Observation.OBSERVED,
                        note="principal set the goal under the conversation",
                    ),
                    evidence_keys=[
                        k for k in ("auth.subject", "dcfp.principal.id")
                        if k in span.attributes
                    ],
                )

        elif op == "inference":
            model = span.get("gen_ai.request.model")
            if agent and model:
                # invoked / inference operation, NOT "the decision".
                graph.add_edge(
                    Edge(
                        source=_node_id(NodeType.AGENT, agent),
                        target=_node_id(NodeType.MODEL, model),
                        edge_type=EdgeType.INVOKED,
                        source_artefact=(span.span_id,),
                        observation=Observation.OBSERVED,
                        confidence=Confidence.HIGH,
                        note="agent invoked the model (inference operation)",
                    )
                )

        elif op == "retrieval":
            source = span.get("gen_ai.data_source.id")
            if agent and source:
                graph.add_edge(
                    Edge(
                        source=_node_id(NodeType.AGENT, agent),
                        target=_node_id(NodeType.RETRIEVAL_SOURCE, source),
                        edge_type=EdgeType.RETRIEVED_FROM,
                        source_artefact=(span.span_id,),
                        observation=Observation.OBSERVED,
                        confidence=Confidence.HIGH,
                    )
                )
                graph.add_edge(
                    Edge(
                        source=_node_id(NodeType.RETRIEVAL_SOURCE, source),
                        target=_node_id(NodeType.AGENT, agent),
                        edge_type=EdgeType.SUPPLIED_CONTEXT_TO,
                        source_artefact=(span.span_id,),
                        observation=Observation.OBSERVED,
                        confidence=Confidence.MEDIUM,
                    )
                )

        elif op == "execute_tool":
            tool = span.get("gen_ai.tool.name")
            if agent and tool:
                graph.add_edge(
                    Edge(
                        source=_node_id(NodeType.AGENT, agent),
                        target=_node_id(NodeType.TOOL, tool),
                        edge_type=EdgeType.INVOKED,
                        source_artefact=(span.span_id,),
                        observation=Observation.OBSERVED,
                        confidence=Confidence.HIGH,
                        note="agent invoked the tool",
                    )
                )
            # authenticated-as: the agent acted under a principal identity (thin
            # attribution, Q4). A delegation/authority edge resting on the auth
            # subject, not on parentage.
            principal = span.get("auth.subject") or span.get("dcfp.principal.id")
            if agent and principal:
                graph.add_delegation_edge(
                    Edge(
                        source=_node_id(NodeType.AGENT, agent),
                        target=_node_id(NodeType.PRINCIPAL, principal),
                        edge_type=EdgeType.AUTHENTICATED_AS,
                        source_artefact=(span.span_id,),
                        observation=Observation.OBSERVED,
                        confidence=Confidence.HIGH,
                        note="tool call ran under the principal's identity",
                    ),
                    evidence_keys=[
                        k for k in ("auth.subject", "dcfp.principal.id")
                        if k in span.attributes
                    ],
                )

        elif op == "downstream":
            # produced-effect-on: link the tool to the target it actually acted
            # on, via dcfp.effect.observed (Q7 actual).
            observed_call = span.get("dcfp.effect.observed")
            target = span.get("dcfp.egress.recipient") or span.get("server.address")
            tool_name = None
            for s in spans:
                if s.get("gen_ai.tool.call.id") == observed_call:
                    tool_name = s.get("gen_ai.tool.name")
                    break
            if tool_name and target:
                graph.add_node(Node(_node_id(NodeType.TARGET, target), NodeType.TARGET, target))
                graph.add_edge(
                    Edge(
                        source=_node_id(NodeType.TOOL, tool_name),
                        target=_node_id(NodeType.TARGET, target),
                        edge_type=EdgeType.PRODUCED_EFFECT_ON,
                        source_artefact=(span.span_id,),
                        observation=Observation.OBSERVED,
                        confidence=Confidence.HIGH,
                        note="observed downstream effect linked by dcfp.effect.observed",
                    )
                )

    return graph
