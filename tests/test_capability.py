"""Tests for the capability check (companion A.2, A.3).

Covers acceptance criterion 5: the out-of-scope external email.send is flagged
as boundary subversion, checked across tool, operation, arguments, target and
purpose together, not by tool name alone.
"""

import unittest

from tfa.capability import (
    boundary_subversions,
    check_episode,
    parse_certificate,
)
from tfa.synth import build_episode


class TestCapability(unittest.TestCase):
    def setUp(self):
        self.ep = build_episode()
        self.checks = check_episode(self.ep.capability_certificates, self.ep.spans)
        self.by_span = {c.span_id: c for c in self.checks}

    def test_in_scope_read_passes(self):
        read = self.by_span["span-tool-emailread"]
        self.assertTrue(read.in_scope)
        self.assertEqual(read.failed_dimensions, ())

    def test_external_send_is_boundary_subversion(self):
        send = self.by_span["span-tool-emailsend"]
        self.assertFalse(send.in_scope)
        self.assertTrue(send.boundary_subversion)
        # It fails on the target and on the recipient-domain argument together,
        # not on the tool name (email.send is itself permitted).
        self.assertIn("target", send.failed_dimensions)
        self.assertIn("arguments", send.failed_dimensions)
        self.assertNotIn("tool", send.failed_dimensions)

    def test_boundary_subversions_collects_the_send(self):
        subs = boundary_subversions(self.checks)
        self.assertEqual([c.span_id for c in subs], ["span-tool-emailsend"])

    def test_tool_name_match_alone_is_insufficient(self):
        # email.send matches by tool name yet is out of scope: the check is at
        # call granularity (companion A.2, A.3).
        send = self.by_span["span-tool-emailsend"]
        self.assertEqual(send.tool, "email.send")
        self.assertFalse(send.in_scope)


class TestParseCertificate(unittest.TestCase):
    def test_parse_roundtrip_fields(self):
        ep = build_episode()
        data = list(ep.capability_certificates.values())[0]
        cert = parse_certificate(data)
        self.assertEqual(cert.agent_id, data["agent_id"])
        self.assertEqual(len(cert.permitted), len(data["permitted"]))
        self.assertIsNotNone(cert.permission_for("email.send"))
        self.assertIsNone(cert.permission_for("shell.exec"))


if __name__ == "__main__":
    unittest.main()
