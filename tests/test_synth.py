"""Tests for the synthetic episode (companion D.4).

Confirms the P0 goal: a witnessed, tamper-evident span set, and that the
preconditions later phases rely on are present in the trace.
"""

import unittest

from tfa.integrity import verify_chain
from tfa.synth import (
    AGENT_ID,
    CERT_ID,
    CONFIDENTIAL_DOC,
    EXTERNAL_RECIPIENT,
    build_episode,
    default_witness,
    witness_episode,
)


class TestEpisodeStructure(unittest.TestCase):
    def setUp(self):
        self.ep = build_episode()

    def test_spans_have_contiguous_capture_indices(self):
        for i, s in enumerate(self.ep.spans):
            self.assertEqual(s.capture_index, i)

    def test_has_all_operation_types(self):
        ops = {s.operation_name for s in self.ep.spans}
        self.assertEqual(
            ops,
            {"create_agent", "invoke_agent", "execute_tool", "retrieval",
             "inference", "downstream"},
        )

    def test_capability_certificate_present(self):
        self.assertIn(CERT_ID, self.ep.capability_certificates)
        cert = self.ep.capability_certificates[CERT_ID]
        self.assertEqual(cert["agent_id"], AGENT_ID)

    def test_q5_closing_signal_is_absent(self):
        # The email.send span must carry no dcfp.approval.* attribute, so Q5
        # (auto-approval) becomes a named gap rather than being read as
        # auto-approval (companion A.5 Q5; acceptance criterion 3).
        send = self.ep.span_by_id("span-tool-emailsend")
        self.assertIsNotNone(send)
        approval_keys = [k for k in send.attributes if k.startswith("dcfp.approval")]
        self.assertEqual(approval_keys, [])

    def test_out_of_scope_send_precondition(self):
        # email.send goes to an external recipient; the cert permits internal
        # only (acceptance criterion 5).
        send = self.ep.span_by_id("span-tool-emailsend")
        self.assertEqual(send.get("dcfp.tool.target"), EXTERNAL_RECIPIENT)
        self.assertFalse(EXTERNAL_RECIPIENT.endswith("@acme.example"))
        self.assertIn(CONFIDENTIAL_DOC, send.get("gen_ai.tool.arguments")["attachments"])

    def test_effect_observed_links_tool_to_egress(self):
        egress = self.ep.span_by_id("span-egress-http")
        send = self.ep.span_by_id("span-tool-emailsend")
        self.assertEqual(
            egress.get("dcfp.effect.observed"), send.get("gen_ai.tool.call.id")
        )


class TestWitnessedEpisode(unittest.TestCase):
    def test_chain_and_anchors_verify(self):
        ep = build_episode()
        witness = default_witness()
        chain, anchors = witness_episode(ep, witness)
        self.assertEqual(len(chain.store), len(ep.spans))
        self.assertEqual(len(anchors), len(ep.anchor_indices))
        result = verify_chain(ep.spans, list(chain.store), anchors, witness, ep.seed)
        self.assertTrue(result.ok, result.messages)

    def test_deterministic_chain_head(self):
        ep1 = build_episode()
        chain1, _ = witness_episode(ep1)
        ep2 = build_episode()
        chain2, _ = witness_episode(ep2)
        self.assertEqual(chain1.head, chain2.head)


if __name__ == "__main__":
    unittest.main()
