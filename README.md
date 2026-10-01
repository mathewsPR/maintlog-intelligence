# Maintenance-log intelligence

An equipment-history review assistant for people who work with exported
maintenance records. Project #52 from the supplied portfolio. Industrial pumps
are the demonstration domain; explicit CSV profiles let other organizations map
their source columns without rewriting the program.

**Version 0.3: enforced task requirements, field-level corrections, reusable
reviewed briefs, vocabulary development, and paired workflow comparisons.** The agent chooses tools dynamically; the local model
server supplies those choices. Replay fixtures demonstrate mechanics without a
model. Live model accuracy, Windows execution, and commercial usefulness remain
unverified. See [PRODUCT_REVIEW.md](reports/PRODUCT_REVIEW.md) for the assessment,
release gaps, benchmark interpretation, and market plan.

## Install — Windows 11, VS Code, Git Bash

Python **3.11 only**. Extract the archive, open the project folder, then:

```bash
py -3.11 -m venv .venv
source .venv/Scripts/activate
python --version
python -m pip install -r requirements-agent.lock
python -m unittest discover -s tests -v
```

In PowerShell activate with `.\.venv\Scripts\Activate.ps1`. On Linux create the
venv with `python3.11 -m venv .venv`, then `source .venv/bin/activate`.
Select that environment in VS Code. Dependencies are pinned to the versions
installed on Linux Python 3.11.16; Windows installation has not been executed.

For the deterministic CSV/search/brief tools alone, install with
`python -m pip install -e .`. They have no runtime package dependencies.
The agent extra is also available with `python -m pip install -e ".[agent]"`;
the lock records the tested transitive versions. Package installation needs
network access. Bundled dataset evaluation and replay runs work offline afterward.

## First run — no model needed

This is a **synthetic replay demonstration**, not an AI-quality test:

```bash
maintlog agent data/demo/company_export.csv --data-kind synthetic --profile data/demo/company_profile.json --asset-id PUMP-001 --question "Review bearing vibration history" --backend replay --replay data/demo/replay_narrative.json --output artifacts/demo-run.json --html artifacts/demo-review.html
```

Open `artifacts/demo-review.html` in your browser. It shows the raw records,
source references, unreviewed extraction proposal, and deterministic aggregate.
Review each field and action status, accept or correct exact source excerpts,
accept/reject the record, enter your name, and download `review-decisions.json`.
Put that downloaded file in `artifacts`, then preserve the review events:

```bash
maintlog-review artifacts/demo-run.json --decisions artifacts/review-decisions.json --database artifacts/reviews.sqlite3
```

Review decisions are bound to the SHA-256 of this exact JSON run. SQLite stores
that run and append-only decision events. Reimporting decisions adds another
review event; it never edits source records or silently approves later runs.
Record acceptance alone does not approve fields. Reuse requires explicit
decisions on all three fields and action status. Partial reviews remain recorded
but are ineligible for aggregation. It is not equipment-operation authorization.
The review page is self-contained and makes no network calls. Unsaved browser
choices are lost on refresh until you download them.

## Use your local model

Start your existing llama.cpp server yourself. Its OpenAI-compatible chat
endpoint must support JSON-object output. Then choose the local backend:

```bash
maintlog agent data/demo/company_export.csv --data-kind synthetic --profile data/demo/company_profile.json --asset-id PUMP-001 --question "Review bearing vibration history and proposed actions" --backend local --base-url http://127.0.0.1:8081/v1 --model local-model --max-steps 8 --max-tokens 512 --timeout 120 --output artifacts/local-run.json --html artifacts/local-review.html
```

Use the model identifier accepted by your server. The program does not download
or start a model, assume GPU settings, or connect without an explicit backend.
Only loopback HTTP endpoints are supported; redirects and environment HTTP
proxies are disabled. LangSmith tracing is disabled for this graph even if
shell tracing settings are enabled. A Gemini/cloud adapter is not implemented.

This delivery did not run Phi-4-mini, a GGUF model, or the user’s RTX 4060. A
10,000-character prompt cap is a size guard, not a token count; measure the actual
context needs of your server/model. Long records can stop with `context_limit`.
The step bound is strict; the run deadline is checked between tools and after
replies. Each local HTTP request runs in a separate Python process, terminated
when its total client deadline expires (at most 30 seconds or the remaining run
budget). Process startup/termination and local tool work are not hard real-time
guarantees. Server-side generation may continue after the client disconnects.

## Bring a company export

The default strict format is:
`record_id,event_date,asset_id,component,issue,action` in that order.
Or create a JSON profile like `data/demo/company_profile.json`:

```json
{
  "columns": {
    "record_id": "Work Order",
    "event_date": "Date",
    "asset_id": "Equipment",
    "narrative": "Technician Notes"
  }
}
```

`record_id`, `event_date`, and `asset_id` mappings are required. Map either
`narrative` or `issue`. In structured mode `component` and `action` are optional;
in narrative mode `component` is optional and `action` cannot also be mapped.
Extra export columns are ignored. Dates must already be `YYYY-MM-DD`; use stable
record IDs and exact asset IDs. IDs are preserved, not guessed. Missing required
identities/dates, duplicate IDs/headers, malformed rows, blank required text,
invalid UTF-8, and noncanonical dates are rejected before analysis.

Use `--data-kind user-supplied` for your own exports. This is your declaration,
not proof of source authenticity. The imported source bytes receive a SHA-256;
original text, source column names, and logical CSV row numbers are retained.
Keep the original CSV. A content hash identifies the bytes but does not store them.
Use a separate CSV/run/database per organization; there is no multi-tenant
permission system. The default noun aliases preserve action abbreviations such as repl/chk/lub.
The six-entry dictionary_v0 remains frozen as a benchmark baseline. An optional
training-derived vocabulary can be loaded with --vocabulary; see below.
Multilingual and cross-company quality remain unverified.

## Deterministic tools

```bash
maintlog import data/demo/pump_records.csv --data-kind synthetic
maintlog search data/demo/pump_records.csv --data-kind synthetic --query "bearing vibration" --asset-id PUMP-001 --start 2026-01-01 --end 2026-01-31
maintlog brief data/demo/pump_records.csv --data-kind synthetic --asset-id PUMP-001 --output artifacts/brief.json
```

All commands honor exact asset IDs and inclusive date ranges. Set these flags
explicitly to constrain the corpus; prose in `--question` does not automatically
change the scope. Unsupported command flags are rejected. Unknown asset IDs
produce an explicitly empty scope. No cross-file merging is performed.

## Agent behavior and evidence boundary

The LangGraph loop asks the model to choose `assets`, `search`, `record`,
`extract`, `aggregate`, `clarify`, `abstain`, or `finish`. It may refine a search or pause for
clarification. A clarification requires a new run with a clearer question/scope;
there is no conversational checkpoint resume yet.

Python locks the tool corpus to the user’s scope, validates tool arguments,
resolves unique copied quotes or checks zero-based character spans against exact raw fields, and rejects final
citations to unseen records. Null extracted fields mean unknown. Action status
(planned/attempted/completed/verified/unknown) is always a **model proposal**.
Conservative rules reject fields copied from incompatible source columns,
obvious action phrases assigned as components, clipped nearby negation, and
non-unknown action states without explicit wording cues. These rules reject
some contradictions; they do not prove semantic classification correctness. The report
contains selected original records and proposals, not free-form diagnoses.

`aggregate` operates on all scoped structured input rows, not top-k hits or
unreviewed extractions. It groups exact asset/component/normalized issue wording.
Unstructured narratives remain explicitly unclassified. Use `reviewed-brief` to aggregate explicitly reviewed/corrected fields.
It uses the latest complete accepted review per record, rechecks the exact source
and normalization profile, and retains event/reviewer/span provenance. A later
rejection or incomplete review supersedes earlier field approval. Counts describe records, not unique events,
failures, repair success, root cause, or predictions. BM25 can retrieve negated
statements; inspect the raw text. CSVs are loaded into memory; enterprise-scale
throughput has not been measured.

Every run records tool choices, results/errors, scope, limits, elapsed time,
backend label, and server-reported usage when provided. Default: eight choices,
120-second run deadline with a terminable HTTP request worker, at most two invalid
responses/tool calls. Tool execution is checked between steps, not preempted.
Default task: `history`, requiring search, full-scope aggregation, inspection
of every final record, and extraction/explicit unknowns for final narratives.
Choose `--task search`, `inspect`, or `extract` for a narrower explicit job.
Optional `--initial-query` gives the model the same initial query used by a
comparison baseline. A finish that skips required work is rejected. An empty
finish requires a completed no-hit search; uncertain relevance should abstain.
Workflow completion and semantic task success are separate report fields.
Statuses: `ready_for_review`, `needs_clarification`, `no_matches`, `no_records`,
`abstained`, `budget_exhausted`, `context_limit`, or `failed`. Incomplete/abstained runs still export their trace and return
CLI exit code 3; input/dependency errors return 2. A successful replay run means
tested plumbing, not autonomous model performance.

## Public-data evaluation

```bash
python -m maintlog.evaluation --data-root data/public --output-dir reports
```

Unmodified MaintNorm/MaintIE snapshots, licenses, revisions and SHA-256 manifest
are included; the evaluator verifies them before scoring. No model/API call is
made by this evaluator. On 1,200 MaintNorm test records the frozen dictionary
achieves 77.18% casefold lexical accuracy versus 76.96% unchanged-input accuracy;
correction precision is 12.79% and recall 0.93%. MaintIE’s 1,076 expert-annotated
records are schema-audited; no model extraction score is available.
Read [DATASET_EVALUATION_REPORT.md](reports/DATASET_EVALUATION_REPORT.md).

## Reuse reviewed fields

After importing decisions, run:

```bash
maintlog reviewed-brief data/demo/company_export.csv --data-kind synthetic --profile data/demo/company_profile.json --asset-id PUMP-001 --review-report artifacts/demo-run.json --database artifacts/reviews.sqlite3 --output artifacts/reviewed-brief.json
```

The report distinguishes all scoped rows from eligible reviewed rows. Original
records are unchanged. `--review-run SHA256` is an alternative to `--review-report`.
Reviews of a changed CSV/profile/vocabulary must be regenerated; the program
refuses to combine source versions. Human judgments are attributed, not declared
infallible. Legacy version 0.2 record acceptance alone does not promote fields.

## Normalization development and optional vocabulary

```bash
python -m maintlog.normalization_probe --data-root data/public --output reports/NORMALIZATION_DEVELOPMENT.json
maintlog search data/demo/pump_records.csv --data-kind synthetic --query bearing --vocabulary reports/NORMALIZATION_DEVELOPMENT.json
```

The development probe fits a vocabulary only on MaintNorm training labels
(minimum five observations, 98% target agreement; protected identifiers and
privacy-mask targets excluded). It compares methods on the validation split.
The 84-entry experimental vocabulary achieved 99.40% correction precision and
41.26% recall on that split, with 86.11% casefold lexical accuracy. These are
**development normalization results**, not independent holdout, agent or
cross-company scores. Test errors had already been inspected before this policy
was designed. Do not tune further and present the same validation set as fresh
confirmation. Corpus-specific vocabulary is optional and not enabled by default.

The probe JSON contains `trained_lexicon`; custom files can contain an `entries`
object mapping alphabetic source words to `{ "target": "expanded phrase" }`.
Explicit `--vocabulary` supports import/search/brief/agent/reviewed-brief and is
mutually exclusive with search `--normalization`. Its hash binds imported records
to the chosen policy. Unknown words and identifier-like strings remain unchanged.
Do not interpret expanded verbs as proof an action occurred.

## Compare simpler workflows and the agent

```bash
maintlog-compare data/demo/comparison_cases.json --backend replay --trials 3 --output artifacts/replay-comparison.json
maintlog-compare data/demo/comparison_cases.json --backend local --base-url http://127.0.0.1:8081/v1 --model local-model --trials 3 --max-steps 20 --timeout 120 --output artifacts/local-comparison.json
```

Comparisons use the same CSV, scope, alias policy and explicit initial query.
Methods: deterministic lexical search/brief, fixed search/inspect/extract workflow,
and dynamic agent. The fixed workflow calls the same local backend for extraction
only; tool ordering is scripted. The agent chooses its tools. Identical run/step
budgets apply to the two model workflows; execution order rotates across trials.
Labels are kept outside model context. Relevance sets, exact field spans, action
statuses and aggregate/count labels are scored separately from graph termination.
Outputs record failures, abstention, elapsed time, actual request attempts and
server-reported token usage; price-based cost remains unknown.

`data/demo/comparison_cases.json` documents the labeled case format, source/profile
hashes and replay fixtures. Replace it with permitted, separately reviewed held-out
cases for a real evaluation. History cases require aggregate-group labels, even
an empty list. Run configurations and raw traces are retained. Three handwritten
synthetic cases with replay outputs verify mechanics only; repeated replay trials
are not independent model observations. No agent superiority is established.
