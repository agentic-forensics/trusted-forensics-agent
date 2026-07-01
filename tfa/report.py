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

from dataclasses import dataclass
from typing import List, Optional

from . import __version__
from .capability import CapabilityCheck, boundary_subversions, check_episode
from .completeness import CompletenessAssessment, assess
from .graph import Graph, build_graph
from .ingest import Ingested, ingest
from .integrity import Anchor, HashChain, VerificationResult, Witness, verify_chain
from .planes import Projection
from .questions import Answer, resolve_all
from .selftrace import SelfTracer
from .synth import (
    EXTERNAL_RECIPIENT,
    PRINCIPAL_ID,
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
    "The integrity layer secures record integrity and provides an independent "
    "attestation of it. It does not make a nondeterministic system reproducible, "
    "establish why the system acted, prove the emitter reported faithfully, or "
    "prove that omitted events did not occur. Integrity is a separate property "
    "from completeness (companion A.6).",
    "The integrity layer is weaker against a collector compromised before the "
    "witness is reached, against operator-witness collusion, and against clock "
    "manipulation (companion A.6).",
    "The witness used here is a development stand-in, not an independent third "
    "party. A real deployment requires a witness independently subpoenable of "
    "the operator (companion A.6).",
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


def analyse(episode: Episode, witness: Optional[Witness] = None) -> Analysis:
    """Run the full model over the episode, self-traced and ledgered."""
    if witness is None:
        witness = default_witness()
    ledger = TransformationLedger(code_version=__version__)
    tracer = SelfTracer(witness)

    # 1. Integrity: build and verify the witnessed episode chain.
    chain, anchors = witness_episode(episode, witness)
    verification = verify_chain(
        episode.spans, list(chain.store), anchors, witness, episode.seed
    )
    tracer.record_action(
        "verify_integrity",
        inputs=[episode.seed.hex(), [s.span_id for s in episode.spans]],
        output={"ok": verification.ok, "summary": verification.summary()},
    )

    verified = verification.ok

    # 2. Ingest and the partial order.
    ing = ingest(episode.spans)
    ledger.record(
        output_id="partial-order",
        rule="ingest: parentage and effect links, never a global clock",
        inputs=[[s.content_dict() for s in episode.spans]],
        output={"roots": ing.roots},
    )
    tracer.record_action("ingest", output={"roots": ing.roots})

    # 3. Planes.
    projection = Projection(episode.spans)
    ledger.record(
        output_id="plane-projection",
        rule="planes: pi projection (companion A.4)",
        inputs=[[s.span_id for s in episode.spans]],
        output={p.value: projection.spans_in(p) for p in projection.by_plane},
    )
    tracer.record_action("project_planes")

    # 4. Graph, with a ledger entry for every reconstructed edge.
    graph = build_graph(episode.spans)
    for i, edge in enumerate(graph.edges):
        ledger.record(
            output_id=f"edge-{i}",
            rule=f"build_graph: {edge.edge_type.value}",
            inputs=[list(edge.source_artefact)],
            output={
                "source": edge.source,
                "target": edge.target,
                "type": edge.edge_type.value,
                "observation": edge.observation.value,
                "confidence": edge.confidence.value,
            },
        )
    tracer.record_action("build_graph", output={"edges": len(graph.edges)})

    # 5. Seven questions, one ledger entry each.
    answers = resolve_all(episode.spans, episode.capability_certificates)
    for a in answers:
        ledger.record(
            output_id=f"answer-{a.qid}",
            rule=f"resolve {a.qid}",
            inputs=[list(a.evidence)],
            output={"classification": a.classification.value, "value": a.value},
        )
    tracer.record_action("resolve_questions", output={"count": len(answers)})

    # 6. Capability check.
    capability_checks = check_episode(episode.capability_certificates, episode.spans)
    for c in capability_checks:
        ledger.record(
            output_id=f"capability-{c.span_id}",
            rule="capability: call-granularity scope check",
            inputs=[c.span_id],
            output={"in_scope": c.in_scope, "failed": list(c.failed_dimensions)},
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
        inputs=[[a.qid for a in answers], verified],
        output=completeness.summary(),
    )
    tracer.record_action("assess_completeness", output=completeness.summary())

    # 8. A model-suggested association, recorded ONLY as an unverified lead: the
    #    external recipient might be the principal's own alias. It is a lead to
    #    verify, never an evidential edge on the model's authority (companion D.3).
    ledger.record_lead(
        output_id="lead-external-recipient-alias",
        rule="model-suggested correlation during reconstruction",
        inputs=[{"recipient": EXTERNAL_RECIPIENT, "principal": PRINCIPAL_ID}],
        suggestion={
            "association": (
                f"{EXTERNAL_RECIPIENT} may be a personal alias of {PRINCIPAL_ID}"
            )
        },
        model_invocation="assistant-model (optional aid); output is a lead only",
    )
    tracer.record_action(
        "record_lead",
        note="model-suggested association recorded as an unverified lead only",
    )

    # 9. Build the report, then witness the self-trace head with the same W.
    tracer.record_action("build_report")
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
    out.append("per-question classification:")
    for qid in sorted(a.completeness.per_question):
        out.append(f"    {qid}: {a.completeness.per_question[qid]}")
    if a.completeness.named_gaps:
        out.append("named gaps:")
        for qid, gap in a.completeness.named_gaps:
            out.append(f"    {qid}: {gap.party} / {gap.data_class}")
    out.append(f"case sufficiency: {a.completeness.case_sufficiency}")
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
    out.append("TRANSFORMATION LEDGER")
    out.append(_line())
    out.append(
        f"{len(a.ledger)} records, each binding inputs by hash to a derived "
        "output and the code version that produced it (companion D.3)."
    )
    out.append("")

    # Self-instrumentation
    out.append(_line())
    out.append("SELF-INSTRUMENTATION (forensic-by-design about itself)")
    out.append(_line())
    out.append(
        f"{len(a.tracer.spans)} of the tool's own actions were emitted as DCFP "
        "spans in a separate hash chain, witnessed by the same W (companion D.3)."
    )
    out.append(f"self-trace chain head: {a.tracer.chain.head.hex()}")
    out.append("")

    # Six dimensions
    out.append(_line())
    out.append("RELIABILITY AND ADMISSIBILITY DIMENSIONS (companion B Phase 7)")
    out.append(_line())
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
         "The witnessed hash chain establishes record integrity and independent "
         "attestation (here a development stand-in). Authenticity, provenance "
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
