"""Deterministic canonical serialisation (companion A.2).

canon(s) is the deterministic canonical serialisation referenced by the
integrity layer: h_i = H(h_(i-1) || canon(s_i)). For the hash chain to be
reproducible on every run and on any platform, canon must be a total,
deterministic function of a span's content.

Canonical form (decision recorded in the build notes):

- A JSON Canonicalisation Scheme (JCS) style serialisation: object keys sorted
  lexicographically at every level, the most compact separators, no insignificant
  whitespace, and UTF-8 output without ASCII escaping.
- Timestamps and other integral quantities are carried as integers (the span
  model uses unix nanoseconds), so there is no floating-point representation to
  vary between platforms.
- capture_index is not part of a span's content and is excluded; the hash chain
  binds stream position through chaining order, not through a content field.

This module is also used wherever the implementation must hash an arbitrary
derived object by value (for example the transformation-record ledger, D.3).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .model import Span


def canonical_json(obj: Any) -> bytes:
    """Return the canonical JSON serialisation of obj as UTF-8 bytes.

    Deterministic: keys are sorted at every level, separators are compact and
    non-ASCII characters are emitted directly. Rejects floats outside the JSON
    number grammar (NaN, Infinity) so that no non-portable value can enter the
    chain.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canon(span: Span) -> bytes:
    """Canonical serialisation of a span's content (companion A.2)."""
    return canonical_json(span.content_dict())


def sha256(data: bytes) -> bytes:
    """The collision-resistant hash H used throughout (companion A.2)."""
    return hashlib.sha256(data).digest()


def digest_hex(data: bytes) -> str:
    """Hex digest of data, for human-readable receipts and reports."""
    return hashlib.sha256(data).hexdigest()
