# Version 0.3 roadmap

## Delivered

The Python 3.11 foundation now includes company CSV profiles, raw source
preservation, explicit normalization policy, local LangGraph tool selection,
workflow completion gates, conservative classification constraints, field-level
review/correction, source-bound SQLite reuse, counted reviewed briefs, client
request termination, and paired workflow comparisons with external scoring labels.

The frozen public test baseline is retained. A training-only vocabulary learner
and validation-split development comparison address limited normalization coverage.
The vocabulary is optional; corpus transfer still needs testing.

## Next decisive gates

| Work | Required evidence |
| --- | --- |
| Live model comparison | Actual selected backend; deterministic vs fixed workflow vs agent; identical source/scope and declared budgets; task/field/count scores and failure traces |
| Semantic classification | Reviewed raw narratives/action states; abstention, negation, multiple-object and partial-action cases; source validity and classification accuracy reported separately |
| Real history workflow | Permitted histories with stable IDs/dates, relevant-record labels, verified counting semantics; review-time and missed-record comparison |
| Vocabulary transfer | Fresh organization/equipment holdout; preserve identifiers and negation; no test-informed policy tuning presented as independent confirmation |
| User delivery | Windows execution, actual browser/installer/import usability, multilingual measurements where supported |
| Operational scaling | Token-aware context budgeting, large-record handling, checkpoint resume, measured file/record limits |
| Commercial pilot | Repeat useful reviews and willingness to pay; authorized case study with measured outcomes and limitations |

One bounded agent remains sufficient. Additional agents, automatic equipment
control, failure prediction, and broad enterprise connectors are not needed to
prove this workflow's value. Broader applicability follows independent results
in additional organizations and domains.

Current design checks workflow completeness, not semantic task truth. The
comparison oracle and human field review are deliberately separate from model
choices. Local request termination stops the client process; it does not guarantee
server-side generation cancellation or hard real-time bounds for all local tools.
