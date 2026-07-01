"""Command-line entry point (companion D.4).

Runs the model end to end on the synthetic trace: generate the episode,
reconstruct, verify, classify, and print the admissibility-readiness report. A
--tamper option mutates one stored span after witnessing to demonstrate that a
single alteration is detected, localised, and that verification fails closed.

No network access, no real provider connectors, no operative preservation
requests: the only input is the synthetic trace (briefing scope).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from typing import List, Optional

from .capability import boundary_subversions
from .ingest import load_trace
from .integrity import verify_chain
from .report import analyse, render_report
from .synth import Episode, build_episode, default_witness, witness_episode


def _json_summary(analysis) -> dict:
    a = analysis
    return {
        "trace_id": a.episode.trace_id,
        "integrity": {
            "ok": a.verification.ok,
            "summary": a.verification.summary(),
            "independent_witness": a.verification.independent_witness,
            "chain_head": a.chain.head.hex(),
            "anchors": len(a.anchors),
        },
        "questions": [
            {
                "qid": ans.qid,
                "classification": ans.classification.value,
                "gap": None if ans.gap is None
                else {"party": ans.gap.party, "data_class": ans.gap.data_class},
            }
            for ans in a.answers
        ],
        "boundary_subversions": [
            {"span_id": c.span_id, "tool": c.tool, "failed": list(c.failed_dimensions)}
            for c in boundary_subversions(a.capability_checks)
        ],
        "completeness": {
            "schema_complete": a.completeness.schema_complete,
            "evidential_complete": a.completeness.evidential_complete,
            "per_question": a.completeness.per_question,
        },
        "unverified_leads": [r.output_id for r in a.unverified_leads],
        "selftrace_actions": len(a.tracer.spans),
    }


def _run_tamper(index: int, episode: Episode) -> int:
    """Witness a clean episode, mutate one stored span, then verify."""
    witness = default_witness()
    chain, anchors = witness_episode(episode, witness)

    if not (0 <= index < len(episode.spans)):
        print(f"tamper index {index} out of range 0..{len(episode.spans) - 1}",
              file=sys.stderr)
        return 2

    original = episode.spans[index]
    mutated_attrs = dict(original.attributes)
    mutated_attrs["dcfp.tampered"] = "an attacker altered this stored span"
    mutated = dataclasses.replace(original, attributes=mutated_attrs)
    stored = list(episode.spans)
    stored[index] = mutated

    result = verify_chain(stored, list(chain.store), anchors, witness, episode.seed)

    print("Tamper demonstration (a stored span was altered after witnessing):")
    print(f"  mutated span index: {index} ({original.span_id})")
    print(f"  {result.summary()}")
    print(f"  broken_at_index: {result.broken_at_index}")
    print(f"  verification ok:  {result.ok}")
    for m in result.messages:
        print(f"    - {m}")
    # Fail closed: a detected tamper is a non-zero exit.
    return 0 if result.ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tfa",
        description="Trusted Forensic Agent - DCFP reference implementation. "
                    "Runs the model on a synthetic trace.",
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="report format (default: text)",
    )
    parser.add_argument(
        "--tamper", type=int, metavar="INDEX", default=None,
        help="mutate the stored span at INDEX after witnessing, to demonstrate "
             "tamper detection and fail-closed verification",
    )
    parser.add_argument(
        "--out", metavar="FILE", default=None,
        help="write output to FILE instead of standard output",
    )
    parser.add_argument(
        "--trace", metavar="FILE", default=None,
        help="load an episode from a JSON trace file (see "
             "examples/synthetic_trace.json) instead of the built-in synthetic "
             "episode",
    )
    args = parser.parse_args(argv)

    try:
        episode = load_trace(args.trace) if args.trace else build_episode()
    except (OSError, ValueError) as exc:
        print(f"could not load trace: {exc}", file=sys.stderr)
        return 2

    if args.tamper is not None:
        return _run_tamper(args.tamper, episode)

    analysis = analyse(episode)

    if args.format == "json":
        output = json.dumps(_json_summary(analysis), indent=2, sort_keys=True) + "\n"
    else:
        output = render_report(analysis)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(output)

    # A clean run exits 0; a failed integrity verification fails closed.
    return 0 if analysis.verification.ok else 1


if __name__ == "__main__":
    sys.exit(main())
