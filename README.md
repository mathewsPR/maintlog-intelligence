# Maintlog Intelligence

Review equipment-maintenance CSV logs with a local agent and source-linked evidence.

[![CI](https://github.com/mathewsPR/AppliedAI_Lab/actions/workflows/maintlog-ci.yml/badge.svg)](https://github.com/mathewsPR/AppliedAI_Lab/actions/workflows/maintlog-ci.yml)
![Version](https://img.shields.io/badge/version-0.3.0-blue)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

**Experimental software for supervised review.** CSV is the supported input format.
Outputs are proposals for an engineer to check, not verified maintenance conclusions.

<!-- Add an actual screenshot of the bundled HTML review when available. -->

## Why it exists

Maintenance exports spread reported problems and actions across many records.
Maintlog helps maintenance engineers find relevant records, inspect original notes,
and review extracted fields without losing their source references.

An agent is a model that chooses tools to complete a task. LangGraph coordinates
those choices; Python code handles CSV import, search, validation, and review storage.
The default local setup uses llama.cpp to run the model on your computer.

## Features

- CSV import with explicit mappings for company column names.
- Search scoped by equipment ID and inclusive dates.
- Proposed component, problem, action, and action-status fields.
- Source hashes, record IDs, and quoted excerpts in results.
- Configurable step and time budgets for agent runs.
- HTML review and human decisions stored in SQLite, a local database file.

## Quick start

Requirements: Git and **Python 3.11**. Commands below use Bash or Windows Git Bash.
The bundled search provides a first result without downloading a model.

```bash
git clone https://github.com/mathewsPR/AppliedAI_Lab.git
cd AppliedAI_Lab/maintlog-intelligence
```

Create and activate an environment using **one** of these options.

Windows Git Bash:

```bash
py -3.11 -m venv .venv
source .venv/Scripts/activate
```

Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Install and search the invented demo records:

```bash
python -m pip install --upgrade "pip==26.2.1" "setuptools==83.0.0"
python -m pip install -e .
python -m maintlog.cli search data/demo/pump_records.csv --data-kind synthetic --query "bearing vibration" --asset-id PUMP-001
```

The JSON result lists matching records and their source evidence. Search matches
wording; it does not generate a model answer. See the next section for agent setup.

## Installation for the agent

From the same project directory, with the environment active:

```bash
python -m pip install -r requirements-agent.lock
python -m pip check
```

This installs the project and pinned agent dependencies. Installation requires
network access. The dependency snapshot has no package hashes. Model weights and
llama.cpp are installed separately; the project does not start a model server.

For the commands below, start an OpenAI-compatible local chat server at
`http://127.0.0.1:8081/v1` accepting model ID `qwen35-4b` and JSON-object replies.
The recorded setup used Qwen3.5-4B with a 4096-token context. Model installation,
server startup, and checks are explained in the [user guide](docs/USAGE.md#local-model-prerequisites).

## Try the review interface

Replay uses saved decisions to demonstrate the interface without a running model.
It does not evaluate model quality. Agent dependencies must already be installed.

```bash
python -m maintlog.cli agent data/demo/company_export.csv --data-kind synthetic --profile data/demo/company_profile.json --asset-id PUMP-001 --question "Review bearing vibration history" --backend replay --replay data/demo/replay_narrative.json --output artifacts/demo-run.json --html artifacts/demo-review.html
```

Open `artifacts/demo-review.html` in your browser. Inspect source notes, proposed
fields, and action statuses. Download review decisions before closing or refreshing
the page. See [how to import decisions and create a reviewed brief](docs/USAGE.md#review-lifecycle).

## Use your own CSV

Keep company inputs and generated reports outside the public repository.
A narrative export can use these columns:

```csv
Work Order,Date,Equipment,Technician Notes
WO-1001,2026-01-03,PUMP-17,"Bearing vibration reported. Inspection planned."
WO-1002,2026-01-08,PUMP-17,"Replaced bearing. Vibration remains high."
```

These rows are invented. Each row needs a unique record ID, a valid `YYYY-MM-DD`
date, and an equipment ID. Notes can be free text. Map the headers in `profile.json`:

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

After placing `maintenance.csv` and `profile.json` in `maintlog-private` under your
home directory, and starting the server described above, run:

```bash
export MAINTLOG_WORKDIR="$(python -c 'from pathlib import Path; print((Path.home() / "maintlog-private").as_posix())')"
mkdir -p "$MAINTLOG_WORKDIR/results"
python -m maintlog.cli agent "$MAINTLOG_WORKDIR/maintenance.csv" --data-kind user-supplied --profile "$MAINTLOG_WORKDIR/profile.json" --asset-id PUMP-17 --start 2026-01-01 --end 2026-01-31 --task history --initial-query "bearing vibration" --question "Review bearing vibration history and reported maintenance actions." --backend local --base-url http://127.0.0.1:8081/v1 --model qwen35-4b --max-steps 20 --timeout 120 --output "$MAINTLOG_WORKDIR/results/pump-17.json" --html "$MAINTLOG_WORKDIR/results/pump-17.html"
```

Replace the equipment ID, dates, and question for your task. Scope comes from flags;
mentioning an ID in the question does not restrict the input.

Open `results/pump-17.html` in your private folder. Check every proposal against the
original records. Keep the original CSV: its hash identifies bytes but does not
save a backup. Follow the [complete CSV tutorial](docs/USAGE.md#use-your-own-csv)
for input checks and the review workflow.

## Settings

| Option | Default | Purpose |
| --- | --- | --- |
| `--data-kind` | Required | Declare `synthetic` or `user-supplied` input |
| `--profile` | None | Map source column names |
| `--asset-id` | All assets | Restrict to an exact equipment ID |
| `--start`, `--end` | Unbounded | Inclusive date range |
| `--task` | `history` | Agent task: history, search, inspect, or extract |
| `--backend` | Select explicitly for agent examples | Use `local` or `replay` |
| `--model` | `local-model` | Model ID accepted by the server |
| `--max-steps` | 8 for agent | Limit workflow decisions; live example sets 20 |
| `--timeout` | 120 seconds | Run budget; not a hard real-time guarantee |
| `--max-tokens` | 512 | Maximum requested reply length in tokens |

A token is a unit of model text. A character cap is not a token count and does not
guarantee that a request fits a 4096-token context. See [additional settings](docs/USAGE.md#settings).

## Evaluation and limitations

A completed local-model development batch on 7 October 2026 used **1,076 adapted
MaintIE singleton tasks**, one trial each:

| Measure | Recorded result |
| --- | --- |
| Saved / planned | 1,076 / 1,076 |
| Operational completion, including four no-match runs | 997 / 1,076 (92.7%) |
| Expected record selected | 993 / 1,076 (92.3%) |
| Source-valid non-null excerpts | 1,293 / 1,293 (100%) |
| Requests started / finished | 5,895 / 5,895 |

These are execution and grounding results, **not semantic accuracy**. The tasks use
artificial equipment/date metadata and development data. 104 ready-for-review runs
had all-null extraction proposals. Entity-span agreement remains a diagnostic;
answer, action-status, and chronology correctness are unmeasured.

See the [final agent review](docs/FINAL_AGENT_REVIEW_20261007.md) and
[curated metrics](reports/MAINTIE_AGENT_REVIEW_20261007.json).
Earlier FAA-history evaluations used a different protocol: recorded agent completion
was 66/100, 74/100, and 81/100, versus 83/100 for the fixed workflow in each batch.
[Evaluation evidence](docs/EVALUATION.md#recorded-operational-results) and
[recorded validation JSON](reports/RECORDED_VALIDATION.json) preserve those results
and the earlier 75.76% coverage/build checks. They do not establish agent superiority.

Separate Windows repository-controls checks on 7 October recorded 222 passing
tests, 75.90% combined statement/branch coverage, successful build/Twine/fresh-wheel
checks, and passing Bandit and dependency audits. These are code/package checks,
not model-accuracy measurements.

A source-valid excerpt can still be misclassified. `ready_for_review` is not an
approval, and `no_matches` does not prove no relevant history exists. Record counts
are not distinct failure counts. Equipment control, failure prediction, Excel/PDF
import, and conversational resume are outside the implemented scope.

## Documentation and support

- [CSV tutorial, review, settings, troubleshooting, and privacy](docs/USAGE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Evaluation](docs/EVALUATION.md)
- [Release checks](docs/RELEASE.md)

Maintainer: [@mathewsPR](https://github.com/mathewsPR).
Report reproducible bugs through the [repository issues](https://github.com/mathewsPR/AppliedAI_Lab/issues).
Use invented or sanitized examples. Follow [SECURITY.md](../.github/SECURITY.md)
for private vulnerability reporting. Never post company logs, prompts, or traces.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, checks, and submitting a change.
The project uses Python 3.11 and the standard-library `unittest` test runner.

## Roadmap

1. Diagnose extraction and action-status errors without weakening source checks.
2. Validate correctness on independent, permitted multi-record CSV histories.
3. Preserve reproducible results and improve the supervised review experience.

## License

Original software uses [Apache-2.0](LICENSE). Third-party code, models, and datasets
retain their own terms. Read the [synthetic provenance](data/demo/PROVENANCE.md)
and [public-data notices](data/public/README.md) before redistribution.
