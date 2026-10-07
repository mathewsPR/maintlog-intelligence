# Evaluation and limits

Run each layer separately. Do not describe replay as measured model intelligence.

## Default CI: small synthetic mechanics

```bash
maintlog-compare data/demo/comparison_cases.json --backend replay --trials 3 --output artifacts/ci-comparison.json
python scripts/check_replay_report.py artifacts/ci-comparison.json data/demo/comparison_cases.json --trials 3
```

The gate checks that every expected case/workflow/trial is present, operationally
complete, and has the expected record set. Fixed and agent replay paths must also
pass the declared task labels. The deterministic baseline is not expected to
extract model fields. Repeating a fixture does not add independent model trials.

## Public dataset audit: required manual check for relevant changes

For ingestion, normalization, vocabulary, dataset, or evaluation changes:

```bash
python -m maintlog.evaluation --data-root data/public --output-dir artifacts/public-evaluation
```

Use the permitted pinned inputs and their existing notices. Record source hashes,
split, normalization policy, correction precision/recall, lexical accuracy, and
identifier-preservation measures. Report exclusions and inspected/tuned splits.
Large or private inputs are excluded from default CI.

## Live comparison: separate release evidence

With the existing llama.cpp server running and accepting model `qwen35-4b`:

```bash
maintlog-compare data/demo/comparison_cases.json --backend local --base-url http://127.0.0.1:8081/v1 --model qwen35-4b --trials 3 --max-steps 20 --timeout 120 --output artifacts/local-comparison.json
```

This tests a real model on development fixtures. Independent acceptance needs
separately labeled, permitted cases not used to tune prompts or recovery rules.
Use the same sources, scopes, policies, and declared budgets across methods.
Keep labels outside model context and record failures rather than dropping them.

| Metric | Interpretation |
| --- | --- |
| workflow_complete | Operational completion only |
| exact_record_set; record precision/recall | Match to declared relevant records |
| field precision/recall; status accuracy | Match to declared extraction labels |
| aggregate_correct; labeled_task_success | Declared count/task correctness |
| failures; invalid decisions; abstention | Reliability and inability to answer |
| latency; request attempts; reported tokens | Measured resource use and missing usage |

Retain denominators, per-case results, model/quantization/server configuration,
code and dataset hashes, prompts or their hashes, budgets, and scorer version.
For repeated live trials, report variation across cases; repeated runs of a small
development set do not establish broad generalization. Cost is unknown unless
actual usage and applicable pricing are available.

Known limits: source-valid excerpts can still be classified incorrectly; a record
count is not a failure-event count; exposed FAA histories are development data;
commercial value and complete-answer accuracy are not established by CI.
Keep current measured results and limitations in their identified run reports.

## Recorded operational results

The three uploaded summaries from 6 October 2026 contain actual prior-run evidence.
They use protocol `faa-history-operational-v3-token-log`, with 100 agent and 100
fixed-workflow runs per batch. All planned outputs were saved. This table reports
operational outcomes, not answer accuracy:

| Uploaded run summary | Agent completed | Fixed completed | Saved / planned |
| --- | --- | --- | --- |
| `summary(20261006-122044).json` | 66/100 (66%) | 83/100 (83%) | 200/200 |
| `summary(20261006-125614).json` | 74/100 (74%) | 83/100 (83%) | 200/200 |
| `summary(20261006-135543).json` | 81/100 (81%) | 83/100 (83%) | 200/200 |

Latest batch (`summary(20261006-135543).json`):

| Outcome | Agent | Fixed |
| --- | --- | --- |
| ready_for_review | 69 | 71 |
| no_matches | 12 | 12 |
| failed | 16 | 15 |
| context_limit | 3 | 2 |
| Completed, as reported | 81 | 83 |

Across both workflows, the latest summary records 882 requests started and 882
responses received, zero transport failures, zero unfinished requests, and zero
responses without usage. Known totals are 1,400,222 input tokens and 70,218 output
tokens: 1,470,440 total. Cached input (719,210) is a subset of input, not additional
tokens. These counts include responses rejected later by decision validation.

All three summaries explicitly set `semantic_accuracy` and `complete_task_success`
to null. Completion includes no-match outcomes, so it does not prove retrieval or
answer correctness. Saving all outputs means the batch finished; it does not mean
all workflows passed. These exposed FAA histories are development evaluation,
not evidence of independent held-out accuracy or agent superiority.

The supplied `manifest(2).json` records Python 3.11.9, model alias `qwen35-4b`,
100 histories, one trial per workflow, 20 steps, 120 seconds, and a 10,000-character
working-context cap. It records component selection, boundary adaptation, and
focused status repair as enabled. The llama.cpp server response advertised
4096 context tokens, 4,205,751,296 parameters, and Q4_K Medium quantization.
The manifest explicitly warns that the alias does not prove model-file identity,
and that questions are source-derived without reviewed relevance/semantic labels.

Keep the matching code/source/candidate/runner hashes and manifest alongside each
summary. Configuration details for all three batches must be compared before
claiming a causal improvement. The summary interpretation itself
warns that the v2 step budget differs from an earlier 12-step batch.

See the [completed agent evaluation review](FINAL_AGENT_REVIEW_20261007.md).

Source integrity (SHA-256 of uploaded summary bytes):

- `summary(20261006-122044).json`: `1cadbfba7d349e13cea9666fa6f5aff39dcfd5ee538addf9d378862a70f21eb2`
- `summary(20261006-125614).json`: `8066465113a622896af60be2409c0684b4d2ad82c33801a8b8a07458a752456a`
- `summary(20261006-135543).json`: `13e381c0218a79d4d558c2fb5db076d775ee306330899544242fa5094ebb1553`

## Recorded packaging and coverage validation

The supplied Windows terminal log `Pasted text(20261006-131631).txt`, on branch
`fix/compact-agent-working-context`, reports:

- Coverage: 2,349 statements, 542 missed; 988 branches, 149 partial; total **75.76%**.
- Successful build of `maintlog_intelligence-0.3.0.tar.gz` and
  `maintlog_intelligence-0.3.0-py3-none-any.whl`.
- `twine check`: **PASSED** for both distributions.

This is actual prior-run evidence, not a result inferred from CI configuration.
The log does not include the associated unit-test execution/count, fresh-wheel
installation, security audit, or execution of the newly proposed workflow.
Do not turn build/metadata success into installation or production-readiness claims.

Additional source integrity:

- `manifest(2).json`: `1b0192df43e9642a11faf894ede5bc1b92a3549d68d19345d371eb8ddc9012cd`
- `Pasted text(20261006-131631).txt`: `be6e1aeb85f81d9403b42aa8afaadd6e2ecfdeb88902445794b9850153f96562`

The curated [validation JSON](../reports/RECORDED_VALIDATION.json) preserves these
metrics and source hashes without raw maintenance narratives. It is a derived
summary, not a substitute for the original reports and manifests.
