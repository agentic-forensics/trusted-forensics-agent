# Trusted Forensic Agent (TFA) - DCFP reference implementation

An open-source reference implementation of the **Delegation-Chain Forensic Profile (DCFP)**: the
integrity layer and the seven-question delegation-chain reconstruction over OpenTelemetry-shaped
GenAI spans, demonstrated on a synthetic trace.

It accompanies the paper *Investigating Agentic Crime: A Forensic Model and Method* (the companion
to *No Human at the Keyboard: Agentic Cybercrime and the Forensic Frontier*). Those papers are the
authoritative specification of the model; this code expresses it in operational form so a reader can
run it end to end on a worked episode and inspect every step.

## Status

Work in progress. This is a **reference, not a product**. The repository is being built out module
by module against the model in `docs/`. Scope, limitations and the honesty notes below are stated up
front and will be expanded as the implementation lands.

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

## Honesty notes

- This is a reference implementation, not a product. There are **no measured error rates and no
  claim of general acceptance** - the field does not yet have these.
- The integrity layer secures **record integrity** and provides an **independent attestation** of it.
  It does not make a nondeterministic system reproducible, establish why the system acted, prove the
  emitter reported faithfully, or prove that omitted events did not occur. **Integrity is a separate
  property from completeness.**
- The bundled witness is a **development stand-in**, not an independent third party. A real
  deployment requires a witness that is independently subpoenable.
- The generated report is an **admissibility-readiness** report. It enumerates limitations and gaps
  and makes **no guarantee** of admission, accuracy or completeness.

## Requirements

Python standard library only. No third-party runtime dependencies. Deterministic; SHA-256.

## Licence

Code is licensed under the [Apache License 2.0](LICENSE). The accompanying papers
are published separately under CC BY 4.0.
