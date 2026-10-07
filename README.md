# Maintlog Intelligence

Review exported equipment-maintenance histories with source-linked results and
a bounded local agent, for maintenance engineers and workflow developers.

[![CI](https://github.com/mathewsPR/AppliedAI_Lab/actions/workflows/maintlog-ci.yml/badge.svg)](https://github.com/mathewsPR/AppliedAI_Lab/actions/workflows/maintlog-ci.yml)
![Version](https://img.shields.io/badge/version-0.3.0-blue)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

**Experimental.** Outputs require engineering review. Successful execution does
not prove a correct answer or authorize equipment operation.

<!-- Demo placeholder: add a short GIF of the synthetic HTML review when available. -->

## Why it exists

Maintenance exports spread evidence across many records. Maintlog helps engineers
find relevant history, inspect original text, and review proposed extracted fields.
An agent is a model that chooses tools during a task. Deterministic checks validate
its requested actions and source references. Python modules handle ingestion,
search, evidence checks, and review persistence; LangGraph coordinates model tool
choices. [Architecture](docs/ARCHITECTURE.md) describes these boundaries.

### Recorded operational evaluation

Maintainer-run FAA-history development evaluations on 6 October 2026 reported:

| Uploaded run summary | Agent completed | Fixed completed | Saved / planned |
| --- | --- | --- | --- |
| `summary(20261006-122044).json` | 66/100 (66%) | 83/100 (83%) | 200/200 |
| `summary(20261006-125614).json` | 74/100 (74%) | 83/100 (83%) | 200/200 |
| `summary(20261006-135543).json` | 81/100 (81%) | 83/100 (83%) | 200/200 |

These are recorded operational results from the supplied run artifacts. Completion includes `no_matches`; the latest agent batch has 69
`ready_for_review` and 12 `no_matches` outcomes. Semantic accuracy and complete-task
success are unmeasured (`null`) in all three summaries. Differences in code,
prompts, or budgets must be checked in the manifests before causal comparisons.
Latest recorded setup: Python 3.11.9, `qwen35-4b`, 100 histories, one trial per
workflow, 20 steps, and 120 seconds. The server advertised 4096 context tokens and
Q4_K Medium quantization; exact weight-file identity remains unverified.

| Other recorded validation, 6 October 2026 | Result |
| --- | --- |
| Combined statement/branch coverage | **75.76%** |
| Windows build, version 0.3.0 | Wheel and source distribution built |
| Twine distribution metadata checks | Both distributions **PASSED** |

These checks do not establish fresh installation, independent answer accuracy,
or acceptance of the proposed CI changes. The latest fixed workflow completed
more runs than the agent; agent superiority is not established.
See [evaluation evidence](docs/EVALUATION.md#recorded-operational-results) for
outcome counts, token accounting, source hashes, and missing evidence.
[Recorded validation JSON](reports/RECORDED_VALIDATION.json) preserves the curated
metrics and provenance; the raw uploaded reports are not reproduced here.

## Features

- Strict CSV import and explicit source-column mapping.
- Search restricted by equipment ID and date range.
- Source hashes and record references in results.
- Bounded tool selection through a local model server.
- HTML field review and recorded decisions in SQLite.
- Comparisons with simpler workflows and explicit evaluation limits.

## Quick start

With Python 3.11 and Git installed, this small search needs no model or agent extra.
It targets a useful first result within five minutes on a normal connection.

Windows Git Bash:

```bash
git clone https://github.com/mathewsPR/AppliedAI_Lab.git
cd AppliedAI_Lab/maintlog-intelligence
py -3.11 -m venv .venv
source .venv/Scripts/activate
python -m pip install -e .
maintlog search data/demo/pump_records.csv --data-kind synthetic --query "bearing vibration" --asset-id PUMP-001
```

Linux:

```bash
git clone https://github.com/mathewsPR/AppliedAI_Lab.git
cd AppliedAI_Lab/maintlog-intelligence
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
maintlog search data/demo/pump_records.csv --data-kind synthetic --query "bearing vibration" --asset-id PUMP-001
```

The JSON result contains `hits`, the requested scope, and source evidence for
`PUMP-001`. Search is lexical: it ranks matching wording rather than generating
an answer. No workplace data is included in this example.

## Installation

For agent and replay commands, run from the cloned project with the environment
above active:

```bash
python -m pip install -r requirements-agent.lock
python -m pip check
```

This installs the editable agent extra and pinned dependencies. The base package
has no runtime third-party dependencies; agent orchestration uses LangGraph.
The snapshot has no hashes and records an environment, not a hash-verified lock.
Python 3.11 is the supported version. Windows examples use Git Bash; PowerShell
activation is `.\.venv\Scripts\Activate.ps1`.

Installation needs network access. Deterministic commands and replay work offline
afterward. Live runs require a loopback, OpenAI-compatible chat server supporting
JSON-object replies. No weights are bundled or model server started.

## Usage

Run these from the project folder with the environment active.

Create a structured-history brief:

```bash
maintlog brief data/demo/pump_records.csv --data-kind synthetic --asset-id PUMP-001 --output artifacts/brief.json
```

Generate an HTML review with replay, which uses saved choices instead of a model:

```bash
maintlog agent data/demo/company_export.csv --data-kind synthetic --profile data/demo/company_profile.json --asset-id PUMP-001 --question "Review bearing vibration history" --backend replay --replay data/demo/replay_narrative.json --output artifacts/demo-run.json --html artifacts/demo-review.html
```

Open `artifacts/demo-review.html` in a browser. Inspect each source record and
proposed field/action status. Download `review-decisions.json` from the page and
save it in `artifacts/`. Then import the decisions and create a reviewed brief:

```bash
maintlog-review artifacts/demo-run.json --decisions artifacts/review-decisions.json --database artifacts/reviews.sqlite3
maintlog reviewed-brief data/demo/company_export.csv --data-kind synthetic --profile data/demo/company_profile.json --asset-id PUMP-001 --review-report artifacts/demo-run.json --database artifacts/reviews.sqlite3 --output artifacts/reviewed-brief.json
```

Reuse requires explicit field and action-status review; record acceptance alone
is insufficient. The database preserves review events without changing sources.
Replay measures mechanics, not model quality. See the [review guide](docs/USAGE.md#review-lifecycle).

Use your running llama.cpp server configured with model ID `qwen35-4b`:

```bash
maintlog agent data/demo/company_export.csv --data-kind synthetic --profile data/demo/company_profile.json --asset-id PUMP-001 --question "Review bearing vibration history" --backend local --base-url http://127.0.0.1:8081/v1 --model qwen35-4b --max-steps 20 --timeout 120 --output artifacts/local-run.json --html artifacts/local-review.html
```

Use the exact model ID accepted by your server. Scope comes from CLI flags;
mentioning an equipment ID in the question does not set the scope.
For your own files, declare `--data-kind user-supplied` and keep exports private.
Default CSV columns are `record_id,event_date,asset_id,component,issue,action`.
Dates use YYYY-MM-DD. IDs must be stable and unique; unknown IDs give an empty
scope. The [input guide](docs/USAGE.md#input-contract) explains required fields,
column profiles, missing actions, and rejected input.

### Outputs and interpretation

JSON preserves selected records, source references, proposed fields, and workflow
outcomes. HTML is a review surface; SQLite stores imported human decisions.
A source hash identifies original bytes, but does not archive them: retain the CSV.

A proposed action is not proof that a repair occurred. Record counts are not
counts of distinct failures. A source-valid quote can still be misclassified.
`no_matches` means no selected search matches; it does not prove no relevant
maintenance history exists. Clarification needs a new run with explicit scope;
conversational checkpoint resume is not implemented.

### Compare workflows

```bash
maintlog-compare data/demo/comparison_cases.json --backend replay --trials 3 --output artifacts/replay-comparison.json
```

The comparison covers deterministic lexical search/brief, a fixed tool sequence,
and an agent choosing its tools. For this synthetic fixture, repeated replay tests
mechanics. See [evaluation guidance](docs/EVALUATION.md) for live runs, independent
labels, scoring, and report acceptance.

## Settings

| CLI option | Default | Description |
| --- | --- | --- |
| --data-kind | Required | Declare synthetic or user-supplied input |
| --profile | None | JSON mapping from source columns to canonical fields |
| --asset-id | All assets | Restrict to an exact equipment ID |
| --start / --end | Unbounded | Inclusive dates |
| --task | history | Agent task: history, search, inspect, or extract |
| --top-k | 5 | Search result limit; not full-scope aggregate size |
| --normalization | noun_alias_v1 | Search wording policy; identifiers stay intact |
| --backend | Must be selected for agent | local or replay |
| --base-url | http://127.0.0.1:8081/v1 | Loopback model endpoint |
| --model | local-model | Model ID accepted by the server |
| --max-steps | 8 for agent | Maximum workflow decisions |
| --timeout | 120 seconds | Run budget; not a hard real-time guarantee |
| --max-tokens | 512 | Maximum requested model reply tokens |
| --output / --html | stdout / no HTML | JSON file; agent HTML review file |

Agent and comparison commands have different step defaults: 8 and 20 respectively.
The live example above explicitly selects 20. The recorded batch's 10,000-character
working-context cap is not a token count and does not guarantee a 4096-token fit.

## Documentation

- [Input, review, troubleshooting, and privacy](docs/USAGE.md)

- [Architecture and development](docs/ARCHITECTURE.md)
- [Evaluation and limitations](docs/EVALUATION.md)
- [Release checks](docs/RELEASE.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). From the project directory, run the existing
suite in the active Python 3.11 environment:

```bash
python -m unittest discover -s tests -v
```

Maintainer: [@mathewsPR](https://github.com/mathewsPR). Use the Maintlog issue forms
for sanitized reproducible bugs or focused feature requests. Report security
problems through [SECURITY.md](../.github/SECURITY.md), not a public issue.
Never submit private maintenance exports.

Traces and reports may contain raw private records. Keep them out of public
commits and issues; use separate organization files/databases. There is no
multi-tenant access-control system.

## Roadmap

1. Improve quote recovery without weakening evidence checks.
2. Evaluate complete-answer accuracy on independent permitted cases and compare
   the dynamic agent fairly against the fixed workflow.
3. Validate fresh base/agent installations and Windows/Linux release checks.

Cloud adapters, conversational resume, failure prediction, and equipment control
are not implemented. No product release is justified by completion rates alone.

## License

Original software uses [Apache-2.0](LICENSE). Third-party code and datasets retain
their own terms. See [synthetic provenance](data/demo/PROVENANCE.md) and
[public-data notices](data/public/README.md) before redistribution.
