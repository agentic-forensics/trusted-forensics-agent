"""Tests for the five-plane projection (companion A.4)."""

import unittest

from tfa.model import Plane
from tfa.planes import Projection, project
from tfa.synth import build_episode


class TestProjection(unittest.TestCase):
    def setUp(self):
        self.ep = build_episode()
        self.by_id = {s.span_id: s for s in self.ep.spans}

    def _planes(self, span_id):
        return project(self.by_id[span_id])

    def test_create_agent_is_dna(self):
        self.assertEqual(self._planes("span-create-agent"), {Plane.DNA})

    def test_invoke_agent_is_brain_and_ears_mouth(self):
        self.assertEqual(
            self._planes("span-invoke-agent"), {Plane.BRAIN, Plane.EARS_MOUTH}
        )

    def test_retrieval_is_memory(self):
        self.assertEqual(self._planes("span-retrieval-contract"), {Plane.MEMORY})

    def test_inference_is_brain_and_ears_mouth(self):
        self.assertEqual(
            self._planes("span-inference-1"), {Plane.BRAIN, Plane.EARS_MOUTH}
        )

    def test_tool_calls_are_hands(self):
        self.assertEqual(self._planes("span-tool-emailread"), {Plane.HANDS})
        self.assertEqual(self._planes("span-tool-emailsend"), {Plane.HANDS})

    def test_downstream_is_hands(self):
        self.assertEqual(self._planes("span-egress-http"), {Plane.HANDS})

    def test_every_plane_is_furnished(self):
        proj = Projection(self.ep.spans)
        for plane in Plane:
            self.assertTrue(proj.spans_in(plane), f"{plane} has no spans")


if __name__ == "__main__":
    unittest.main()
