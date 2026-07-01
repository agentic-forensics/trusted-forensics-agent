## What this changes

A short description of the change and why.

## Companion section

The section(s) of the model this touches (for example "companion A.6 integrity
layer"). If the papers are silent, note how the point was resolved.

## Checklist

- [ ] Standard library only; deterministic; SHA-256.
- [ ] British English; single hyphens only; docstrings cite the companion section.
- [ ] Tests pass: `python -m unittest discover -s tests`.
- [ ] If reconstruction or the report changed, `examples/synthetic_report.txt` was
      regenerated and the diff reviewed.
- [ ] No overclaiming; integrity is not represented as completeness; any model aid
      produces leads, not edges.
- [ ] Effect on the acceptance criteria noted (if any).
