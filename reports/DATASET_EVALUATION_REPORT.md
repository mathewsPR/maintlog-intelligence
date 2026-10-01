# Maintenance-log intelligence: public dataset evaluation

Run UTC: 2026-09-30T14:08:19.642466+00:00. Runtime: Python 3.11.16.

## Assessment

This run evaluates the frozen six-entry dictionary baseline, not an agent. It compares against returning input unchanged. Dataset scores establish normalization behavior only; they do not validate a full maintenance application.

The dictionary corrects only 11 of 1182 required lexical changes (0.93% correction recall), with 12.79% correction precision. It preserves the labeled identifier source units, but its coverage and word-form choices are inadequate for general maintenance-text normalization. A working CSV/search demo is not evidence of useful text understanding.

## MaintNorm: measured normalization results

Primary table uses casefold comparison to separate lexical corrections from capitalization. Any target unit containing <id>, <num>, <date>, or <sensitive> is excluded from lexical scoring. Empty targets/insertions remain eligible. Strict case-sensitive scores and all denominators are in results.json.

| Scope | Test documents | Lexical units | Unchanged accuracy | Dictionary accuracy | Correction precision | Correction recall | Error reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Company A | 400 | 1602 | 76.09% | 76.40% | 6.49% | 1.31% | 1.31% |
| Company B | 400 | 1706 | 70.98% | 71.16% | 50.00% | 0.61% | 0.61% |
| Company C | 400 | 1823 | 83.32% | 83.49% | 100.00% | 0.99% | 0.99% |
| All nominal test splits | 1200 | 5131 | 76.96% | 77.18% | 12.79% | 0.93% | 0.93% |

Nominal correction counts: TP=11, FP=75, FN=1171. Required corrections=1182; predicted corrections=86.

Strict dictionary lexical-unit accuracy: 39.35%. Strict document exact accuracy: 11.08%. Casefold document exact accuracy: 39.58%.

Masked units excluded: 1180. Identifier units checked: 909; unchanged identifier units: 909 (100.00%). This checks obfuscated source-unit preservation by the dictionary, not confidentiality or real asset-history linkage.

## Split overlap and interpretation

| Company | Train | Validation | Test | Test rows also in any train/validation | Within-test duplicate occurrences | Globally clean test documents |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 3200 | 400 | 400 | 1 | 0 | 399 |
| B | 3200 | 400 | 400 | 21 | 0 | 379 |
| C | 3200 | 400 | 400 | 1 | 0 | 399 |

Exclude exact source documents present in any company train/val split; deduplicate remaining test source documents across companies in A/B/C order. Labels are not used for filtering. Near duplicates are not removed.

On the clean subset (1177 documents; 5029 lexical units), dictionary accuracy=77.79%, correction precision=12.79%, correction recall=0.98%. This is a supplementary project-specific subset, not a replacement official split.

The dictionary was authored before these files were downloaded and was not tuned during this run. Changes informed by these test errors must be evaluated on a fresh held-out set. Exact-duplicate filtering does not remove near duplicates. Mining-equipment text is a domain-transfer test for the pump demo.

## Frequent dictionary failures

| Source unit | Reference | Prediction | Count |
| --- | --- | --- | ---: |
| REPL | replace | replaced | 71 |
| Mech | mechanical | Mech | 56 |
| & | and | & | 49 |
| Insp | inspection | Insp | 31 |
| Svce | service | Svce | 26 |
| C/O | change out | C/O | 25 |
| u/s | unserviceable | u/s | 25 |
| POS | position | POS | 22 |
| RH | right hand | RH | 22 |
| LH | left hand | LH | 20 |

A six-entry dictionary has deliberately limited coverage. Wrong expansions and tense/word-form mismatches are real errors under this task. High accuracy on unchanged units can hide poor correction recall; inspect both. Model-based normalization should be compared with this baseline under identical scoring.

## MaintIE: measured schema audit, extraction not evaluated

Actual downloaded gold file: 1076 records; 6119 tokens; 3397 entities; 2341 relations. All spans and relation indices passed schema validation. Duplicate text occurrences beyond the first: 1.

| Top-level entity class | Annotated entities |
| --- | ---: |
| Activity | 784 |
| PhysicalObject | 1994 |
| Process | 146 |
| Property | 35 |
| State | 438 |

Extraction precision, recall, and F1 are unavailable: this evaluation runs no model or extraction predictions. The separate agent prototype can propose source spans; that capability has not been scored on this corpus. The gold corpus can support selected entity/relation tests after a reviewed mapping; its already normalized/sanitized text does not test raw-text normalization or real chronology. Published README counts differ in different sections; this report uses the measured downloaded file count. A split must group duplicate texts and check cross-corpus overlap before prompts or models are tuned.

## Capability coverage and release decision

| Capability | Evidence in this run | Status |
| --- | --- | --- |
| Dictionary normalization | MaintNorm reference targets and unchanged-input baseline | Measured |
| Identifier preservation | MaintNorm source units labeled with identifier masks | Measured for dictionary only |
| Narrative field extraction | MaintIE schema and annotations audited | Prototype separate; no model score |
| Historical retrieval relevance | No query relevance labels loaded | Not measured |
| Real recurring issues | No verified asset/event histories loaded | Not measured |
| LangGraph agent behavior | Separate replay/behavioral tests; no model calls in this run | Live model quality not measured |
| MaintNet transfer evaluation | No snapshot/access/license audit completed | Not run |

This is an evaluated software baseline, not a production-ready agent. Close the real-data/application gate with a representative authorized sample. Evaluate the bounded agent and compare it with a fixed model workflow and the deterministic baseline. Evaluate source-span support, abstention, malformed outputs, retrieval relevance, citation/count validity, latency, cost, and tool budgets. Do not use invented asset identities/dates to claim public-data recurrence performance.

## Reproduction and provenance

```bash
export PYTHONPATH=src
python -m unittest discover -s tests -v
python -m maintlog.evaluation --data-root data/public --output-dir reports
```

Use Python 3.11 only. Bundled source snapshots are checked against manifest.json before scoring. results.json contains all denominators, task definitions, hashes, versions, limits, and descriptive document-accuracy intervals. No model/API calls or training occurred; there is no model cost or agent latency measurement.

Sources and MIT notices:

- MaintNorm: https://github.com/nlp-tlp/maintnorm
- Dataset mirror: https://huggingface.co/datasets/nlp-tlp/MaintNorm
- MaintIE: https://github.com/nlp-tlp/maintie
- Dataset-local LICENSE.md files are included with the source snapshots.


## Version 0.3 development addendum — 2026-09-30

The sections above are the reproduced frozen baseline evaluation. This addendum
covers separate development measurements; it does not replace the nominal test
results or score the live agent. Re-running the baseline evaluator regenerates
the baseline report; the separate JSON artifacts remain the development record.

A conservative vocabulary was fitted using 9,600 MaintNorm **training** documents
with minimum support five and agreement at least 98%, yielding 84 entries.
Development scoring used 1,200 **validation** documents and 5,091 lexical units,
with 1,235 privacy-mask units excluded from lexical accuracy. The default noun
aliases avoid converting action abbreviations into performed-action tense.

| Policy | Validation lexical accuracy | Correction TP / FP / FN | Correction precision | Correction recall |
| --- | ---: | ---: | ---: | ---: |
| Unchanged input | 76.39% | 0 / 0 / 1,202 | Undefined (no changes) | 0.00% |
| Frozen dictionary_v0 | 76.61% | 11 / 59 / 1,191 | 15.71% | 0.92% |
| Default noun_alias_v1 | 76.61% | 11 / 0 / 1,191 | 100.00% (11 changes) | 0.92% |
| Optional train_lexicon_v1 | 86.11% | 496 / 3 / 706 | 99.40% | 41.26% |

All 1,235 masked source units, including 914 identifier-labeled units, were
preserved under each policy in this validation run. Lexicon entries come only
from training annotations, but policy design followed inspection of earlier test
errors. These are **development diagnostics, not fresh independent holdout
results**. They do not establish accuracy on another company, extraction accuracy,
or useful agent performance. Coverage remains incomplete: the learned policy
misses 706 of 1,202 required corrections. The opt-in vocabulary changes both query
and document tokens and is bound by a hash; original source text is retained.

Reproduce with Python 3.11:

```bash
python -m maintlog.normalization_probe --output reports/NORMALIZATION_DEVELOPMENT.json
maintlog-compare data/demo/comparison_cases.json --backend replay --trials 3 --output reports/WORKFLOW_COMPARISON.json
```

`NORMALIZATION_DEVELOPMENT.json` includes exact denominators, fitted entries,
source manifest and policy hash. `WORKFLOW_COMPARISON.json` records 27 synthetic
replay outcomes across deterministic, fixed-model and agent-shaped workflows.
The bearing-history case deliberately requires six field spans; the deterministic
workflow predicts none, whereas the two handwritten extraction fixtures supply
them. This verifies the scorer and workflow mechanics, not an agent advantage.
All three workflows return the labeled record sets on these fixtures. Three
identical replay trials are not independent model observations. MaintIE remains
a schema audit only: no model extraction predictions were evaluated.

Delivery validation: 113 tests passed on Python 3.11.16 with LangGraph 1.2.12;
Ruff lint/format checks passed; a fresh locked version 0.3 installation exercised
the installed agent and comparison CLIs. Client HTTP timeout termination and
field correction/download/import/reuse were exercised with local/DOM fixtures.
Live LLM, GPU, Windows and actual browser interaction were not executed.
