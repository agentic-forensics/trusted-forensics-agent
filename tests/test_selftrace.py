"""Tests for self-instrumentation (companion D.3).

Covers acceptance criterion 8: the tool emits its own actions as DCFP spans,
hash-chained and witnessed by the same W - in a separate chain from the episode
evidence.
"""

import unittest

from tfa.integrity import verify_chain
from tfa.selftrace import SelfTracer
from tfa.synth import default_witness, witness_episode, build_episode


class TestSelfTrace(unittest.TestCase):
    def test_actions_form_a_witnessed_chain(self):
        witness = default_witness()
        tracer = SelfTracer(witness)
        tracer.record_action("ingest", inputs=[1, 2], output={"spans": 7})
        tracer.record_action("build_graph", output={"edges": 9})
        anchor = tracer.witness_head()

        receipts = list(tracer.chain.store)
        result = verify_chain(tracer.spans, receipts, [anchor], witness, tracer.seed)
        self.assertTrue(result.ok, result.messages)

    def test_actions_are_linked_in_sequence(self):
        tracer = SelfTracer(default_witness())
        a = tracer.record_action("one")
        b = tracer.record_action("two")
        self.assertIsNone(a.parent_span_id)
        self.assertEqual(b.parent_span_id, a.span_id)

    def test_selftrace_is_a_separate_chain_from_the_episode(self):
        witness = default_witness()
        ep = build_episode()
        ep_chain, _ = witness_episode(ep, witness)

        tracer = SelfTracer(witness)
        tracer.record_action("ingest", output={"spans": len(ep.spans)})

        # Same witness, but distinct seeds and therefore distinct chains.
        self.assertNotEqual(tracer.seed, ep.seed)
        self.assertNotEqual(tracer.chain.head, ep_chain.head)

    def test_witnessing_nothing_raises(self):
        tracer = SelfTracer(default_witness())
        with self.assertRaises(ValueError):
            tracer.witness_head()

    def test_same_witness_verifies_both_chains(self):
        witness = default_witness()
        ep = build_episode()
        ep_chain, ep_anchors = witness_episode(ep, witness)
        tracer = SelfTracer(witness)
        tracer.record_action("report", output={"done": True})
        self_anchor = tracer.witness_head()

        ep_ok = verify_chain(
            ep.spans, list(ep_chain.store), ep_anchors, witness, ep.seed
        ).ok
        self_ok = verify_chain(
            tracer.spans, list(tracer.chain.store), [self_anchor], witness, tracer.seed
        ).ok
        self.assertTrue(ep_ok)
        self.assertTrue(self_ok)


if __name__ == "__main__":
    unittest.main()
