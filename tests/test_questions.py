"""Tests for the seven-question resolvers (companion A.5).

Covers acceptance criterion 3: Q1 to Q7 are answered, and Q5 (its closing signal
omitted from the trace) is recorded as a named gap, not guessed.
"""

import unittest

from tfa.questions import Classification, resolve_all
from tfa.synth import build_episode


class TestResolvers(unittest.TestCase):
    def setUp(self):
        self.ep = build_episode()
        self.answers = {a.qid: a for a in resolve_all(
            self.ep.spans, self.ep.capability_certificates)}

    def test_all_seven_present_and_ordered(self):
        self.assertEqual(
            [a.qid for a in resolve_all(self.ep.spans)],
            ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"],
        )

    def test_q1_principal_goal(self):
        a = self.answers["Q1"]
        self.assertEqual(a.classification, Classification.ANSWERED_DIRECT)
        self.assertIn("alice@acme.example", a.value)

    def test_q2_model_and_version(self):
        a = self.answers["Q2"]
        self.assertEqual(a.classification, Classification.ANSWERED_DIRECT)
        self.assertIn("examplelm-2-medium", a.value)
        self.assertIn("1.4.2", a.value)

    def test_q3_declared_vs_observed(self):
        a = self.answers["Q3"]
        self.assertEqual(a.classification, Classification.ANSWERED_DIRECT)
        self.assertIn("email.send", a.value)

    def test_q4_thin_attribution_is_flagged_as_such(self):
        a = self.answers["Q4"]
        self.assertEqual(a.classification, Classification.ANSWERED_DIRECT)
        self.assertIn("thin attribution", a.value)

    def test_q5_is_a_named_gap_not_auto_approval(self):
        a = self.answers["Q5"]
        self.assertEqual(a.classification, Classification.UNANSWERED_UNAVAILABLE)
        self.assertIsNotNone(a.gap)
        self.assertIn("dcfp.approval", a.gap.data_class)
        self.assertIn("NOT read as auto-approval", a.value)
        self.assertTrue(a.resolved)   # a named gap is a resolved question

    def test_q6_context_flags_injection(self):
        a = self.answers["Q6"]
        self.assertEqual(a.classification, Classification.ANSWERED_DIRECT)
        self.assertIn("injected", a.value.lower())

    def test_q7_intent_versus_actual(self):
        a = self.answers["Q7"]
        self.assertEqual(a.classification, Classification.ANSWERED_DIRECT)
        self.assertIn("dcfp.effect.observed", a.value)
        self.assertIn("mailbox-backup.example", a.value)


if __name__ == "__main__":
    unittest.main()
