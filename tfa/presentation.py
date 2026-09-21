"""Compact terminal and Mermaid views for the four-step demo (companion D.4)."""
from __future__ import annotations

from .report import Analysis


def graph_text(a: Analysis) -> str:
    lines = ["DELEGATION CHAIN - typed relations with source spans",
             "Verified means record integrity, not proof of the asserted facts."]
    for edge in a.graph.edges:
        lines.append(f"{edge.source} --{edge.edge_type.value}--> {edge.target}")
        lines.append(f"  source: {', '.join(edge.source_artefact)} | {edge.integrity_status.value} | "
                     f"{edge.observation.value} | confidence: {edge.confidence.value}")
    for segment in a.episode.missing_segments:
        lines.append(f"GAP: {segment.party} | {segment.data_class}")
    return "\n".join(lines) + "\n"


def graph_mermaid(a: Analysis) -> str:
    # Numeric node identifiers and HTML entities prevent labels becoming syntax.
    def label(value):
        return str(value).replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', ' ')
    ids = {node_id: f"n{i}" for i, node_id in enumerate(a.graph.nodes)}
    lines = ["flowchart LR"]
    for node in a.graph.nodes.values():
        lines.append(f'  {ids[node.node_id]}["{label(node.node_id)}"]')
    for edge in a.graph.edges:
        text = f"{edge.edge_type.value}: {', '.join(edge.source_artefact)}"
        lines.append(f'  {ids[edge.source]} -->|"{label(text)}"| {ids[edge.target]}')
    for i, segment in enumerate(a.episode.missing_segments):
        lines.append(f'  gap{i}["MISSING: {label(segment.party)} - {label(segment.data_class)}"]')
        lines.append(f'  style gap{i} stroke:#aa5500,stroke-dasharray: 5 5')
    return "\n".join(lines) + "\n"


def demo_step(a: Analysis, step: int, preserved: bool = False, package: str = "") -> str:
    if step == 1:
        return ("1 / INGEST AND VERIFY\n"
                + ("Verified original receipts and anchors from the preserved bundle.\n" if preserved
                   else "Simulated capture: raw spans were newly sealed at ingestion.\n")
                + f"Trace: {a.episode.trace_id} | spans: {len(a.episode.spans)}\n"
                + f"Integrity: {a.verification.summary()}\nHead: {a.chain.head.hex()}\n"
                + f"Anchors: {len(a.anchors)}; final span covered.\n"
                + "Development witness only. Integrity does not establish completeness or truth.\n")
    if step == 2:
        planes = "\n".join(f"  {p.value}: {len(a.projection.spans_in(p))} spans"
                           for p in a.projection.by_plane)
        return "2 / RECONSTRUCT\n" + graph_text(a) + "FIVE PLANES\n" + planes + "\n"
    if step == 3:
        lines = ["3 / ANSWER THE SEVEN QUESTIONS"]
        for answer in a.answers:
            lines += [f"{answer.qid}. {answer.question} [{answer.classification.value}]",
                      f"  {answer.value}"]
            if answer.gap:
                lines.append(f"  GAP: {answer.gap.party} | {answer.gap.data_class}")
        lines.append("CALL SCOPE")
        for check in a.capability_checks:
            lines.append(f"  {check.tool}: {'IN SCOPE' if check.in_scope else 'OUT OF SCOPE'} - {check.reason}")
        return "\n".join(lines) + "\n"
    return ("4 / PRODUCE THE PACKAGE\n"
            + (f"Sealed bundle: {package}\n" if package else
               "Readiness report available. Use --bundle FILE to seal and export it.\n")
            + "Six declared dimensions: methodology, error rate, peer review, general acceptance,\n"
            + "forensic reproducibility, and custody/record integrity.\n"
            + "No measured error rate, judicial validation or general acceptance is claimed.\n"
            + "Bundle binds evidence, certificates, graph, answers, ledger, self-trace and report.\n"
            + "Verify with --verify-bundle FILE; repeat the analysis with --reproduce FILE.\n"
            + "The local witness uses a public demo key; it is not an independent attestation.\n")
