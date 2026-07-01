"""Tests for the end-to-end analysis and report (companion B Phase 7, D.2).

Covers acceptance criterion 9: an admissibility-readiness report listing
supporting evidence, named gaps and stated limitations, making no guarantee of
admission. Also checks determinism against the committed example report and that
the CLI fails closed on tamper.
"""

import contextlib
import io
import os
import unittest

from tfa.capability import boundary_subversions
from tfa.cli import main
from tfa.integrity import verify_chain
from tfa.report import analyse, render_report
from tfa.synth import build_episode, default_witness

EXAMPLE_REPORT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "examples", "synthetic_report.txt"
)


class TestAnalyse(unittest.TestCase):
    def setUp(self):
        self.analysis = analyse(build_episode())

    def test_integrity_verifies(self):
        self.assertTrue(self.analysis.verification.ok)

    def test_boundary_subversion_present(self):
        subs = boundary_subversions(self.analysis.capability_checks)
        self.assertEqual([c.span_id for c in subs], ["span-tool-emailsend"])

    def test_schema_complete_with_q5_gap(self):
        self.assertTrue(self.analysis.completeness.schema_complete)
        qids = [qid for qid, _ in self.analysis.completeness.named_gaps]
        self.assertIn("Q5", qids)

    def test_exactly_one_unverified_lead(self):
        self.assertEqual(len(self.analysis.unverified_leads), 1)

    def test_ledger_and_selftrace_populated(self):
        self.assertGreater(len(self.analysis.ledger), 0)
        self.assertGreater(len(self.analysis.tracer.spans), 0)

    def test_selftrace_anchor_verifies_with_same_witness(self):
        # The self-trace is witnessed by the same W as the episode.
        witness = default_witness()
        analysis = analyse(build_episode(), witness)
        result = verify_chain(
            analysis.tracer.spans,
            list(analysis.tracer.chain.store),
            [analysis.selftrace_anchor],
            witness,
            analysis.tracer.seed,
        )
        self.assertTrue(result.ok, result.messages)


class TestRenderReport(unittest.TestCase):
    def setUp(self):
        self.text = render_report(analyse(build_episode()))

    def test_is_a_readiness_report_not_a_guarantee(self):
        self.assertIn("ADMISSIBILITY-READINESS REPORT", self.text)
        self.assertIn("not a guarantee", self.text)

    def test_lists_named_gaps(self):
        self.assertIn("NAMED GAP", self.text)

    def test_lists_boundary_subversion(self):
        self.assertIn("boundary subversion", self.text)

    def test_lists_unverified_leads(self):
        self.assertIn("UNVERIFIED LEADS (not evidence)", self.text)

    def test_lists_stated_limitations(self):
        self.assertIn("STATED LIMITATIONS", self.text)
        self.assertIn("development stand-in", self.text)

    def test_deterministic_matches_committed_example(self):
        with open(EXAMPLE_REPORT, encoding="utf-8") as f:
            expected = f.read()
        self.assertEqual(self.text, expected)


class TestCli(unittest.TestCase):
    def test_normal_run_exits_zero(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--format", "json"])
        self.assertEqual(rc, 0)

    def test_tamper_fails_closed(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--tamper", "3"])
        self.assertEqual(rc, 1)
        self.assertIn("tampering detected", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
