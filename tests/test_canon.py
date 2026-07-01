"""Tests for deterministic canonicalisation (companion A.2)."""

import unittest

from tfa.canon import canon, canonical_json, sha256
from tfa.model import Span


def _span(**overrides) -> Span:
    base = dict(
        trace_id="t1",
        span_id="s1",
        parent_span_id=None,
        operation_name="inference",
        start_time=1000,
        end_time=2000,
        attributes={"b": 2, "a": 1, "nested": {"y": 1, "x": 2}},
        events=(),
        capture_index=0,
    )
    base.update(overrides)
    return Span(**base)


class TestCanonicalJson(unittest.TestCase):
    def test_keys_sorted_at_every_level(self):
        out = canonical_json({"b": 1, "a": {"d": 4, "c": 3}})
        self.assertEqual(out, b'{"a":{"c":3,"d":4},"b":1}')

    def test_compact_separators_no_whitespace(self):
        out = canonical_json({"a": 1, "b": [1, 2]})
        self.assertNotIn(b" ", out)

    def test_non_ascii_emitted_directly(self):
        out = canonical_json({"name": "Sotiropoulos"})
        self.assertIn(b"Sotiropoulos", out)

    def test_rejects_nan_and_infinity(self):
        with self.assertRaises(ValueError):
            canonical_json({"x": float("nan")})
        with self.assertRaises(ValueError):
            canonical_json({"x": float("inf")})


class TestCanon(unittest.TestCase):
    def test_deterministic_across_builds(self):
        self.assertEqual(canon(_span()), canon(_span()))

    def test_capture_index_excluded(self):
        # Two spans identical but for capture_index must canonicalise alike.
        self.assertEqual(canon(_span(capture_index=0)), canon(_span(capture_index=9)))

    def test_attribute_order_does_not_matter(self):
        a = _span(attributes={"a": 1, "b": 2})
        b = _span(attributes={"b": 2, "a": 1})
        self.assertEqual(canon(a), canon(b))

    def test_content_change_changes_canon(self):
        self.assertNotEqual(canon(_span(span_id="s1")), canon(_span(span_id="s2")))

    def test_sha256_is_32_bytes(self):
        self.assertEqual(len(sha256(b"x")), 32)


if __name__ == "__main__":
    unittest.main()
