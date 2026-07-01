"""Tests for loading an episode from a JSON trace file (companion A.2, D.4)."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from tfa.cli import main
from tfa.ingest import load_trace
from tfa.report import analyse, render_report
from tfa.synth import build_episode

EXAMPLE_TRACE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "examples", "synthetic_trace.json"
)


class TestLoadExampleTrace(unittest.TestCase):
    def test_round_trip_reproduces_the_synthetic_episode(self):
        loaded = load_trace(EXAMPLE_TRACE)
        from_file = analyse(loaded)
        built_in = analyse(build_episode())
        # Same spans, seed and anchors: identical chain head and identical report.
        self.assertEqual(from_file.chain.head, built_in.chain.head)
        self.assertEqual(render_report(from_file), render_report(built_in))

    def test_loaded_episode_verifies_and_finds_the_subversion(self):
        analysis = analyse(load_trace(EXAMPLE_TRACE))
        self.assertTrue(analysis.verification.ok)
        from tfa.capability import boundary_subversions
        subs = boundary_subversions(analysis.capability_checks)
        self.assertEqual([c.span_id for c in subs], ["span-tool-emailsend"])


class TestLoadHandWrittenTrace(unittest.TestCase):
    def _write(self, obj) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        self.addCleanup(os.remove, path)
        return path

    def test_minimal_two_span_trace_loads_and_verifies(self):
        trace = {
            "trace_id": "t-min",
            "conversation_id": "c-min",
            "spans": [
                {
                    "trace_id": "t-min", "span_id": "s0", "parent_span_id": None,
                    "operation_name": "invoke_agent",
                    "start_time": 1000, "end_time": 1100, "capture_index": 0,
                    "attributes": {
                        "gen_ai.conversation.id": "c-min",
                        "gen_ai.agent.id": "agent-x",
                        "gen_ai.input.messages": [{"role": "user", "content": "go"}],
                        "dcfp.principal.id": "user@x.example",
                        "auth.subject": "user@x.example",
                    },
                },
                {
                    "trace_id": "t-min", "span_id": "s1", "parent_span_id": "s0",
                    "operation_name": "inference",
                    "start_time": 1200, "end_time": 1300, "capture_index": 1,
                    "attributes": {
                        "gen_ai.request.model": "examplelm-1",
                        "gen_ai.provider.name": "ExampleAI",
                        "gen_ai.agent.id": "agent-x",
                    },
                },
            ],
        }
        ep = load_trace(self._write(trace))
        self.assertEqual(len(ep.spans), 2)
        self.assertEqual(ep.anchor_indices, (1,))   # defaults to the final head
        analysis = analyse(ep)
        self.assertTrue(analysis.verification.ok)

    def test_spans_ordered_by_capture_index(self):
        trace = {
            "spans": [
                {"trace_id": "t", "span_id": "b", "operation_name": "inference",
                 "start_time": 2, "end_time": 3, "capture_index": 1,
                 "attributes": {}},
                {"trace_id": "t", "span_id": "a", "operation_name": "invoke_agent",
                 "start_time": 0, "end_time": 1, "capture_index": 0,
                 "attributes": {}},
            ]
        }
        ep = load_trace(self._write(trace))
        self.assertEqual([s.span_id for s in ep.spans], ["a", "b"])

    def test_empty_spans_rejected(self):
        with self.assertRaises(ValueError):
            load_trace(self._write({"spans": []}))

    def test_missing_required_field_rejected(self):
        trace = {"spans": [{"trace_id": "t", "span_id": "s0"}]}
        with self.assertRaises(ValueError):
            load_trace(self._write(trace))


class TestCliTrace(unittest.TestCase):
    def test_cli_runs_a_loaded_trace(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--trace", EXAMPLE_TRACE, "--format", "json"])
        self.assertEqual(rc, 0)

    def test_cli_tamper_on_loaded_trace_fails_closed(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--trace", EXAMPLE_TRACE, "--tamper", "5"])
        self.assertEqual(rc, 1)

    def test_cli_missing_trace_file_reports_error(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = main(["--trace", "/no/such/trace.json"])
        self.assertEqual(rc, 2)
        self.assertIn("could not load trace", err.getvalue())


if __name__ == "__main__":
    unittest.main()
