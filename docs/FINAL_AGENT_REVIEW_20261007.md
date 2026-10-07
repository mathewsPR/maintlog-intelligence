# Final CSV-agent evaluation review — 7 October 2026

## Decision

Freeze feature scope at CSV maintenance-log review for supervised use. The batch is complete and transport logging reconciles, but this is not evidence of production readiness or a passed live-model release gate. No runtime patch is supplied: the current implementation source and extraction contract were not included, and changing behavior from traces alone would be speculative.

## Evidence inspected

All 1,076 individual run files, plan.json, summary.json, and tokens.jsonl in the supplied archive were inspected programmatically. Outcome totals, tool-error counts, source-valid-span counts, and request/run identities were cross-checked. Representative traces were inspected for ready, recovered, abstained, failed, no-match, and clarification outcomes. No model calls or runtime tests were made during this review. The companion JSON records hashes and reproducible diagnostic counts; raw source narratives are excluded from this delivery.

The plan identifies protocol maintie_real_agent_singleton_history_v1, Python 3.11.9, model alias qwen35-4b, split all, one trial, 20 steps, 120 seconds, and 512 response tokens. It records model/server file hashes and implementation hashes; these do not prove the active server loaded those bytes. The adapter uses artificial date 2000-01-01 and asset MAINTIE-SINGLETON. It supplies one target record and a source-derived initial query. This is an adapted application-agent exercise, not the official MaintIE benchmark, a realistic CSV-ingestion test, or independent held-out acceptance.

## Final outcomes

| Measure | Result |
| --- | --- |
| Planned / saved | 1,076 / 1,076 |
| Ready for review / expected record selected | 993 / 1,076 (92.3%) |
| Operational completion | 997 / 1,076 (92.7%), including four no-match runs |
| Abstained | 61 (5.7%) |
| Failed | 17 (1.6%) |
| Clarification | 1 |
| No matches | 4 |
| Source-valid non-null proposals | 1,293 / 1,293 (100%) |
| Exact gold-entity diagnostic | 118 / 1,289 (9.2%) |
| Class-compatible exact diagnostic | 107 / 1,289 (8.3%) |

Entity alignment is unavailable for five indices: 825, 858, 882, 905, and 1038. Diagnostic spans exclude unaligned proposals; therefore 1,289 and 1,293 have different denominators. Semantic success, action-status correctness, and chronology correctness are null in the per-run metrics. Exact entity association is not overall answer accuracy or a complete entity precision/recall score. Original gold annotations are absent from the archive, so their correctness and mappings were not independently re-scored.

## Trace findings

### Action-status validation dominates errors

411 of 440 tool-error steps (93.4%) reject unsupported status claims: 324 attempted, 78 planned, and 9 completed. Remaining errors comprise 8 invalid abstention reasons, 8 components beginning with action phrases, 5 ambiguous repeated quotes, 3 unsupported-action/status combinations, 2 invalid quotes, 2 invalid offsets, and 1 unsearchable query.

423 distinct runs encountered tool errors; 405 completed afterward (95.7% operational recovery among runs with tool errors). The other 18 were 17 failed runs and one clarification. Recovery is not proof of semantic correctness. The initial 324 attempted-status rejections merit diagnosis before changing model or budgets. Preserve the rule that persistent symptoms do not convert performed work into attempted work.

### A bounded-reason interface problem is visible

Four failed runs (indices 186, 194, 781, 1064) repeat a rejected abstention reason unchanged. The reasons contain 563, 514, 535, and 503 characters. All exceed 500, which suggests a reason-length contract mismatch; the current implementation must confirm the actual limit. A narrow candidate fix is explicit bounded-reason instructions and actionable validator feedback, retaining schema validation and repeated-decision stopping. Do not silently truncate or accept arbitrary output. This is separate from whether the abstention itself is warranted.

### Completion hides empty extraction

104 ready-for-review runs contain proposals whose component, problem, and action fields are all null. Another 61 all-null proposals belong to abstained runs and four to failed runs. A ready status can therefore mean a selected source record is available for review without extracted content. Do not relabel it semantic success. All-null results may be legitimate for some notes; classification needs the source and intended task. Examples inspected include broad symptom excerpts and abstention explanations that deny explicit evidence despite short identifiable source phrases. These warrant review, not automatic conversion to completed fields.

### Retrieval is not meaningfully challenged

Four no-match outcomes miss the singleton target (858, 869, 870, 882). In inspected cases the chosen query differs from the adapter's source-derived query. Index 805 starts with an unsearchable '[' query and ultimately clarifies after additional empty searches. These demonstrate adapter/query sensitivity. Do not require every real company query to match something; assess against declared relevance labels. Singleton selection and placeholder searches such as '<id>' cannot validate broad retrieval quality.

## Request accounting

5,895 unique requests started and finished, with zero pending/orphan requests and 1,076 distinct run IDs. Every finished event reports response_received and token usage. Totals: 7,068,079 input, 180,047 output, 7,248,126 total; cached input 4,595,873 is a subset of input. Request latency median 1.375 seconds, 95th percentile 3.531 seconds, maximum 5.532 seconds. Requests by stage: 4,405 tool selection, 1,489 extraction, 1 evidence revision. Median recorded per-run wall time is 9.859 seconds, maximum 17.531 seconds. The log spans approximately 3 hours 6 minutes; it is not a company deployment throughput benchmark.

## Supplied script review

analyze_maintie_run.py expects a frozen entity-prediction object with rows, dataset_sha256, split=validation, micro metrics, and exact_record_matches. The current archive stores individual application-agent reports with fields such as report and metrics. That analyzer is for a different evaluation path and cannot directly validate this archive. This is an interface mismatch, not proof that either scorer is incorrect.

prepare_maintie_eval.py validates a pinned 1,076-record source and creates content-based duplicate-group splits. Its documentation explicitly evaluates entity extraction, not the full application agent. The actual completed agent plan uses split all. Do not present its aggregate as an untouched test score. Exact duplicate grouping does not rule out near duplicates or prior exposure.

## Closure and remaining work

1. Preserve this development result and its limitations; keep raw archive and private traces out of routine commits.
2. If fixing runtime behavior now, obtain the implementation matching the plan and inspect the status prompt, reason-length validator, and all-null completion contract. Add focused regression cases and verify only affected live cases before any broader rerun.
3. Freeze CSV-only portfolio scope. A production or stable-agent release requires separate semantic acceptance and realistic multi-record/date/asset cases. No new formats, model switching, expanded process, or automatic label relaxation are justified by this batch.
