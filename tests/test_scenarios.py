"""Tests for the two worked-case episodes (companion C.1, C.2, C.3).

The cases contrast on the single variable the companion argues is decisive - the
number of providers. These tests pin the behaviour that carries the argument:

- the single-provider case reconstructs and verifies, and its residual gap is
  *not* the cross-provider join (it does not degrade Q2/Q6);
- the cross-provider case declares the uncaptured analysis segment as a missing
  segment, so Q2 and Q6 fall to partial and name the party that holds the
  evidence, rather than guessing across the boundary.

Also covers the missing-segment field round-tripping through the JSON loader and
surfacing in the report and the CLI JSON summary.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest

from tfa.capability import boundary_subversions
from tfa.cli import main
from tfa.ingest import load_trace
from tfa.questions import Classification
from tfa.report import analyse, render_report
from tfa.scenarios import (
    build_cross_provider_episode,
    build_single_provider_episode,
)


class TestSingleProviderEpisode(unittest.TestCase):
    def setUp(self):
        self.ep = build_single_provider_episode()
        self.analysis = analyse(self.ep)
        self.answers = {a.qid: a for a in self.analysis.answers}

    def test_reconstructs_and_verifies(self):
        self.assertTrue(self.analysis.verification.ok)

    def test_q2_model_resolves_directly(self):
        a = self.answers["Q2"]
        self.assertEqual(a.classification, Classification.ANSWERED_DIRECT)
        self.assertIn("exec-llm-1", a.value)

    def test_no_boundary_subversion_offence_is_in_the_aggregate(self):
        # Every call is within the account's own broad grant, so the scope check
        # finds nothing; the offence lives in the aggregate and the intent.
        self.assertEqual(boundary_subversions(self.analysis.capability_checks), [])

    def test_residual_gap_is_not_the_cross_provider_join(self):
        # The single-provider case still declares a residual gap, but it must not
        # bear on Q2/Q6 - that is the contrast with the cross-provider case.
        self.assertEqual(len(self.ep.missing_segments), 1)
        seg = self.ep.missing_segments[0]
        self.assertNotIn("Q2", seg.affects)
        self.assertNotIn("Q6", seg.affects)
        self.assertNotEqual(self.answers["Q2"].classification, Classification.PARTIAL)


class TestCrossProviderEpisode(unittest.TestCase):
    def setUp(self):
        self.ep = build_cross_provider_episode()
        self.analysis = analyse(self.ep)
        self.answers = {a.qid: a for a in self.analysis.answers}

    def test_reconstructs_and_verifies(self):
        self.assertTrue(self.analysis.verification.ok)

    def test_missing_segment_declares_the_uncaptured_analysis_party(self):
        self.assertEqual(len(self.ep.missing_segments), 1)
        seg = self.ep.missing_segments[0]
        self.assertEqual(seg.affects, ("Q2", "Q6"))
        self.assertIn("Provider-B", seg.party)
        # It is a declared segment, not a guess: it states what shows it existed.
        self.assertTrue(seg.evidence)

    def test_q2_falls_to_partial_and_names_the_party(self):
        a = self.answers["Q2"]
        self.assertEqual(a.classification, Classification.PARTIAL)
        self.assertIsNotNone(a.gap)
        self.assertIn("Provider-B", a.gap.party)

    def test_q6_falls_to_partial_and_names_the_party(self):
        a = self.answers["Q6"]
        self.assertEqual(a.classification, Classification.PARTIAL)
        self.assertIsNotNone(a.gap)
        self.assertIn("Provider-B", a.gap.party)

    def test_report_renders_the_missing_segment_section(self):
        report = render_report(self.analysis)
        self.assertIn("MISSING SEGMENTS", report)
        self.assertIn("provider-b-analysis", report)


class TestMissingSegmentRoundTrip(unittest.TestCase):
    """A trace file carrying missing_segments loads and drives Q2/Q6 to partial."""

    def _write(self, obj) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        self.addCleanup(os.remove, path)
        return path

    def test_missing_segments_load_and_affect_questions(self):
        trace = {
            "trace_id": "t-ms",
            "conversation_id": "c-ms",
            "spans": [
                {
                    "trace_id": "t-ms", "span_id": "s0", "parent_span_id": None,
                    "operation_name": "invoke_agent",
                    "start_time": 1000, "end_time": 1100, "capture_index": 0,
                    "attributes": {
                        "gen_ai.conversation.id": "c-ms",
                        "gen_ai.agent.id": "agent-x",
                        "gen_ai.input.messages": [{"role": "user", "content": "go"}],
                        "dcfp.principal.id": "user@x.example",
                        "auth.subject": "user@x.example",
                    },
                },
                {
                    "trace_id": "t-ms", "span_id": "s1", "parent_span_id": "s0",
                    "operation_name": "retrieval",
                    "start_time": 1200, "end_time": 1300, "capture_index": 1,
                    "attributes": {
                        "gen_ai.data_source.id": "seized://tool",
                        "gen_ai.agent.id": "agent-x",
                    },
                },
            ],
            "missing_segments": [
                {
                    "segment_id": "provider-b",
                    "party": "Provider-B",
                    "data_class": "analysis inference spans",
                    "affects": ["Q2", "Q6"],
                    "evidence": "seized tooling references a second provider",
                    "note": "request by data class",
                },
            ],
        }
        ep = load_trace(self._write(trace))
        self.assertEqual(len(ep.missing_segments), 1)
        self.assertEqual(ep.missing_segments[0].affects, ("Q2", "Q6"))

        analysis = analyse(ep)
        answers = {a.qid: a for a in analysis.answers}
        # No inference span at all: Q2 is unanswered-unavailable, and it names
        # the party that holds the model evidence.
        self.assertEqual(
            answers["Q2"].classification, Classification.UNANSWERED_UNAVAILABLE)
        self.assertIsNotNone(answers["Q2"].gap)
        self.assertIn("Provider-B", answers["Q2"].gap.party)
        # A retrieval source is present, so Q6 is partial rather than empty.
        self.assertEqual(answers["Q6"].classification, Classification.PARTIAL)


class TestScenarioCli(unittest.TestCase):
    def _run_json(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(argv)
        return rc, buf.getvalue()

    def test_cross_scenario_runs_and_reports_missing_segments(self):
        rc, out = self._run_json(["--scenario", "cross", "--format", "json"])
        self.assertEqual(rc, 0)
        summary = json.loads(out)
        seg_ids = [s["segment_id"] for s in summary["missing_segments"]]
        self.assertIn("provider-b-analysis", seg_ids)

    def test_single_scenario_runs(self):
        rc, _ = self._run_json(["--scenario", "single", "--format", "json"])
        self.assertEqual(rc, 0)

    def test_default_scenario_is_the_synthetic_episode(self):
        rc_default, out_default = self._run_json(["--format", "json"])
        rc_named, out_named = self._run_json(
            ["--scenario", "synthetic", "--format", "json"])
        self.assertEqual(rc_default, 0)
        self.assertEqual(out_default, out_named)


if __name__ == "__main__":
    unittest.main()
