# Extraction label audit

Status: development audit; annotations and runtime unchanged.

## Frozen checkpoint

Full evaluation:
- Agent strict successes: 30/36.
- Fixed workflow strict successes: 30/36.
- Agent model calls: 165.
- Fixed workflow model calls: 33.
- Invalid decisions: 3 for each model workflow.
- Regression tests: 143 passed.
- Source files remained unchanged during evaluation.
- Existing all-success release gate: blocked.

Evaluation directory:
artifacts/release-check-20261001T115043603996Z

The fixed workflow matched agent accuracy with fewer model calls.
This evaluation does not demonstrate an orchestration advantage.

## Candidate coverage experiment

Across labeled non-null components:
- Identifier-based candidate coverage: 8/9.
- Identifier plus development terminology coverage: 9/9.
- Candidate count increased from 9 to 18.

Candidate coverage is not selection accuracy.
Terminology expansion is not enabled in production extraction.

## Observed contract questions

| Case | Observation | Required review |
| --- | --- | --- |
| WO-01 | Gold selects brg, while BRG-204 is also available in the action | Decide which supported mention the component contract prefers |
| WO-01 | Gold problem excludes brg; model includes it | Apply a consistent component/condition separation rule |
| WO-01 and WO-02 | Gold actions include terminal periods | Compare with the proposed punctuation-excluding v2 rule |
| Release action labels | Comparable actions exclude terminal periods | Confirm a uniform annotation convention |
| RL-07 | Compressor appears in source but gold component is null | Determine whether this is an asset name rather than a maintained subcomponent |
| RL-07 | Model problem includes cause unknown; gold excludes it | Distinguish condition evidence from independent cause commentary |

These observations identify review questions. They do not automatically
establish that an existing label is incorrect.

## Decisions

- Keep existing demo and release annotations unchanged.
- Keep existing strict scoring and budgets unchanged.
- Keep vocabulary normalization separate from component recognition.
- Preserve the 30/36 implementation as the comparison checkpoint.
- Treat terminology expansion as an optional experiment.
- Review the proposed v2 contract before revising annotations.
- Report any future v2 evaluation separately from v1.

## Limits

All currently inspected synthetic cases are exposed development data.
Three repeated trials demonstrate consistency under the tested setup,
not performance on independent examples.

The existing vocabulary stores normalization mappings and confidence.
It does not contain component-role annotations and must not be treated
as a component classification resource.