"""Tests for ingest and the partial order (companion A.2)."""

import dataclasses
import unittest

from tfa.ingest import ingest
from tfa.synth import build_episode


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.ep = build_episode()
        self.ing = ingest(self.ep.spans)

    def test_roots_are_the_parentless_spans(self):
        self.assertEqual(
            set(self.ing.roots), {"span-create-agent", "span-invoke-agent"}
        )

    def test_parent_precedes_child(self):
        po = self.ing.partial_order
        self.assertTrue(po.precedes("span-invoke-agent", "span-tool-emailread"))
        self.assertTrue(po.precedes("span-inference-1", "span-tool-emailsend"))
        # transitive
        self.assertTrue(po.precedes("span-invoke-agent", "span-egress-http"))

    def test_siblings_are_concurrent(self):
        # Both are children of the invoke_agent span; nothing orders them.
        po = self.ing.partial_order
        self.assertTrue(
            po.concurrent("span-tool-emailread", "span-retrieval-contract")
        )

    def test_effect_link_orders_egress_after_tool(self):
        po = self.ing.partial_order
        self.assertTrue(po.precedes("span-tool-emailsend", "span-egress-http"))

    def test_no_global_clock_linear_extension_is_deterministic(self):
        a = ingest(self.ep.spans).partial_order.linear_extension()
        b = ingest(self.ep.spans).partial_order.linear_extension()
        self.assertEqual([s.span_id for s in a], [s.span_id for s in b])

    def test_by_call_id(self):
        span = self.ing.by_call_id("call-send-1")
        self.assertIsNotNone(span)
        self.assertEqual(span.span_id, "span-tool-emailsend")

    def test_duplicate_span_ids_rejected_instead_of_overwriting_evidence(self):
        original = self.ep.spans[0]
        replacement = dataclasses.replace(original, operation_name="execute_tool")
        with self.assertRaisesRegex(ValueError, "duplicate span_id"):
            ingest(self.ep.spans + [replacement])

    def test_duplicate_span_ids_across_traces_are_rejected(self):
        # Correlation currently uses span_id as its key, so a second trace must
        # not silently replace the first record even when trace_ids differ.
        original = self.ep.spans[0]
        other_trace = dataclasses.replace(original, trace_id="another-trace")
        with self.assertRaisesRegex(ValueError, "duplicate span_id"):
            ingest([original, other_trace])


if __name__ == "__main__":
    unittest.main()
