# Presentation demo

This four-minute terminal walkthrough follows the four steps on slide 16 of
`docs/deck/AMLUCS-2026-Agentic-Forensics.pdf`: verify the preserved record,
reconstruct the delegation chain, answer the seven questions, and produce a
sealed admissibility-readiness package. The [four-minute video](demos/trusted_forensic_agent_4min.mp4)
shows the complete demonstration without a voiceover.

Everything runs offline using Python 3.9 or later and the standard library.
The scenarios are synthetic illustrations. The cross-provider scenario is not
evidence from the Mexico investigation or another real incident. The witness
uses a publicly known demonstration key and provides no independent attestation:
someone holding the key can issue replacement seals. The demo shows detection
of changes against the original seal, not resistance to that key holder.

For an automatic walkthrough with pauses before each stage, run:

```sh
python3 scripts/run_demo.py --pause
```

The runner creates a fresh folder under `results/`, verifies the prepared
package, presents the four views, repeats the analysis, and demonstrates failure
on an altered copy. The manual commands below also show exporting the final
package as a separate presentation action.

## Prepare before presenting

Run from the repository root. Use a fresh output directory for each rehearsal:
bundle export deliberately refuses to overwrite an existing preserved bundle.

```sh
mkdir -p results/presentation
python3 -m tfa --bundle results/presentation/captured.bundle.json --out results/presentation/captured-report.txt
python3 -m tfa --verify-bundle results/presentation/captured.bundle.json
```

Preparation simulates capture and sealing of the mailbox fixture. During the
presentation, `--from-bundle` verifies these original receipts and anchors before
analysis. Loading a raw `--trace` instead would newly seal the input at ingestion;
it would not verify an earlier capture. Keep the source files unchanged between
preparation and reproduction: the bundle records their hashes.

## Four-minute sequence

| Time | Action | Point to show |
|---|---|---|
| 0:00-0:40 | Verify the preserved bundle | Final span is witnessed; the development witness is explicitly qualified. |
| 0:40-1:40 | Display the delegation chain | Typed relations, source spans, integrity labels and five views of one record. |
| 1:40-2:50 | Show answers, scope and named gaps | The mailbox email exceeds scope; Q4 is partial and Q5 is unavailable. The cross-provider example names Provider-B for Q2 and Q6. |
| 2:50-4:00 | Export, verify, reproduce and alter a copy | The actual report and supporting artefacts are bound into the package; verification rejects a changed report. |

### 1. Verify the record

```sh
python3 -m tfa --from-bundle results/presentation/captured.bundle.json --demo-step 1
```

### 2. Reconstruct the chain

```sh
python3 -m tfa --from-bundle results/presentation/captured.bundle.json --demo-step 2
```

The terminal view prints each relation with its source spans. For a separate
diagram, export Mermaid text and open it in a Mermaid-capable viewer:

```sh
python3 -m tfa --from-bundle results/presentation/captured.bundle.json --format mermaid --out results/presentation/chain.mmd
```

The optional diagram export is not needed during the four-minute sequence.

### 3. Answer the questions and expose the gaps

```sh
python3 -m tfa --from-bundle results/presentation/captured.bundle.json --demo-step 3
python3 -m tfa --scenario cross --demo-step 3
```

Do not read every answer aloud. Highlight the mailbox call's recipient and
purpose, the missing downstream identity and approval records, then the named
Provider-B gaps in the second fixture. An in-scope call does not establish that
an overall objective was lawful. The injected content is recorded in the fixture;
the demonstration does not claim to detect prompt injection autonomously.

### 4. Produce and challenge the package

```sh
python3 -m tfa --from-bundle results/presentation/captured.bundle.json --demo-step 4 --bundle results/presentation/mailbox.bundle.json
python3 -m tfa --verify-bundle results/presentation/mailbox.bundle.json
python3 -m tfa --reproduce results/presentation/mailbox.bundle.json
```

The new package retains the original evidence receipts and anchors. Verification
checks its preserved seals. Reproduction separately reruns the versioned analysis
and compares conclusions, report, ledger and self-trace; it does not replay the
original agent's behaviour.

Create an altered copy, preserving the original package and its seals:

```sh
python3 - <<'PY'
import json
from pathlib import Path

source = Path("results/presentation/mailbox.bundle.json")
bundle = json.loads(source.read_text(encoding="utf-8"))
bundle["payload"]["report"] += "\nReport altered after sealing.\n"
with source.with_name("altered.bundle.json").open("x", encoding="utf-8") as stream:
    json.dump(bundle, stream, indent=2, ensure_ascii=False)
PY
python3 -m tfa --verify-bundle results/presentation/altered.bundle.json
```

The final command must print `BUNDLE VERIFICATION: FAIL`, identify the report
digest mismatch and exit with status 1. That is the expected successful tamper
demonstration. For the separate span-localisation example:

```sh
python3 -m tfa --tamper 3
```

This also intentionally exits with status 1 after identifying the altered span.
Neither demonstration proves completeness, source truth, human intent or
admissibility. The report states the six readiness dimensions and their limits.
