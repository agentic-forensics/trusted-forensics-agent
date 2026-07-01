# Contributing

Thank you for your interest in the Trusted Forensic Agent (TFA). This is a
reference implementation of the Delegation-Chain Forensic Profile (DCFP): its
purpose is to express the model in operational form so it can be examined
concretely, and faithfulness to the model and honesty about its limits matter
more than features.

Please read this short guide before opening an issue or a pull request.

## The specification governs

The accompanying papers - *Investigating Agentic Crime: A Forensic Model and
Method* and *No Human at the Keyboard* - are the authoritative specification.
Where code and the papers disagree, the papers govern. Where the model is silent,
please raise it for discussion rather than inventing behaviour.

## Non-negotiable constraints

These are what keep the implementation a trusted reference rather than a
convenient one. Changes that break them will not be merged.

- **Standard library only.** No third-party runtime dependencies. If you believe
  one is genuinely necessary, open an issue first.
- **Deterministic.** The synthetic trace must produce the same result on every
  run. SHA-256 is the hash throughout.
- **Integrity is not completeness.** Nothing in code or output may imply that
  tamper-evidence establishes completeness, causation or truth.
- **A model-suggested association is a lead, never an edge.** Any optional model
  aid records its output as an unverified lead; it is never promoted to an
  evidential edge on the model's authority alone.
- **Named-gap discipline.** An unanswerable question is recorded as a named gap
  (the party and data class that would close it), never silently dropped and
  never guessed.
- **Capability is checked at call granularity**, across tool, operation,
  arguments, target and purpose together.
- **Partial order, never a global clock.** Do not sort the whole episode by
  timestamp as if it were totally ordered.
- **Output language discipline.** The report is an admissibility-readiness
  report. It must enumerate limitations and gaps and must not claim
  admissibility, accuracy or completeness beyond what the data supports.
- **No overclaiming.** Do not fabricate benchmarks, accuracy figures or empirical
  claims. There are no measured error rates and no general acceptance yet.

## Style

- British English in prose, comments and the report. Single hyphens only, never
  em or en dashes.
- Keep each module small and mapped to a section of the companion paper. Comments
  and docstrings should cite the section they implement (for example
  "companion A.2 integrity layer").
- Match the naming and idiom of the surrounding code.

## Tests

Every acceptance criterion has at least one corresponding test under `tests/`.
Run the suite before opening a pull request:

```sh
python -m unittest discover -s tests -v
```

If you change the reconstruction or the report, the committed example under
`examples/synthetic_report.txt` will need regenerating (a test compares against
it). Regenerate it with:

```sh
python -m tfa --out examples/synthetic_report.txt
```

and review the diff carefully - an unexpected change there is a signal, not a
chore.

## Commits and pull requests

- Keep commits small and focused. Reference the companion section in the message
  where it applies.
- Describe what changed and why, and note any effect on the acceptance criteria
  or the honesty notes.
- CI runs the test suite across supported Python versions and exercises the
  end-to-end demo, including that tamper-evidence fails closed.

## Scope

Out of scope by design (see the README): real provider connectors or live
telemetry; issuing any real preservation request, legal hold or subpoena;
anomaly detection beyond simple declared rule flags; measured error rates or
claims of general acceptance; and any GUI, service, or scale/performance work.
Proposals in these areas are welcome as discussion, but will not be added to the
reference itself.
