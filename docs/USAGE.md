# CSV user guide

This guide covers installation, company CSV logs, a local-agent run, and review.
Commands use Bash or Windows Git Bash and run from `AppliedAI_Lab/maintlog-intelligence`.
Keep inputs and outputs private. Example notes below are invented.

## Install and activate

Install Git and Python 3.11, then clone the repository:

```bash
git clone https://github.com/mathewsPR/AppliedAI_Lab.git
cd AppliedAI_Lab/maintlog-intelligence
```

Choose the environment commands for your operating system.

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

In Windows PowerShell, activate an existing environment with
`.\.venv\Scripts\Activate.ps1`; the rest of this tutorial uses Bash syntax.

```bash
python --version
python -m pip install --upgrade "pip==26.2.1" "setuptools==83.0.0"
python -m pip install -r requirements-agent.lock
python -m pip check
python -m maintlog.cli --help
```

Confirm Python reports 3.11.x and `pip check` reports no broken requirements.
The dependency file installs the editable project with agent dependencies. It is
a pinned environment snapshot without package hashes, not a hash-verified lock.

For each new terminal, return to the project directory and activate the environment
again. Model weights and the llama.cpp executable are separate prerequisites.

## Input contract

CSV is the supported application input. Use UTF-8, comma-separated columns, and
proper quoting for commas or line breaks inside notes. Each row is a maintenance
record, not necessarily a distinct failure or completed repair.

### Structured CSV

The default format uses these headers in this order:

```csv
record_id,event_date,asset_id,component,issue,action
EXAMPLE-001,2026-01-03,PUMP-001,bearing,bearing vibration,inspection requested
EXAMPLE-002,2026-01-08,PUMP-001,bearing,bearing vibration,
```

| Field | Requirement |
| --- | --- |
| `record_id` | Stable, unique, nonblank ID without surrounding whitespace |
| `event_date` | Valid date in canonical `YYYY-MM-DD` form |
| `asset_id` | Exact, nonblank equipment ID without surrounding whitespace |
| `component` | Nonblank in the default structured format |
| `issue` | Nonblank in the default structured format |
| `action` | Header required; value may be blank |

A blank action means no action is recorded. It does not establish that no action
occurred. A requested inspection does not establish completed work.

### Narrative CSV and profiles

For free-text technician notes, keep identity/date columns and map the narrative:

```csv
Work Order,Date,Equipment,Technician Notes
WO-1001,2026-01-03,PUMP-17,"Bearing vibration reported. Inspection planned."
WO-1002,2026-01-08,PUMP-17,"Replaced bearing. Vibration remains high."
```

The corresponding `profile.json` is:

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

Map your actual header names exactly. Profiles require identity/date mappings and
either narrative or issue text. In narrative mode, action is extracted from the
narrative; separately stored actions need a profile supported by the ingestion
contract. Do not assume additional fields are combined automatically. Extra export
columns are ignored. The bundled `data/demo/company_profile.json` is a working
narrative example.

Malformed rows, duplicate IDs or headers, missing identities, and invalid dates
are rejected. Resolve missing dates or equipment IDs in the source preparation
process; do not invent them to pass validation. Preserve the original export and
record any transformations. No fuzzy equipment-ID matching or cross-file merging
is performed.

Source hashes identify original bytes, not backups. A CSV evidence row is a logical
record; a quoted multiline note can occupy more than one physical line.

## Use your own CSV

### 1. Choose a private working folder

This cross-platform Bash command uses a folder under your home directory, outside
the cloned repository in a typical setup:

```bash
export MAINTLOG_WORKDIR="$(python -c 'from pathlib import Path; print((Path.home() / "maintlog-private").as_posix())')"
mkdir -p "$MAINTLOG_WORKDIR/results"
```

Place your UTF-8 export at `maintenance.csv` and its mapping at `profile.json` in
that folder. If you choose another location, set `MAINTLOG_WORKDIR` to its absolute
path; on Windows use a form such as `F:/MaintlogPrivate`.

To try the tutorial before using company data, create the two invented records
and mapping below. This refuses to replace either existing input file:

```bash
python - <<'PY'
import csv
import json
import os
from pathlib import Path

folder = Path(os.environ["MAINTLOG_WORKDIR"])
csv_path = folder / "maintenance.csv"
profile_path = folder / "profile.json"
if csv_path.exists() or profile_path.exists():
    raise SystemExit("Input exists. Choose an empty tutorial folder.")
folder.mkdir(parents=True, exist_ok=True)
with csv_path.open("x", encoding="utf-8", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["Work Order", "Date", "Equipment", "Technician Notes"])
    writer.writerow([
        "WO-1001", "2026-01-03", "PUMP-17",
        "Bearing vibration reported. Inspection planned.",
    ])
    writer.writerow([
        "WO-1002", "2026-01-08", "PUMP-17",
        "Replaced bearing. Vibration remains high.",
    ])
profile = {"columns": {
    "record_id": "Work Order", "event_date": "Date",
    "asset_id": "Equipment", "narrative": "Technician Notes",
}}
with profile_path.open("x", encoding="utf-8") as stream:
    json.dump(profile, stream, indent=2)
    stream.write("\n")
print(f"Created invented examples in {folder}")
PY
```

Use `--data-kind synthetic` for these invented examples. Use
`--data-kind user-supplied` for company exports. This flag declares provenance;
it does not validate authenticity.

### 2. Check import and scope without a model

For a company export:

```bash
python -m maintlog.cli import "$MAINTLOG_WORKDIR/maintenance.csv" --data-kind user-supplied --profile "$MAINTLOG_WORKDIR/profile.json" --output "$MAINTLOG_WORKDIR/results/import.json"
python -m maintlog.cli search "$MAINTLOG_WORKDIR/maintenance.csv" --data-kind user-supplied --profile "$MAINTLOG_WORKDIR/profile.json" --query "bearing vibration" --asset-id PUMP-17 --start 2026-01-01 --end 2026-01-31 --output "$MAINTLOG_WORKDIR/results/search.json"
```

For the invented files, replace both `user-supplied` values with `synthetic`.
Inspect the JSON files before continuing. Stop if import fails. Confirm the chosen
asset/date range and search hits refer to the intended records.

Scope is set by flags. Dates are inclusive; equipment IDs are exact. Writing an
ID or date in a question does not set scope. Search ranks matching wording and
can miss relevant synonyms. Top-k limits hits, not full-scope aggregate size.

### 3. Start and check the model server

Follow [local model prerequisites](#local-model-prerequisites). Keep the server
terminal open while running the agent.

### 4. Run a scoped agent review

With the model server accepting `qwen35-4b`, run this for a company export:

```bash
python -m maintlog.cli agent "$MAINTLOG_WORKDIR/maintenance.csv" --data-kind user-supplied --profile "$MAINTLOG_WORKDIR/profile.json" --asset-id PUMP-17 --start 2026-01-01 --end 2026-01-31 --task history --initial-query "bearing vibration" --question "Review bearing vibration history and reported maintenance actions." --backend local --base-url http://127.0.0.1:8081/v1 --model qwen35-4b --max-steps 20 --timeout 120 --max-tokens 512 --output "$MAINTLOG_WORKDIR/results/pump-17.json" --html "$MAINTLOG_WORKDIR/results/pump-17.html"
```

For invented input, replace `user-supplied` with `synthetic`. Change the ID, date
range, query, and question to match your task. Choose distinct output names for
additional runs; retain earlier outputs and do not overwrite original inputs.
A successful process or saved JSON is not proof of a correct answer.

### 5. Inspect the report

Open `results/pump-17.html` in your browser. Compare selected notes, quoted fields,
and action-status proposals with the original CSV. JSON preserves the run status,
source evidence, proposed fields, and trace. Follow the review lifecycle below to
save decisions and produce a reviewed brief.

## Review lifecycle

After the tutorial run:

1. Inspect original records and proposed component, problem, and action fields.
2. Review action status separately: planned work is not completed work; completed
   work is not proof of successful repair.
3. Accept, reject, or correct supported fields, with a reviewer name and notes.
4. Download decisions from the HTML page and save them as
   `results/review-decisions.json` inside `MAINTLOG_WORKDIR`.
5. Import decisions into a private SQLite database, then create the reviewed brief.

These commands require the tutorial run and downloaded decisions:

```bash
maintlog-review "$MAINTLOG_WORKDIR/results/pump-17.json" --decisions "$MAINTLOG_WORKDIR/results/review-decisions.json" --database "$MAINTLOG_WORKDIR/results/reviews.sqlite3"
python -m maintlog.cli reviewed-brief "$MAINTLOG_WORKDIR/maintenance.csv" --data-kind user-supplied --profile "$MAINTLOG_WORKDIR/profile.json" --asset-id PUMP-17 --start 2026-01-01 --end 2026-01-31 --review-report "$MAINTLOG_WORKDIR/results/pump-17.json" --database "$MAINTLOG_WORKDIR/results/reviews.sqlite3" --output "$MAINTLOG_WORKDIR/results/reviewed-brief.json"
```

For invented input, use `synthetic` in the reviewed-brief command.

Decisions are bound to the exact run hash. Original source records are not changed.
Record acceptance alone does not approve extracted fields. Incomplete field/status
review cannot be reused for reviewed aggregation. Changed source, profile, or
vocabulary requires compatible new review; do not reuse approvals across versions.
Importing decisions again adds review events. Retain the original report, downloaded
decisions, database, CSV, and profile together.

The self-contained HTML page makes no network calls. Unsaved choices are lost on
refresh until downloaded. Human judgments are attributed, not infallible.

## Local model prerequisites

Install llama.cpp and obtain compatible model weights separately, following their
licenses. The adapter uses a loopback HTTP chat endpoint with OpenAI-compatible
request formatting and JSON-object responses; this does not require OpenAI's
hosted service. The demonstrated model alias is `qwen35-4b`.

On Windows Git Bash, set the executable and model paths to your actual files before
running this example in a separate terminal:

```bash
MAINTLOG_SERVER="F:/AI/2.llamacpp/llama-server.exe"
MAINTLOG_MODEL="F:/AI/2.llamacpp/models/_unpinned/Qwen3.5-4B-Q4_K_M.gguf"
"$MAINTLOG_SERVER" --model "$MAINTLOG_MODEL" --alias qwen35-4b --host 127.0.0.1 --port 8081 --ctx-size 4096 --n-gpu-layers 99 --reasoning off
```

Those paths are examples from the maintainer's setup. They are not bundled files.
On Linux, use your actual `llama-server` executable and GGUF model paths. Server
flags depend on the installed llama.cpp build; inspect its `--help` if a flag is
rejected. The GPU-layer setting requests offload and does not guarantee a fit on
other hardware. The maintainer used an RTX 4060 with 8 GB VRAM.

From the project terminal, check readiness and the advertised model ID:

```bash
curl --fail http://127.0.0.1:8081/health
curl --fail http://127.0.0.1:8081/v1/models
```

Use the server's exact accepted model ID in `--model`. Reuse an existing server only
when its model/configuration matches; do not start a second one on the same port.
Retain model/server versions and file hashes for reproducibility. An alias and
advertised metadata do not establish the identity of loaded weight bytes.

Recorded runs used a server-advertised 4096-token context. A 10,000-character
working-context cap does not guarantee a fit. Client timeout does not guarantee
server-side generation cancellation. Inspect token needs and preserved traces
before changing scope or configuration.

## Settings

| Option | Default | Notes |
| --- | --- | --- |
| `--data-kind` | Required | CLI accepts `synthetic` or `user-supplied` |
| `--profile` | None | Explicit input-column mapping |
| `--vocabulary` | None | Optional supported vocabulary file |
| `--asset-id` | All assets | Exact equipment ID |
| `--start`, `--end` | Unbounded | Inclusive canonical dates |
| `--task` | `history` | Agent mode: history, search, inspect, or extract |
| `--initial-query` | None supplied | Explicit first search wording for the task |
| `--top-k` | 5 | Search hit limit |
| `--normalization` | `noun_alias_v1` | Search wording policy; identifiers stay intact |
| `--base-url` | `http://127.0.0.1:8081/v1` | Model endpoint |
| `--model` | `local-model` | Set the accepted server alias |
| `--max-steps` | 8 for agent | Comparison command defaults to 20 |
| `--timeout` | 120 seconds | Workflow budget |
| `--max-tokens` | 512 | Maximum requested model reply tokens |
| `--output`, `--html` | stdout / no HTML | JSON and optional agent review page |

Live examples explicitly use backend `local` and 20 steps. Use the CLI's help for
installed options; do not assume defaults are shared across different commands.

## Outcomes and troubleshooting

| Outcome | Interpretation |
| --- | --- |
| `ready_for_review` | Output is available for inspection; fields may be null or wrong |
| `no_matches` | Search selected no matches; not proof of no relevant history |
| `abstained` | Agent stopped without completing the task |
| `needs_clarification` | Start a new run with clearer input and explicit scope |
| `failed` | Run did not finish successfully |
| `context_limit` | Model request exceeded the available context |

The inspected CLI returns 0 for supported normal outcomes, including clarification
and no-match cases; 2 for input/runtime errors; and 3 for non-successful agent
outcomes. Inspect JSON status/completion regardless of process exit. Other commands
have their own semantics. The comparison command saves scores even when task
scores fail; a saved comparison is not passed acceptance.

| Problem | Action |
| --- | --- |
| Wrong Python | Activate the environment and check `python --version` |
| Missing agent imports | Install `requirements-agent.lock`; run `python -m pip check` |
| `maintlog` command not found | Use `python -m maintlog.cli`; verify environment activation |
| `maintlog-review` not found | Activate the installation's environment; check its Scripts/bin directory |
| Import rejection | Check encoding, duplicate headers/IDs, mapped fields, and date format |
| Empty scope | Check exact asset ID and date range against the CSV |
| No search matches | Inspect query, normalization, source text, and scope |
| Connection/model error | Check health, accepted ID, and port |
| Invalid proposal | Preserve the trace and inspect validation feedback; do not bypass checks |
| Context limit | Inspect token needs and long notes; use explicit scope and measured settings |
| Input/output collision | Choose a separate output file and preserve original inputs |

```bash
python -m maintlog.cli --help
maintlog-review --help
python -m maintlog.comparison --help
```

## Evaluation and limitations

Replay demonstrates mechanics using saved decisions. Live results on development
cases do not establish independent accuracy. Source-valid quotes can be assigned
to the wrong field. Record counts do not represent distinct failures, root causes,
or verified repair outcomes. Neither absence of an advisory warning nor ready
status establishes correctness.

The completed 1,076-task evaluation used singleton records with artificial asset
IDs and dates. It did not test real multi-event chronology or realistic company
CSV ingestion. See [the final review](FINAL_AGENT_REVIEW_20261007.md) and
[evaluation guidance](EVALUATION.md) before interpreting results or planning acceptance.

## Privacy and support

With the demonstrated loopback endpoint, model requests go to the local server.
Changing the endpoint changes where records are sent; review the destination before
using company inputs. Exports, prompts, traces, HTML/JSON reports, decisions, and
SQLite databases can contain sensitive text. Keep them in company-controlled
storage and out of public issues and commits. A `.gitignore` does not untrack
previously committed files. Source hashes do not redact or anonymize records.

Separate organizations' files/databases. The project has no multi-tenant access
control, automated retention service, or commercial response-time guarantee.
For bugs, submit a small invented reproduction, version/commit, Python/OS, command,
backend/model details, expected outcome, and sanitized error. Use the Maintlog issue
forms in AppliedAI_Lab. For vulnerabilities, follow [the security policy](../../.github/SECURITY.md)
and its activation status.
