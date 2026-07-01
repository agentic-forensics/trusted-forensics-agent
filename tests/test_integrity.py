"""Tests for the integrity layer (companion A.2, A.6).

Covers acceptance criterion 4: verify the hash chain against witnessed anchors;
a single mutated span is detected and localised; verification fails closed.
"""

import dataclasses
import unittest

from tfa.integrity import (
    HashChain,
    LocalWitness,
    Receipt,
    ReceiptStore,
    verify_chain,
)
from tfa.model import Span


def _stream():
    spans = [
        Span("t1", f"s{i}", None, "inference", 1000 + i, 2000 + i,
             attributes={"i": i}, capture_index=i)
        for i in range(5)
    ]
    seed = b"seed"
    chain = HashChain(seed)
    chain.extend(spans)
    return spans, seed, chain


class TestHashChain(unittest.TestCase):
    def test_receipts_contiguous_and_complete(self):
        spans, _seed, chain = _stream()
        self.assertEqual(len(chain.store), len(spans))
        for i, r in enumerate(chain.store):
            self.assertEqual(r.index, i)
            self.assertEqual(r.span_id, spans[i].span_id)

    def test_chain_links(self):
        _spans, _seed, chain = _stream()
        receipts = list(chain.store)
        for i in range(1, len(receipts)):
            self.assertEqual(receipts[i].prev_head, receipts[i - 1].head)

    def test_deterministic_head(self):
        _a, _b, chain1 = _stream()
        _c, _d, chain2 = _stream()
        self.assertEqual(chain1.head, chain2.head)


class TestReceiptStore(unittest.TestCase):
    def test_append_only_requires_contiguous_indices(self):
        store = ReceiptStore()
        store.append(Receipt(0, "s0", b"\x00", b"\x01", b"\x02"))
        with self.assertRaises(ValueError):
            store.append(Receipt(2, "s2", b"\x02", b"\x03", b"\x04"))

    def test_first_receipt_must_be_index_zero(self):
        store = ReceiptStore()
        with self.assertRaises(ValueError):
            store.append(Receipt(1, "s1", b"\x00", b"\x01", b"\x02"))


class TestWitness(unittest.TestCase):
    def test_local_witness_is_not_independent(self):
        w = LocalWitness(b"k")
        self.assertFalse(w.independent)

    def test_attest_then_verify(self):
        w = LocalWitness(b"k")
        anchor = w.attest(3, b"head-bytes")
        self.assertTrue(w.verify(anchor))
        self.assertIn("not an independent third party", anchor.note)

    def test_tampered_anchor_head_fails(self):
        w = LocalWitness(b"k")
        anchor = w.attest(3, b"head-bytes")
        forged = dataclasses.replace(anchor, head=b"other-head")
        self.assertFalse(w.verify(forged))

    def test_empty_key_rejected(self):
        with self.assertRaises(ValueError):
            LocalWitness(b"")


class TestVerifyChain(unittest.TestCase):
    def _witnessed(self):
        spans, seed, chain = _stream()
        w = LocalWitness(b"k")
        receipts = list(chain.store)
        anchors = [w.attest(len(spans) - 1, receipts[-1].head)]
        return spans, seed, receipts, anchors, w

    def test_intact_chain_verifies(self):
        spans, seed, receipts, anchors, w = self._witnessed()
        result = verify_chain(spans, receipts, anchors, w, seed)
        self.assertTrue(result.ok)
        self.assertIsNone(result.broken_at_index)
        self.assertTrue(result.anchors_ok)

    def test_intact_chain_reports_non_independent_witness(self):
        spans, seed, receipts, anchors, w = self._witnessed()
        result = verify_chain(spans, receipts, anchors, w, seed)
        self.assertFalse(result.independent_witness)
        self.assertIn("not independent", result.summary())

    def test_mutated_span_detected_and_localised(self):
        spans, seed, receipts, anchors, w = self._witnessed()
        mutated = list(spans)
        mutated[2] = dataclasses.replace(spans[2], attributes={"i": 999})
        result = verify_chain(mutated, receipts, anchors, w, seed)
        self.assertFalse(result.ok)
        self.assertEqual(result.broken_at_index, 2)

    def test_verification_fails_closed_when_anchor_unreachable(self):
        # Mutating before the anchored index means the anchored head is never
        # reproduced, so the anchor cannot be confirmed: fail closed.
        spans, seed, receipts, anchors, w = self._witnessed()
        mutated = list(spans)
        mutated[0] = dataclasses.replace(spans[0], attributes={"i": -1})
        result = verify_chain(mutated, receipts, anchors, w, seed)
        self.assertFalse(result.ok)
        self.assertFalse(result.anchors_ok)

    def test_forged_anchor_signature_fails(self):
        spans, seed, receipts, anchors, w = self._witnessed()
        forged = [dataclasses.replace(anchors[0], signature=b"not-a-signature")]
        result = verify_chain(spans, receipts, forged, w, seed)
        self.assertFalse(result.ok)
        self.assertFalse(result.anchors_ok)

    def test_missing_anchors_fail_closed(self):
        spans, seed, receipts, _anchors, w = self._witnessed()
        result = verify_chain(spans, receipts, [], w, seed)
        self.assertFalse(result.ok)

    def test_count_mismatch_fails(self):
        spans, seed, receipts, anchors, w = self._witnessed()
        result = verify_chain(spans[:-1], receipts, anchors, w, seed)
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
