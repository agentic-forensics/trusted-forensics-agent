"""End-to-end analysis and the admissibility-readiness report (companion B Phase 7, D.2).

analyse() runs the whole model over an episode - verify the integrity layer,
ingest, project the planes, reconstruct G, answer the seven questions, check
capabilities, assess completeness - while being forensic-by-design about itself:
every step is emitted to a witnessed self-trace, and every derived object is
recorded in the transformation ledger (companion D.3). One model-suggested
association is included, and appears only as an unverified lead.

render_report() produces an admissibility-readiness report. Output language
discipline (briefing section 5): it is a readiness report, not a guarantee. It
enumerates limitations and named gaps and makes no claim of admissibility,
accuracy or completeness beyond what the synthetic data supports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import List, Optional

from . import __version__
from .capability import CapabilityCheck, boundary_subversions, check_episode
from .completeness import CompletenessAssessment, assess
from .graph import Graph, build_graph
from .ingest import Ingested, ingest
from .integrity import Anchor, HashChain, VerificationResult, Witness, verify_chain
from .planes import Projection
from .model import IntegrityStatus
from .questions import Answer, resolve_all
from .selftrace import SelfTracer
from .synth import (
    Episode,
    default_witness,
    witness_episode,
)
from .transform import TransformationLedger, TransformationRecord

# The standing limitations, stated up front and repeated on the report so no
# reader can mistake the reference for more than it is (briefing section 6;
# companion A.6, D.5).
STANDING_LIMITATIONS = (
    "This is a reference implementation, not a product.",
    "There are no measured error rates and no claim of general acceptance; the "
    "field does not yet have these (companion D.5).",
    "The integrity layer checks record integrity relative to a witnessed seal. "
    "Independent attestation requires an independent witness. It does not make "
    "a nondeterministic system reproducible, "
    "establish why the system acted, prove the emitter reported faithfully, or "
    "prove that omitted events did not occur. Integrity is a separate property "
    "from completeness (companion A.6).",
    "The integrity layer is weaker against a collector compromised before the "
    "witness is reached, against operator-witness collusion, and against clock "
    "manipulation (companion A.6).",
    "The witness used here is a development stand-in, not an independent third "
    "party. A real deployment requires a witness independently subpoenable of "
    "the operator (companion A.6). Its public demo key permits replacement seals.",
    "The synthetic trace and this report make no claim of admissibility, "
    "accuracy or completeness beyond what the synthetic data supports.",
)


@dataclass
class Analysis:
    """The result of running the whole model over an episode."""

    episode: Episode
    chain: HashChain
    anchors: List[Anchor]
    verification: VerificationResult
    ingested: Ingested
    projection: Projection
    graph: Graph
    answers: List[Answer]
    capability_checks: List[CapabilityCheck]
    completeness: CompletenessAssessment
    ledger: TransformationLedger
    tracer: SelfTracer
    selftrace_anchor: Anchor
    unverified_leads: List[TransformationRecord]


def analyse(episode: Episode, witness: Optional[Witness] = None,
            preserved=None) -> Analysis:
    """Run the full model over the episode, self-traced and ledgered."""
    if witness is None:
        witness = default_witness()
    ledger = TransformationLedger(code_version=__version__)
    tracer = SelfTracer(witness)

    # 1. Integrity: build and verify the witnessed episode chain.
    chain, anchors = preserved if preserved is not None else witness_episode(episode, witness)
    verification = verify_chain(
        episode.spans, list(chain.store), anchors, witness, episode.seed
    )
    if not verification.ok:
        raise ValueError("evidence integrity verification failed: " + "; ".join(verification.messages))
    # Validate identities before deriving anything; duplicates cannot be collapsed.
    ingest(episode.spans)
    span_records = [s.content_dict() for s in episode.spans]
    context = {"spans": span_records,
               "capability_certificates": episode.capability_certificates,
               "missing_segments": [m.as_record() for m in episode.missing_segments]}
    tracer.record_action(
        "verify_integrity",
        inputs=[episode.seed.hex(), context],
        output={"ok": verification.ok, "summary": verification.summary()},
    )

    verified = verification.ok

    # 2. Ingest and the partial order.
    ing = ingest(episode.spans)
    ledger.record(
        output_id="partial-order",
        rule="ingest: parentage and effect links, never a global clock",
        inputs=[[s.content_dict() for s in episode.spans]],
        output={"roots": ing.roots, "predecessors": {
            s.span_id: sorted(ing.partial_order.predecessors(s.span_id))
            for s in episode.spans}},
    )
    tracer.record_action("ingest", output={"roots": ing.roots})

    # 3. Planes.
    projection = Projection(episode.spans)
    ledger.record(
        output_id="plane-projection",
        rule="planes: pi projection (companion A.4)",
        inputs=[span_records],
        output={p.value: projection.spans_in(p) for p in projection.by_plane},
    )
    tracer.record_action("project_planes")

    # 4. Graph, with a ledger entry for every reconstructed edge.
    graph = build_graph(episode.spans)
    graph.edges = [replace(edge, integrity_status=IntegrityStatus.VERIFIED)
                   for edge in graph.edges]
    for node in graph.nodes.values():
        ledger.record(output_id="node-" + node.node_id,
                      rule="build_graph: actor or resource (companion A.2)",
                      inputs=[span_records], output=asdict(node))
    for i, edge in enumerate(graph.edges):
        ledger.record(
            output_id=f"edge-{i}",
            rule=f"build_graph: {edge.edge_type.value}",
            inputs=[s.content_dict() for s in episode.spans
                    if s.span_id in edge.source_artefact],
            output=asdict(edge),
        )
    tracer.record_action("build_graph", output={"edges": len(graph.edges)})

    # 5. Seven questions, one ledger entry each.
    answers = resolve_all(
        episode.spans, episode.capability_certificates, episode.missing_segments
    )
    for a in answers:
        ledger.record(
            output_id=f"answer-{a.qid}",
            rule=f"resolve {a.qid}",
            inputs=[context],
            output=asdict(a),
        )
    tracer.record_action("resolve_questions", output={"count": len(answers)})

    # 6. Capability check.
    capability_checks = check_episode(episode.capability_certificates, episode.spans)
    for c in capability_checks:
        ledger.record(
            output_id=f"capability-{c.span_id}",
            rule="capability: call-granularity scope check",
            inputs=[episode.span_by_id(c.span_id).content_dict(),
                    episode.capability_certificates],
            output=asdict(c),
        )
    tracer.record_action(
        "check_capability",
        output={"boundary_subversions": len(boundary_subversions(capability_checks))},
    )

    # 7. Completeness.
    completeness = assess(answers, chain_verified=verified)
    ledger.record(
        output_id="completeness",
        rule="completeness: three senses (companion A.2)",
        inputs=[[asdict(a) for a in answers], verified],
        output=asdict(completeness),
    )
    tracer.record_action("assess_completeness", output=completeness.summary())

    # 8. A model-suggested association, recorded ONLY as an unverified lead: the
    #    external recipient might be the principal's own alias. It is a lead to
    #    verify, never an evidential edge on the model's authority (companion D.3).
    for span in episode.spans:
        suggestion = span.get("dcfp.demo.lead")
        if not isinstance(suggestion, dict) or not suggestion.get("recipient") or not suggestion.get("principal"):
            continue
        ledger.record_lead(
            output_id="lead-external-recipient-alias",
            rule="synthetic illustration of an unverified association",
            inputs=[span.content_dict()],
            suggestion={
                "association": (
                    f"{suggestion['recipient']} may be a personal alias of {suggestion['principal']}"
                )
            },
            model_invocation="SIMULATED fixture suggestion; no model was invoked",
            note="Synthetic lead only; no model was invoked and this is not evidence.",
        )
        tracer.record_action(
            "record_lead",
            note="synthetic association recorded as an unverified lead; no model invoked",
        )

    # 9. Bind all derivations, then witness the analysis self-trace with the same W.
    # bundle.py separately records and seals the rendered report bytes.
    tracer.record_action("complete_analysis", inputs=context,
                         output={"ledger": ledger.records(),
                                 "answers": [asdict(a) for a in answers]})
    selftrace_anchor = tracer.witness_head()

    return Analysis(
        episode=episode,
        chain=chain,
        anchors=anchors,
        verification=verification,
        ingested=ing,
        projection=projection,
        graph=graph,
        answers=answers,
        capability_checks=capability_checks,
        completeness=completeness,
        ledger=ledger,
        tracer=tracer,
        selftrace_anchor=selftrace_anchor,
        unverified_leads=ledger.unverified_leads(),
    )


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _line(char: str = "-", width: int = 74) -> str:
    return char * width


def render_report(analysis: Analysis) -> str:
    """Render the admissibility-readiness report as text (companion B Phase 7)."""
    a = analysis
    out: List[str] = []

    out.append(_line("="))
    out.append("ADMISSIBILITY-READINESS REPORT")
    out.append("Trusted Forensic Agent (TFA) - DCFP reference implementation")
    out.append(f"Code version: {__version__}")
    out.append(_line("="))
    out.append("")
    out.append(
        "This is a readiness report, not a guarantee. It records supporting "
        "evidence, named gaps and stated limitations. It makes no claim of "
        "admissibility, accuracy or completeness."
    )
    out.append("")

    # Episode
    out.append(_line())
    out.append("EPISODE")
    out.append(_line())
    out.append(f"trace id:        {a.episode.trace_id}")
    out.append(f"conversation id: {a.episode.conversation_id}")
    out.append(f"spans:           {len(a.episode.spans)}")
    out.append("")

    # Integrity
    out.append(_line())
    out.append("INTEGRITY LAYER")
    out.append(_line())
    out.append(a.verification.summary())
    out.append(f"chain head: {a.chain.head.hex()}")
    out.append(f"witnessed anchors: {len(a.anchors)}")
    out.append("Raw trace inputs are sealed at ingestion; this does not verify their earlier history.")
    if not a.verification.independent_witness:
        out.append(
            "NOTE: the witness is a development stand-in, not an independent "
            "third party. Integrity is a separate property from completeness."
        )
    if a.verification.messages:
        for m in a.verification.messages:
            out.append(f"  - {m}")
    out.append("")

    # Seven questions
    out.append(_line())
    out.append("THE SEVEN QUESTIONS")
    out.append(_line())
    for ans in a.answers:
        out.append(f"{ans.qid}. {ans.question}")
        out.append(f"    classification: {ans.classification.value}")
        out.append(f"    {ans.value}")
        if ans.evidence:
            out.append(f"    evidence: {', '.join(ans.evidence)}")
        if ans.gap is not None:
            out.append(
                f"    NAMED GAP - party: {ans.gap.party}; "
                f"data class: {ans.gap.data_class}"
            )
            if ans.gap.note:
                out.append(f"      {ans.gap.note}")
        out.append("")

    # Capability / boundary subversion
    out.append(_line())
    out.append("CAPABILITY (call-granularity scope check)")
    out.append(_line())
    subs = boundary_subversions(a.capability_checks)
    for c in a.capability_checks:
        status = "IN SCOPE" if c.in_scope else "OUT OF SCOPE - boundary subversion"
        out.append(f"{c.span_id}: {c.tool} [{status}]")
        if not c.in_scope:
            out.append(f"    failed on: {', '.join(c.failed_dimensions)}")
            out.append(f"    {c.reason}")
    if not subs:
        out.append("no boundary subversions found")
    out.append("")

    # Completeness
    out.append(_line())
    out.append("COMPLETENESS (three senses)")
    out.append(_line())
    out.append(f"schema-complete:     {a.completeness.schema_complete}")
    out.append(f"evidential-complete: {a.completeness.evidential_complete}")
    out.append("This concerns support for the answers given; named gaps remain below.")
    out.append("per-question classification:")
    for qid in sorted(a.completeness.per_question):
        out.append(f"    {qid}: {a.completeness.per_question[qid]}")
    if a.completeness.named_gaps:
        out.append("named gaps:")
        for qid, gap in a.completeness.named_gaps:
            out.append(f"    {qid}: {gap.party} / {gap.data_class}")
    out.append(f"case sufficiency: {a.completeness.case_sufficiency}")
    out.append("")

    # Declared missing segments (companion C.2/C.3). Rendered only when present,
    # so the base single-episode report is unaffected.
    if a.episode.missing_segments:
        out.append(_line())
        out.append("MISSING SEGMENTS - declared, not captured (cross-provider join)")
        out.append(_line())
        out.append(
            "Known to have existed but not obtained. Named here rather than "
            "papered over (companion C.2/C.3)."
        )
        for seg in a.episode.missing_segments:
            out.append(f"    {seg.segment_id}")
            out.append(f"      party:      {seg.party}")
            out.append(f"      data class: {seg.data_class}")
            if seg.affects:
                out.append(f"      bears on:   {', '.join(seg.affects)}")
            if seg.evidence:
                out.append(f"      evidence:   {seg.evidence}")
            if seg.note:
                out.append(f"      note:       {seg.note}")
        out.append("")

    # Unverified leads
    out.append(_line())
    out.append("UNVERIFIED LEADS (not evidence)")
    out.append(_line())
    if a.unverified_leads:
        for lead in a.unverified_leads:
            out.append(f"    {lead.output_id}: {lead.rule}")
            out.append(f"      {lead.note}")
    else:
        out.append("none")
    out.append("")

    # Transformation ledger
    out.append(_line())
    out.append("TRANSFORMATION LEDGER (analysis-stage snapshot)")
    out.append(_line())
    out.append(
        f"{len(a.ledger)} records, each binding inputs by hash to a derived "
        "output and the code version that produced it (companion D.3)."
    )
    out.append("")

    # Self-instrumentation
    out.append(_line())
    out.append("SELF-INSTRUMENTATION (analysis-stage snapshot)")
    out.append(_line())
    out.append(
        f"{len(a.tracer.spans)} of the tool's own actions were emitted as DCFP "
        "spans in a separate hash chain, witnessed by the same W (companion D.3)."
    )
    out.append(f"self-trace chain head: {a.tracer.chain.head.hex()}")
    out.append("Package export appends the rendered-report transformation and witnesses the extended self-trace.")
    out.append("")

    # Six dimensions
    out.append(_line())
    out.append("RELIABILITY AND ADMISSIBILITY DIMENSIONS (companion B Phase 7)")
    out.append(_line())
    out.append("Declared readiness statements, not measured scores or a judicial validation.")
    dimensions = [
        ("Testable methodology",
         "The method is documented and deterministic; another examiner can "
         "repeat the analysis from the preserved record."),
        ("Known error rate",
         "None. The field has no measured error rates for agentic forensics "
         "(companion D.5). Stated plainly rather than estimated."),
        ("Peer review and publication",
         "Not claimed. The surrounding literature is one or two papers deep."),
        ("General acceptance",
         "None. The relevant community is still forming (companion D.5)."),
        ("Reproducibility (forensic sense)",
         "The analysis is re-runnable from versioned inputs and code via the "
         "transformation ledger; the agent's own run is not replayable, and "
         "that nondeterminism is documented rather than concealed."),
        ("Chain of custody and record integrity",
         "The witnessed hash chain checks record integrity relative to the seal. "
         "The development witness does not provide independent attestation. "
         "Authenticity, provenance "
         "and custody/handling records are established separately and are out "
         "of scope for this synthetic demonstration."),
    ]
    for name, text in dimensions:
        out.append(f"- {name}:")
        out.append(f"    {text}")
    out.append("")

    # Limitations
    out.append(_line())
    out.append("STATED LIMITATIONS")
    out.append(_line())
    for lim in STANDING_LIMITATIONS:
        out.append(f"- {lim}")
    out.append("")
    out.append(_line("="))
    out.append("END OF REPORT")
    out.append(_line("="))

    return "\n".join(out) + "\n"
