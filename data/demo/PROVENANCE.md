# Synthetic pump-maintenance records

All twelve records were authored specifically for this starter on 2026-09-30.
They contain invented equipment identifiers, dates, symptoms, and actions.
No workplace records, MaintNorm, MaintNet, or existing evaluation dataset was
used to construct them. They may be reused with this starter, including in tests.

Purpose: exercise CSV ingestion, standalone abbreviation expansion, exact asset
identity, negative wording, unknown actions, and source-linked aggregates.
They do not establish product usefulness, model quality, failure prediction,
or generalization. They are development fixtures, not a held-out benchmark.

Blank action means no action is recorded, not that no action happened.
CSV evidence `csv_row` is a logical record row (header is row 1); a quoted
multiline field may occupy more than one physical file line.

## Version 0.2 narrative fixtures

`company_export.csv`, `company_profile.json`, and the version 0.2 `replay_*.json` files are
handwritten synthetic examples. No company/customer supplied them. The replay
files contain prewritten tool choices and source offsets; they do not come from
a model and must not be presented as measured agent intelligence. WO-01 describes
a planned action; WO-02 deliberately records unresolved vibration after a part
replacement. These examples exercise review semantics only.


## Version 0.3 comparison and review fixtures

All added `replay_*.json` files and `comparison_cases.json` are handwritten
synthetic development fixtures created on 2026-09-30. Labels describe invented
source records, exact spans and planned/completed wording. SHA-256 hashes bind
the comparison labels to the demo CSV/profile. Scoring labels are withheld from
model prompts. Replaying the same fixture three times verifies repeatable
mechanics; it does not create independent model observations or establish
agent superiority. Review corrections used for tests are synthetic human-review
fixtures and contain no real reviewer/customer data.

`reports/NORMALIZATION_DEVELOPMENT.json` is a separate public-data development
artifact: its vocabulary uses MaintNorm training annotations only; its metrics
use the supplied validation split. Policy design followed inspection of earlier
test errors, so it must not be described as fresh held-out generalization proof.
See the bundled public-data manifest and licenses for source revisions/notices.
