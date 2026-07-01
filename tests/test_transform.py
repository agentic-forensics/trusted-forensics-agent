"""Tests for the transformation-record ledger (companion D.3).

Covers acceptance criterion 7: a ledger entry for every derived object, and one
model-suggested association that appears only as an unverified lead.
"""

import unittest

from tfa.transform import TransformationLedger, hash_input


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.ledger = TransformationLedger(code_version="0.0.1")

    def test_record_captures_input_and_output_hashes(self):
        rec = self.ledger.record(
            output_id="edge-1",
            rule="build_graph: agent invoked model",
            inputs=[{"span": "span-inference-1"}],
            output={"edge": "agent->model"},
        )
        self.assertEqual(rec.code_version, "0.0.1")
        self.assertEqual(len(rec.input_hashes), 1)
        self.assertEqual(rec.output_hash, hash_input({"edge": "agent->model"}))
        self.assertFalse(rec.is_lead)

    def test_model_suggestion_is_a_lead_not_an_edge(self):
        rec = self.ledger.record_lead(
            output_id="lead-1",
            rule="model-suggested correlation",
            inputs=[{"recipient": "external-archive@mailbox-backup.example"}],
            suggestion={"assoc": "recipient may be the principal's personal alias"},
            model_invocation="assistant-model:examplelm-2-medium",
        )
        self.assertTrue(rec.is_lead)
        self.assertFalse(rec.promoted)
        self.assertEqual(len(self.ledger.unverified_leads()), 1)

    def test_lead_cannot_be_promoted_without_evidence(self):
        self.ledger.record_lead(
            output_id="lead-1", rule="r", inputs=[{}], suggestion={},
            model_invocation="m",
        )
        with self.assertRaises(ValueError):
            self.ledger.promote_lead("lead-1", verifying_evidence=[])

    def test_lead_promoted_with_independent_evidence(self):
        self.ledger.record_lead(
            output_id="lead-1", rule="r", inputs=[{}], suggestion={},
            model_invocation="m",
        )
        promoted = self.ledger.promote_lead(
            "lead-1", verifying_evidence=[{"span": "span-corroborating"}]
        )
        self.assertTrue(promoted.promoted)
        self.assertEqual(len(self.ledger.unverified_leads()), 0)

    def test_promote_unknown_lead_raises(self):
        with self.assertRaises(KeyError):
            self.ledger.promote_lead("nope", verifying_evidence=[{"x": 1}])


if __name__ == "__main__":
    unittest.main()
