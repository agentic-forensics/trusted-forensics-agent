"""Portable, development-witness evidence packages (companion A.6, B Phase 7).

The JSON envelope is a reference format, not an external forensic standard.
Verification consumes original receipts and anchors and never signs new ones.
The bundled witness has a public demo key: it detects changes relative to a seal,
but does not protect against a party that deliberately issues a replacement seal.
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from . import __version__
from .canon import canonical_json, digest_hex, sha256
from .ingest import _span_from_record, ingest
from .integrity import Anchor, HashChain, Receipt, ReceiptStore, Witness, verify_chain
from .model import MissingSegment
from .report import Analysis, analyse, render_report
from .synth import Episode, default_witness

FORMAT = "tfa-evidence-bundle-v1"
PAYLOAD_KEYS = {"code_version", "code_manifest", "evidence", "analysis", "ledger", "selftrace", "report"}


def code_manifest() -> dict:
    """Identify the exact source used, without running code from a bundle."""
    return {p.name: digest_hex(p.read_bytes())
            for p in sorted(Path(__file__).parent.glob("*.py"))}


def episode_record(episode: Episode) -> dict:
    return {
        "trace_id": episode.trace_id,
        "conversation_id": episode.conversation_id,
        "seed_hex": episode.seed.hex(),
        "spans": [dict(s.content_dict(), capture_index=i)
                  for i, s in enumerate(episode.spans)],
        "capability_certificates": episode.capability_certificates,
        "anchor_indices": list(episode.anchor_indices),
        "missing_segments": [m.as_record() for m in episode.missing_segments],
    }


def episode_from_record(record: dict) -> Episode:
    spans = [_span_from_record(s) for s in record["spans"]]
    if not spans:
        raise ValueError("bundle contains no evidence spans")
    if [s.capture_index for s in spans] != list(range(len(spans))):
        raise ValueError("bundle span order must match contiguous capture indices")
    ingest(spans)
    return Episode(
        spans, record["capability_certificates"], bytes.fromhex(record["seed_hex"]),
        record["trace_id"], record["conversation_id"], tuple(record["anchor_indices"]),
        tuple(MissingSegment(**dict(m, affects=tuple(m["affects"])))
              for m in record["missing_segments"]),
    )


def analysis_record(a: Analysis) -> dict:
    """Full inspectable conclusions, not just counts or classifications."""
    return {
        "graph": {"nodes": [asdict(n) for n in a.graph.nodes.values()],
                  "edges": [asdict(e) for e in a.graph.edges]},
        "partial_order": {s.span_id: sorted(a.ingested.partial_order.predecessors(s.span_id))
                          for s in a.episode.spans},
        "planes": {p.value: a.projection.spans_in(p) for p in a.projection.by_plane},
        "answers": [asdict(answer) for answer in a.answers],
        "capability_checks": [asdict(check) for check in a.capability_checks],
        "completeness": asdict(a.completeness),
    }


def _anchor(record: dict) -> Anchor:
    return Anchor(record["index"], bytes.fromhex(record["head"]),
                  bytes.fromhex(record["signature"]), record["witness_id"],
                  record["independent"], record["note"])


def _receipt(record: dict) -> Receipt:
    return Receipt(record["index"], record["span_id"],
                   bytes.fromhex(record["prev_head"]), bytes.fromhex(record["span_digest"]),
                   bytes.fromhex(record["head"]))


def _seal_digest(manifest: dict) -> bytes:
    return sha256(canonical_json({"format": FORMAT, "manifest": manifest}))


def create_bundle(analysis: Analysis, witness: Optional[Witness] = None) -> dict:
    """Seal the actual rendered bytes, all inputs, derivations and self-trace."""
    witness = witness or default_witness()
    a = copy.deepcopy(analysis)
    checked = verify_chain(a.episode.spans, list(a.chain.store), a.anchors,
                           witness, a.episode.seed)
    if not checked.ok:
        raise ValueError("cannot package evidence that fails integrity verification")
    report = render_report(a)
    derived = analysis_record(a)
    report_inputs = [
        episode_record(a.episode), a.chain.store.records(),
        [anchor.as_record() for anchor in a.anchors], asdict(a.verification),
        derived, a.ledger.records(),
        [s.content_dict() for s in a.tracer.spans], a.selftrace_anchor.as_record(),
        code_manifest(),
    ]
    a.ledger.record("report", "render_report (companion B Phase 7)", report_inputs, report)
    a.tracer.record_action("render_report", inputs=derived,
                           output={"report_sha256": digest_hex(report.encode("utf-8")),
                                   "ledger": a.ledger.records()})
    self_anchor = a.tracer.witness_head()
    payload = {
        "code_version": __version__,
        "code_manifest": code_manifest(),
        "evidence": {"episode": episode_record(a.episode),
                     "receipts": a.chain.store.records(),
                     "anchors": [anchor.as_record() for anchor in a.anchors]},
        "analysis": derived,
        "ledger": a.ledger.records(),
        "selftrace": {"seed_hex": a.tracer.seed.hex(),
                      "spans": [s.content_dict() for s in a.tracer.spans],
                      "receipts": a.tracer.chain.store.records(),
                      "anchors": [self_anchor.as_record()]},
        "report": report,
    }
    # JSON round-trip fixes tuples to the same portable representation on disk.
    payload = json.loads(canonical_json(payload))
    manifest = {name: digest_hex(canonical_json(value)) for name, value in payload.items()}
    return {"format": FORMAT, "payload": payload, "manifest": manifest,
            "seal": witness.attest(0, _seal_digest(manifest)).as_record()}


@dataclass(frozen=True)
class BundleVerification:
    ok: bool
    messages: List[str]
    independent_witness: bool


def verify_bundle(bundle: dict, witness: Optional[Witness] = None) -> BundleVerification:
    """Verify preserved content in place; never re-seal or execute bundled code."""
    witness = witness or default_witness()
    errors = []
    try:
        if set(bundle) != {"format", "payload", "manifest", "seal"} or bundle["format"] != FORMAT:
            raise ValueError("unsupported bundle envelope or format")
        payload, manifest = bundle["payload"], bundle["manifest"]
        if set(payload) != PAYLOAD_KEYS or set(manifest) != PAYLOAD_KEYS:
            raise ValueError("missing or unexpected bundle components")
        for name, value in payload.items():
            if digest_hex(canonical_json(value)) != manifest[name]:
                errors.append(f"{name}: content digest does not match manifest")
        seal = _anchor(bundle["seal"])
        if (seal.index != 0 or seal.head != _seal_digest(manifest)
                or seal.independent != witness.independent or not witness.verify(seal)):
            errors.append("package seal does not verify")
        evidence = payload["evidence"]
        ep = episode_from_record(evidence["episode"])
        for name, spans, records, seed in (
            ("evidence", ep.spans, evidence, ep.seed),
            ("selftrace", [_span_from_record(s) for s in payload["selftrace"]["spans"]],
             payload["selftrace"], bytes.fromhex(payload["selftrace"]["seed_hex"])),
        ):
            result = verify_chain(spans, [_receipt(r) for r in records["receipts"]],
                                  [_anchor(a) for a in records["anchors"]], witness, seed)
            if not result.ok:
                errors.extend(f"{name}: {m}" for m in result.messages)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        errors.append(f"invalid bundle: {exc}")
    return BundleVerification(not errors, errors, witness.independent)


def load_bundle(path: str) -> dict:
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def analyse_bundle(bundle: dict, witness: Optional[Witness] = None) -> Analysis:
    """Reconstruct from verified original receipts, without re-anchoring evidence."""
    witness = witness or default_witness()
    checked = verify_bundle(bundle, witness)
    if not checked.ok:
        raise ValueError("; ".join(checked.messages))
    evidence = bundle["payload"]["evidence"]
    episode = episode_from_record(evidence["episode"])
    store = ReceiptStore()
    for record in evidence["receipts"]:
        store.append(_receipt(record))
    chain = HashChain(episode.seed, store)
    chain.head = store[-1].head
    anchors = [_anchor(a) for a in evidence["anchors"]]
    return analyse(episode, witness, preserved=(chain, anchors))


def reproduce_bundle(bundle: dict, witness: Optional[Witness] = None) -> BundleVerification:
    """Repeat with the installed source and compare conclusions and report bytes."""
    witness = witness or default_witness()
    checked = verify_bundle(bundle, witness)
    if not checked.ok:
        return checked
    if bundle["payload"]["code_manifest"] != code_manifest():
        return BundleVerification(False, ["source version differs; use the recorded code manifest"],
                                  witness.independent)
    a = analyse_bundle(bundle, witness)
    errors = []
    if render_report(a) != bundle["payload"]["report"]:
        errors.append("reproduced report differs from sealed report")
    if canonical_json(analysis_record(a)) != canonical_json(bundle["payload"]["analysis"]):
        errors.append("reproduced conclusions differ from sealed conclusions")
    # This includes the report transformation and self-trace as exported.
    repeated = create_bundle(a, witness)
    for name in ("ledger", "selftrace"):
        if repeated["manifest"][name] != bundle["manifest"][name]:
            errors.append(f"reproduced {name} differs from sealed {name}")
    return BundleVerification(not errors, errors, witness.independent)
