"""Tests for completeness in three senses (companion A.2).

Covers acceptance criterion 6: completeness classified in all three senses with
a per-question label for each of Q1 to Q7.
"""

import unittest

from tfa.completeness import assess
from tfa.questions import resolve_all
from tfa.synth import build_episode


class TestCompleteness(unittest.TestCase):
    def setUp(self):
        self.ep = build_episode()
        self.answers = resolve_all(self.ep.spans, self.ep.capability_certificates)

    def test_schema_complete_because_every_question_is_resolved(self):
        # Q5 is unanswered but recorded as a named gap, so it is resolved.
        result = assess(self.answers, chain_verified=True)
        self.assertTrue(result.schema_complete)
        self.assertEqual(result.unresolved, ())

    def test_per_question_labels_cover_all_seven(self):
        result = assess(self.answers, chain_verified=True)
        self.assertEqual(
            set(result.per_question), {"Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"}
        )

    def test_named_gaps_include_q5(self):
        result = assess(self.answers, chain_verified=True)
        qids = [qid for qid, _ in result.named_gaps]
        self.assertIn("Q5", qids)

    def test_evidential_completeness_requires_verified_chain(self):
        verified = assess(self.answers, chain_verified=True)
        unverified = assess(self.answers, chain_verified=False)
        self.assertTrue(verified.evidential_complete)
        self.assertFalse(unverified.evidential_complete)

    def test_case_sufficiency_is_represented_not_asserted(self):
        result = assess(self.answers, chain_verified=True)
        self.assertIn("Not assessed", result.case_sufficiency)


if __name__ == "__main__":
    unittest.main()
