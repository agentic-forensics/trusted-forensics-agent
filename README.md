# Trusted Forensic Agent (TFA) - DCFP reference implementation

An open-source reference implementation of the **Delegation-Chain Forensic Profile (DCFP)**: the
integrity layer and the seven-question delegation-chain reconstruction over OpenTelemetry-shaped
GenAI spans, demonstrated on a synthetic trace.

It accompanies the paper *Investigating Agentic Crime: A Forensic Model and Method* (the companion
to *No Human at the Keyboard: Agentic Cybercrime and the Forensic Frontier*). Those papers are the
authoritative specification of the model; this code expresses it in operational form so a reader can
run it end to end on a worked episode and inspect every step.

## Status

The v1 scope is implemented and demonstrated on the synthetic trace, with every acceptance criterion
covered by a test. This is a **reference, not a product**: clarity and traceability to the model
matter more than performance or breadth, and the limitations below are stated plainly rather than
designed around.

## Quick start

Requires Python 3.9 or newer. No installation and no third-party dependencies.

```sh
# Run the model end to end on the synthetic trace and print the report.
python -m tfa

# Machine-readable summary instead of the text report.
python -m tfa --format json

# Demonstrate tamper-evidence: alter one stored span after witnessing, and watch
# verification detect it, localise it, and fail closed (non-zero exit).
python -m tfa --tamper 3

# Run the two worked cases the companion contrasts on the number of providers.
# One provider holds the conversation, the model calls and the tool calls, so
# most of the seven questions resolve from a single vendor's records.
python -m tfa --scenario single
# Execution is on one provider and the analysis is on a second whose records were
# not obtained; that segment is declared as a missing segment, so Q2 and Q6 are
# partial and the report names the party that holds the missing evidence.
python -m tfa --scenario cross

# Run the tests.
python -m unittest discover -s tests
```

The generated report, a JSON summary and the synthetic trace itself are also committed under
[`examples/`](examples/) so they can be read without running anything.

## For investigators: using this in the real world

This is a reference, not a deployable forensic product: it does not reach live providers, issue
preservation demands or score anomalies (see *What this is (and is not)* below). What it gives a
practitioner is a working, inspectable model of the method - and there are several concrete ways to
put it to work today.

- **Rehearse the reconstruction before an incident.** Run `python -m tfa` and read the report top to
  bottom. It walks a full delegation-chain reconstruction - the seven questions, the five planes, the
  integrity check, a boundary-subversion finding and a named gap - on a worked case. It is a good way
  to brief a DFIR team or a prosecutor on what an agentic case actually looks like, and to rehearse
  Phase 5 (reconstruction) while it is cheap.

- **Turn the seven questions into a preservation and subpoena checklist.** The report shows, for each
  question, which evidence answers it and which party holds it - and, where it cannot be answered, a
  *named gap* stating the party and data class that would close it. That is a ready-made list of what
  to demand and from whom. Preserve the artefacts that fragment first (prompt and transcript,
  memory and state, the cross-provider join) ahead of everything else.

- **Run your own episode through it.** Shape your collected evidence - provider audit logs, OTel
  spans, tool and connector logs, identity records - into the same span form as
  [`examples/synthetic_trace.json`](examples/synthetic_trace.json), then point the tool at it:

  ```sh
  python -m tfa --trace mycase.json
  python -m tfa --trace mycase.json --format json --out mycase-report.json
  ```

  Hand-written fixtures are a supported input; the synthetic trace is just one such fixture. To work
  with the results in code, `tfa.ingest.load_trace(path)` returns an episode you can pass straight to
  `analyse` and `render_report`.

- **Test an agent's authority.** Encode the agent's real capability certificate (tools, operations,
  targets, purposes, argument constraints) and let the call-granularity check flag any call that
  exceeds it as boundary subversion. Matching a tool name is never enough; the check looks at the
  whole call.

- **Guard against wrongful attribution.** Q4 deliberately reports *thin* attribution - the identity
  the action ran under - and says in plain terms that this is not evidence the principal directed it.
  Q7 compares the agent's stated intent against what actually ran downstream. Together they are the
  practical defence against charging a person for their agent's act.

- **Produce a defensible readiness report.** The report structure - supporting evidence, named gaps,
  three-sense completeness, the six reliability and admissibility dimensions, and stated limitations -
  is a template for documenting a real reconstruction fully, including what you could not
  establish.

- **Keep your own analysis reviewable.** The transformation ledger and the self-trace show how to
  record every derived object by hash and code version, and how to witness your own tool's conduct,
  so another examiner can repeat your analysis and challenge it.

**What it will not do for you.** It will not connect to a model provider or pull live telemetry; it
will not issue a legal hold, subpoena or any operative preservation demand; it does no machine
learning or anomaly scoring; and it reports no error rates, because the field has none yet. Use it
alongside your own authority, process and counsel, not in place of them.

## What the model does

- **Episode and spans (A.2).** An episode is a finite, partially ordered set of OTel GenAI spans;
  order is recovered from parentage, links and correlated timestamps, never from a single global
  clock.
- **Integrity layer (A.2, A.6).** A hash chain over the canonicalised span stream, with a pluggable
  witness. A tamper is detected, localised, and verification fails closed. Integrity is a separate
  property from completeness.
- **Five-plane projection (A.4).** Each span is projected to the plane(s) it furnishes: Brain, DNA,
  Memory, Ears and Mouth, Hands.
- **Delegation-chain graph (A.2, A.3).** Typed, evidence-backed edges. Parentage is technical
  correlation only; delegation and authority edges require identity, authorisation, approval or
  policy evidence. The agent-to-model edge is an invocation, not a decision.
- **Seven questions (A.5).** Each resolved from the spans with a per-question classification and
  either evidence or a named gap. Q5 (auto-approval) is recorded as a named gap when its approval
  record is absent, never read as auto-approval.
- **Capability check (A.2, A.3).** Each tool call is checked at call granularity across tool,
  operation, arguments, target and purpose together; an out-of-scope call is boundary subversion.
- **Completeness in three senses (A.2).** Schema, evidential and case sufficiency, the last
  represented rather than assessed.
- **Transformation ledger (D.3).** Every derived object records its inputs by hash, code version,
  rule, any model invocation and its output hash. A model-suggested association is a lead, never an
  edge on the model's authority alone.
- **Self-instrumentation (D.3).** The tool emits its own actions as DCFP spans in a separate hash
  chain, witnessed by the same W.

## Repository layout

```
tfa/
  model.py         span, plane, node and edge types; the partial-order container   (A.2, A.4)
  canon.py         deterministic canonical serialisation; SHA-256 helpers          (A.2)
  integrity.py     hash chain, append-only receipts, Witness, verification         (A.2, A.6)
  ingest.py        build the partial order from parentage and effect links         (A.2)
  planes.py        the five-plane projection pi                                     (A.4)
  graph.py         the delegation-chain graph with the delegation-edge discipline   (A.2, A.3)
  questions.py     the seven-question resolvers with named-gap discipline           (A.5)
  capability.py    the capability certificate and the call-granularity check        (A.2, A.3)
  completeness.py  completeness in three senses                                     (A.2)
  transform.py     the transformation-record ledger                                 (D.3)
  selftrace.py     the tool's own witnessed DCFP spans                              (D.3)
  synth.py         the synthetic episode                                            (D.4)
  report.py        end-to-end analysis and the admissibility-readiness report       (B7, D.2)
  cli.py           the command-line entry point
examples/          the synthetic trace and its expected report and summary
tests/             one or more tests per acceptance criterion
```

## Acceptance criteria

Each criterion from the build brief is demonstrated on the synthetic trace and covered by a test.

| # | Criterion | Where |
|---|-----------|-------|
| 1 | Ingest, partial order, five planes | `test_ingest`, `test_planes` |
| 2 | Typed evidence-backed G; agent-to-model is an invocation; no delegation from parentage | `test_graph` |
| 3 | Q1-Q7 answered; Q5 recorded as a named gap, not guessed | `test_questions` |
| 4 | Chain verified against anchors; a mutated span detected and localised; fails closed | `test_integrity`, `test_report` |
| 5 | Out-of-scope external send flagged as boundary subversion | `test_capability` |
| 6 | Completeness in three senses with a per-question label | `test_completeness` |
| 7 | A ledger entry per derived object; one model-suggested association as an unverified lead | `test_transform`, `test_report` |
| 8 | The tool's own actions emitted as DCFP spans, witnessed by the same W | `test_selftrace` |
| 9 | An admissibility-readiness report listing evidence, named gaps and limitations, no guarantee | `test_report` |

## What this is (and is not)

In scope (v1): a data model for OTel GenAI spans; deterministic canonicalisation and a hash chain
with a pluggable witness interface; partial-order ingest; the five-plane projection; the
delegation-chain graph with typed, evidence-backed edges; the seven-question resolvers with named-gap
discipline; the capability-certificate check at call granularity; completeness in three senses; a
transformation-record ledger; an admissibility-readiness report; self-instrumentation; a synthetic
trace generator; a command-line entry point; and tests.

Out of scope, by design: real provider connectors or live telemetry; issuing any real preservation
request, legal hold or subpoena; anomaly detection beyond simple declared rule flags; measured error
rates or claims of general acceptance; any GUI, service, or scale/performance work.

## Limitations and caveats

- This is a reference implementation, not a product. There are **no measured error rates and no
  claim of general acceptance** - the field does not yet have these.
- The integrity layer secures **record integrity** and provides an **independent attestation** of it.
  It does not make a nondeterministic system reproducible, establish why the system acted, prove the
  emitter reported faithfully, or prove that omitted events did not occur. **Integrity is a separate
  property from completeness**: one cannot protect through a hash chain what was never written.
- The integrity layer resists a specific adversary. It makes tampering evident where a compromised
  agent or application emits into an uncompromised, independent collector, or where an operator would later
  alter the stored record. It is **weaker against a collector compromised before the witness is
  reached, against operator-witness collusion, and against clock manipulation**, which is why a real
  witness must be independently subpoenable.
- The bundled witness is a **development stand-in**, not an independent third party. Every anchor it
  issues says so. A real deployment requires a witness that is independently subpoenable of the
  operator.
- The generated report is an **admissibility-readiness** report. It enumerates limitations and gaps
  and makes **no guarantee** of admission, accuracy or completeness.

## Requirements

Python standard library only. No third-party runtime dependencies. Deterministic; SHA-256.

## Licence

Code is licensed under the [Apache License 2.0](LICENSE). The accompanying papers
are published separately under CC BY 4.0.
