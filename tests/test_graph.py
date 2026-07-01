"""Tests for the delegation-chain graph (companion A.2, A.3).

Covers acceptance criterion 2: typed, evidence-backed edges; the agent-to-model
edge is an invocation, not a decision; no delegation edge rests on parentage
alone.
"""

import unittest

from tfa.graph import (
    DELEGATION_EDGE_TYPES,
    DelegationEvidenceError,
    Graph,
    build_graph,
)
from tfa.model import (
    Confidence,
    Edge,
    EdgeType,
    Node,
    NodeType,
    Observation,
)
from tfa.synth import build_episode


class TestBuildGraph(unittest.TestCase):
    def setUp(self):
        self.ep = build_episode()
        self.graph = build_graph(self.ep.spans)

    def test_core_nodes_present(self):
        types = {n.node_type for n in self.graph.nodes.values()}
        self.assertIn(NodeType.PRINCIPAL, types)
        self.assertIn(NodeType.AGENT, types)
        self.assertIn(NodeType.MODEL, types)
        self.assertIn(NodeType.TOOL, types)
        self.assertIn(NodeType.RETRIEVAL_SOURCE, types)
        self.assertIn(NodeType.TARGET, types)

    def test_agent_to_model_edge_is_invocation_not_decision(self):
        invoked = self.graph.edges_of_type(EdgeType.INVOKED)
        agent_model = [
            e for e in invoked
            if e.source.startswith("agent:") and e.target.startswith("model:")
        ]
        self.assertEqual(len(agent_model), 1)
        # There is deliberately no "decision" edge type in the model.
        self.assertFalse(any(et.value == "decision" for et in EdgeType))

    def test_instructed_edge_is_evidence_backed(self):
        instructed = self.graph.edges_of_type(EdgeType.INSTRUCTED)
        self.assertEqual(len(instructed), 1)
        edge = instructed[0]
        self.assertTrue(edge.source.startswith("principal:"))
        self.assertTrue(edge.target.startswith("agent:"))
        self.assertTrue(edge.source_artefact)          # cites a span
        self.assertEqual(edge.observation, Observation.OBSERVED)

    def test_authenticated_as_edge_present(self):
        auth = self.graph.edges_of_type(EdgeType.AUTHENTICATED_AS)
        self.assertTrue(auth)

    def test_produced_effect_on_links_tool_to_external_target(self):
        effects = self.graph.edges_of_type(EdgeType.PRODUCED_EFFECT_ON)
        self.assertTrue(effects)
        self.assertTrue(any("mailbox-backup.example" in e.target for e in effects))


class TestDelegationDiscipline(unittest.TestCase):
    def _two_nodes(self):
        g = Graph()
        g.add_node(Node("principal:p", NodeType.PRINCIPAL, "p"))
        g.add_node(Node("agent:a", NodeType.AGENT, "a"))
        return g

    def test_delegation_edge_via_add_edge_is_refused(self):
        g = self._two_nodes()
        edge = Edge("principal:p", "agent:a", EdgeType.INSTRUCTED,
                    source_artefact=("s1",))
        with self.assertRaises(DelegationEvidenceError):
            g.add_edge(edge)

    def test_delegation_edge_without_evidence_is_refused(self):
        g = self._two_nodes()
        edge = Edge("principal:p", "agent:a", EdgeType.INSTRUCTED,
                    source_artefact=("s1",))
        with self.assertRaises(DelegationEvidenceError):
            g.add_delegation_edge(edge, evidence_keys=[])

    def test_delegation_edge_without_source_artefact_is_refused(self):
        g = self._two_nodes()
        edge = Edge("principal:p", "agent:a", EdgeType.INSTRUCTED)
        with self.assertRaises(DelegationEvidenceError):
            g.add_delegation_edge(edge, evidence_keys=["auth.subject"])

    def test_delegation_edge_with_evidence_is_accepted(self):
        g = self._two_nodes()
        edge = Edge("principal:p", "agent:a", EdgeType.INSTRUCTED,
                    source_artefact=("s1",), confidence=Confidence.HIGH)
        g.add_delegation_edge(edge, evidence_keys=["auth.subject"])
        self.assertEqual(len(g.edges), 1)

    def test_delegation_edge_types_cover_the_authority_relations(self):
        self.assertEqual(
            DELEGATION_EDGE_TYPES,
            {
                EdgeType.INSTRUCTED,
                EdgeType.AUTHORISED,
                EdgeType.AUTHENTICATED_AS,
                EdgeType.APPROVED,
            },
        )


class TestAcyclicProjection(unittest.TestCase):
    def test_projection_is_acyclic_and_reports_removed_edges(self):
        ep = build_episode()
        graph = build_graph(ep.spans)
        kept, removed = graph.acyclic_projection()
        # instructed (principal->agent) and authenticated-as (agent->principal)
        # form a logical cycle; the projection must break it and report it.
        self.assertTrue(removed)

        # Confirm the kept edges form a DAG.
        adjacency = {}
        for e in kept:
            adjacency.setdefault(e.source, set()).add(e.target)

        def has_cycle():
            colour = {}

            def visit(node):
                colour[node] = "grey"
                for nxt in adjacency.get(node, ()):
                    c = colour.get(nxt)
                    if c == "grey":
                        return True
                    if c is None and visit(nxt):
                        return True
                colour[node] = "black"
                return False

            return any(visit(n) for n in list(adjacency) if colour.get(n) is None)

        self.assertFalse(has_cycle())


if __name__ == "__main__":
    unittest.main()
