"""The integrity layer: hash chain, append-only receipts, witness (companion A.2, A.6).

The hash chain over the canonicalised span stream is:

    h_0 = H(seed)
    h_i = H(h_(i-1) || canon(s_i))

A span set is tamper-evident iff the recomputed chain matches a sequence of
independently witnessed anchors w_j = Sign_W(h_k), produced by an attestation
service W distinct from the agent's principals (companion A.2).

What this establishes, and what it does not (companion A.2, A.6): it secures the
integrity of the record that was captured and provides an independent attestation
of it. It does NOT make a nondeterministic system reproducible, establish why the
system acted, prove the emitter reported faithfully, or prove that omitted events
did not occur. Integrity is a separate property from completeness; one cannot
protect through a hash chain what was never written.

The chain runs over the captured emission order (a total order), which is a
separate property from the reconstructed partial order of the episode (model.py).

Threat model (companion A.6): tampering is made evident where the attacker is a
compromised agent or application emitting into an honest, independent collector,
or an operator who would later alter the stored record. It is correspondingly
weaker against a collector compromised before the witness is reached, against
operator-witness collusion, and against clock manipulation.
"""

from __future__ import annotations

import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .canon import canon, sha256
from .model import Span


# --------------------------------------------------------------------------- #
# Receipts and the append-only store (companion A.6)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Receipt:
    """A tamper-evident receipt (h_(i-1), digest of canon(s_i), h_i).

    Written by the forensic span processor on export (companion A.6).
    """

    index: int
    span_id: str
    prev_head: bytes        # h_(i-1)
    span_digest: bytes      # H(canon(s_i))
    head: bytes             # h_i

    def as_record(self) -> dict:
        return {
            "index": self.index,
            "span_id": self.span_id,
            "prev_head": self.prev_head.hex(),
            "span_digest": self.span_digest.hex(),
            "head": self.head.hex(),
        }


class ReceiptStore:
    """An append-only store of receipts (companion A.6).

    Append-only by API: receipts may be added and read, never mutated or
    removed. A real deployment would persist these to durable append-only
    storage; the reference keeps them in memory and can render them as records.
    """

    def __init__(self) -> None:
        self._receipts: List[Receipt] = []

    def append(self, receipt: Receipt) -> None:
        if self._receipts and receipt.index != self._receipts[-1].index + 1:
            raise ValueError("receipts must be appended in contiguous order")
        if not self._receipts and receipt.index != 0:
            raise ValueError("first receipt must have index 0")
        self._receipts.append(receipt)

    def __len__(self) -> int:
        return len(self._receipts)

    def __iter__(self):
        return iter(self._receipts)

    def __getitem__(self, i: int) -> Receipt:
        return self._receipts[i]

    def records(self) -> List[dict]:
        return [r.as_record() for r in self._receipts]


# --------------------------------------------------------------------------- #
# The hash chain (companion A.2)
# --------------------------------------------------------------------------- #

class HashChain:
    """The forensic span processor's hash chain (companion A.2, A.6).

    Extends the chain as each span is captured and writes a receipt to the
    append-only store. The seed fixes h_0 so the chain is reproducible.
    """

    def __init__(self, seed: bytes, store: Optional[ReceiptStore] = None) -> None:
        self._seed = seed
        self.head: bytes = sha256(seed)
        self.store = store if store is not None else ReceiptStore()

    @property
    def seed(self) -> bytes:
        return self._seed

    def append(self, span: Span) -> Receipt:
        """Canonicalise the span, extend the chain, write the receipt."""
        canon_bytes = canon(span)
        prev = self.head
        span_digest = sha256(canon_bytes)
        self.head = sha256(prev + canon_bytes)
        receipt = Receipt(
            index=len(self.store),
            span_id=span.span_id,
            prev_head=prev,
            span_digest=span_digest,
            head=self.head,
        )
        self.store.append(receipt)
        return receipt

    def extend(self, spans: Sequence[Span]) -> None:
        for span in spans:
            self.append(span)


# --------------------------------------------------------------------------- #
# The witness W (companion A.2, A.6)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Anchor:
    """An independently witnessed anchor w_j = Sign_W(h_k) (companion A.2)."""

    index: int               # k: the chain position whose head is anchored
    head: bytes              # h_k
    signature: bytes         # Sign_W(h_k)
    witness_id: str
    independent: bool        # whether W is independent of the agent's principals
    note: str = ""

    def as_record(self) -> dict:
        return {
            "index": self.index,
            "head": self.head.hex(),
            "signature": self.signature.hex(),
            "witness_id": self.witness_id,
            "independent": self.independent,
            "note": self.note,
        }


class Witness(ABC):
    """An attestation service W, distinct from the agent's principals (A.2).

    W must be independently subpoenable; that independence is what converts a
    self-signed log into third-party-witnessed evidence (companion A.6). The
    interface is pluggable precisely so a real, independent W can replace the
    development stand-in.
    """

    witness_id: str
    independent: bool

    @abstractmethod
    def attest(self, index: int, head: bytes) -> Anchor:
        """Counter-sign the chain head h_k at position k."""

    @abstractmethod
    def verify(self, anchor: Anchor) -> bool:
        """Verify that the anchor's signature is W's over its head."""


# A label carried on every anchor a development witness produces, so no reader
# can mistake it for the independent third party the model requires.
_DEV_NOTE = (
    "development stand-in only; not an independent third party. A real "
    "deployment requires a witness independently subpoenable of the operator "
    "(companion A.6)."
)


class LocalWitness(Witness):
    """A development stand-in witness using HMAC-SHA256 (companion A.6).

    This is NOT an independent third party and is labelled as such on every
    anchor. It exists so the synthetic demo can show the shape of witnessing end
    to end. The signing key is held distinctly from any agent principal, but a
    party that both operates the agent and holds this key gains nothing a real,
    independent W would prevent; that is the point of the label.
    """

    def __init__(self, key: bytes, witness_id: str = "local-dev-witness") -> None:
        if not key:
            raise ValueError("witness key must be non-empty")
        self._key = key
        self.witness_id = witness_id
        self.independent = False

    def _sign(self, index: int, head: bytes) -> bytes:
        message = index.to_bytes(8, "big") + head
        return hmac.new(self._key, message, "sha256").digest()

    def attest(self, index: int, head: bytes) -> Anchor:
        return Anchor(
            index=index,
            head=head,
            signature=self._sign(index, head),
            witness_id=self.witness_id,
            independent=self.independent,
            note=_DEV_NOTE,
        )

    def verify(self, anchor: Anchor) -> bool:
        if anchor.witness_id != self.witness_id:
            return False
        expected = self._sign(anchor.index, anchor.head)
        return hmac.compare_digest(expected, anchor.signature)


# --------------------------------------------------------------------------- #
# Verification (companion A.2: "tamper-evident iff the recomputed chain matches
# ... independently witnessed anchors")
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class VerificationResult:
    """The outcome of verifying a span stream against receipts and anchors.

    Fails closed: ok is True only if every span's recomputed digest and head
    match its receipt AND every anchor verifies against a head the chain
    actually produced. The first divergence is localised in broken_at_index.
    """

    ok: bool
    broken_at_index: Optional[int]
    anchors_ok: bool
    independent_witness: bool
    messages: Sequence[str] = field(default_factory=tuple)

    def summary(self) -> str:
        if self.ok:
            independence = (
                "an independent witness"
                if self.independent_witness
                else "a development stand-in witness (not independent)"
            )
            return f"tamper-evident: chain intact and attested by {independence}"
        if self.broken_at_index is not None:
            return f"tampering detected: chain diverges at span index {self.broken_at_index}"
        return "verification failed"


def verify_chain(
    spans: Sequence[Span],
    receipts: Sequence[Receipt],
    anchors: Sequence[Anchor],
    witness: Witness,
    seed: bytes,
) -> VerificationResult:
    """Recompute the chain from spans and check it against receipts and anchors.

    The spans must be supplied in captured emission order (the order the chain
    was built in). Any mismatch fails closed and localises the first divergent
    span; anchors are then checked against the heads the chain actually
    produced.
    """
    messages: List[str] = []

    if len(spans) != len(receipts):
        messages.append(
            f"span/receipt count mismatch: {len(spans)} spans, {len(receipts)} receipts"
        )
        return VerificationResult(
            ok=False,
            broken_at_index=None,
            anchors_ok=False,
            independent_witness=witness.independent,
            messages=tuple(messages),
        )

    # Recompute the chain, recording each produced head so anchors can be
    # checked against what the chain actually yields.
    heads_by_index: dict = {}
    head = sha256(seed)
    broken_at: Optional[int] = None
    for i, span in enumerate(spans):
        canon_bytes = canon(span)
        span_digest = sha256(canon_bytes)
        prev = head
        head = sha256(prev + canon_bytes)
        heads_by_index[i] = head

        receipt = receipts[i]
        if span_digest != receipt.span_digest:
            messages.append(
                f"span index {i} ({span.span_id}): content digest does not match receipt"
            )
            broken_at = i
            break
        if prev != receipt.prev_head:
            messages.append(
                f"span index {i} ({span.span_id}): previous head does not match receipt"
            )
            broken_at = i
            break
        if head != receipt.head:
            messages.append(
                f"span index {i} ({span.span_id}): chain head does not match receipt"
            )
            broken_at = i
            break

    chain_ok = broken_at is None

    # Verify anchors. An anchor is valid only if its signature verifies AND it
    # attests a head the (intact) chain actually produced at that index.
    anchors_ok = True
    if not anchors:
        anchors_ok = False
        messages.append("no witnessed anchors supplied")
    for anchor in anchors:
        if not witness.verify(anchor):
            anchors_ok = False
            messages.append(f"anchor at index {anchor.index}: signature does not verify")
            continue
        expected_head = heads_by_index.get(anchor.index)
        if expected_head is None:
            anchors_ok = False
            messages.append(
                f"anchor at index {anchor.index}: no chain head at that index"
            )
            continue
        if anchor.head != expected_head:
            anchors_ok = False
            messages.append(
                f"anchor at index {anchor.index}: attested head does not match the recomputed chain"
            )

    ok = chain_ok and anchors_ok
    return VerificationResult(
        ok=ok,
        broken_at_index=broken_at,
        anchors_ok=anchors_ok,
        independent_witness=witness.independent,
        messages=tuple(messages),
    )
