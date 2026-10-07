# Inputs, review, and troubleshooting

Commands assume the cloned project directory and an active Python 3.11 environment.
The repository contains demo data; do not assume examples are installed in a wheel.

## Input contract

The default CSV uses these headers, in this order:

```csv
record_id,event_date,asset_id,component,issue,action
EXAMPLE-001,2026-01-03,PUMP-001,bearing,bearing vibration,inspection requested
EXAMPLE-002,2026-01-08,PUMP-001,bearing,bearing vibration,
```

These rows are invented examples. Blank action means no action is recorded, not
that no action occurred. A stated inspection request does not mean it was completed.

| Field | Requirement |
| --- | --- |
| record_id | Stable, unique, nonblank ID without surrounding whitespace |
| event_date | Canonical YYYY-MM-DD date |
| asset_id | Exact, nonblank equipment ID without surrounding whitespace |
| component | Required nonblank field in the default structured format |
| issue | Nonblank issue text in the default structured format |
| action | Header required in default format; value may be blank |

Use UTF-8. Malformed rows, duplicate IDs or headers, missing required identities,
and invalid dates are rejected. Keep original bytes: source hashes identify the
input version but do not store a backup. CSV evidence rows are logical records;
a multiline quoted field can occupy more than one physical line.

For a differently named narrative export, `data/demo/company_profile.json` is:

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

Profiles require identity/date mappings and either narrative or issue text.
In narrative mode, action is extracted from the narrative rather than separately
mapped. See the demo for the complete supported format. Extra export columns
are ignored. No fuzzy equipment-ID matching or cross-file merging is performed.
Use `--data-kind user-supplied` for real exports; this is a declaration, not proof
of authenticity. Public data retains its own provenance and redistribution terms.

Scope comes from flags, with inclusive dates:

```bash
maintlog search data/demo/pump_records.csv --data-kind synthetic --query "bearing vibration" --asset-id PUMP-001 --start 2026-01-01 --end 2026-01-31 --output artifacts/scoped-search.json
```

Top-k limits search results. A full-scope aggregate has different counting semantics.
Never interpret a record count as distinct failures, repairs, or verified outcomes.

## Review lifecycle

1. Create the replay or local JSON run and HTML review shown in README.
2. Open the HTML and inspect the original records, proposed fields, and action status.
3. Accept, reject, or correct fields as supported; supply a reviewer name and notes.
4. Download decisions and save them as `artifacts/review-decisions.json`.
5. Import them and generate the reviewed brief:

```bash
maintlog-review artifacts/demo-run.json --decisions artifacts/review-decisions.json --database artifacts/reviews.sqlite3
maintlog reviewed-brief data/demo/company_export.csv --data-kind synthetic --profile data/demo/company_profile.json --asset-id PUMP-001 --review-report artifacts/demo-run.json --database artifacts/reviews.sqlite3 --output artifacts/reviewed-brief.json
```

The commands require the generated demo run and downloaded decisions. Decisions
are bound to the exact run hash. Source records are not changed. The SQLite store
preserves review events; importing decisions again adds events. Record acceptance
alone does not approve fields. Incomplete field/status review is not eligible for
reviewed aggregation. Changed source/profile/vocabulary needs a compatible new
review; do not reuse approvals across source versions.

The self-contained review page makes no network calls. Unsaved choices are lost
on refresh until downloaded. Reviewer judgments are attributed, not infallible.

## Local model prerequisites

Start and configure llama.cpp independently. The current adapter expects a
loopback HTTP OpenAI-compatible chat endpoint supporting JSON-object responses.
For the README example, its accepted model ID must be `qwen35-4b`.
Inspect the advertised IDs with:

```bash
curl http://127.0.0.1:8081/v1/models
```

Use the exact accepted ID in `--model`. The recorded batch used a server-advertised
4096-token context; model alias and advertised metadata do not identify exact
weight bytes. Keep model-file/server versions and hashes in reproducibility records.
Default commands do not download weights or connect without an explicit backend.

Character caps and token budgets differ. A 10,000-character context cap does not
guarantee a 4096-token fit. Measure with the chosen server tokenizer and record
limits. Client timeout does not guarantee server-side generation cancellation.

## Outcomes and troubleshooting

Inspect JSON status and completion fields; process exit alone does not establish
answer quality. The inspected CLI returns 0 for supported normal outcomes,
including clarification/no-match cases; 2 for input/runtime errors; and 3 for
non-successful agent outcomes. Other commands have their own result semantics.
The comparison command saves scores even when a task score fails, so use the
report checker for the declared synthetic CI fixture.

| Symptom | Action |
| --- | --- |
| Python version error | Activate Python 3.11 and inspect `python --version` |
| Agent import error | Install `requirements-agent.lock` and run `pip check` |
| Connection/model error | Check the loopback endpoint and advertised model ID |
| context_limit | Inspect token needs and large narratives; narrow explicit scope or use a measured configuration |
| Invalid quote or field proposal | Preserve the failure trace; inspect the source and validator rather than accepting unsupported text |
| needs_clarification | Start a new run with clearer question and explicit scope |
| no_matches | Inspect source, scope, query, and normalization; do not treat it as proof of no relevant history |
| Input/output collision | Choose a new output path; preserve original inputs |
| Low replay/task score | Read per-case metrics; a saved report is not a passed evaluation |

Run `maintlog --help`, `maintlog-review --help`, or `maintlog-compare --help` for
the installed command options. Report a minimal synthetic reproduction, version,
Python/OS, backend/model details, command, expected outcome, and sanitized error.

## Privacy and support

Exports, prompts, traces, reports, downloaded decisions, and review databases may
contain private records. Keep them out of public issues and commits. A .gitignore
does not untrack previously committed files. Separate organization inputs and
databases; this project has no multi-tenant authorization or retention service.

For ordinary bugs and focused features, use the Maintlog issue forms in
AppliedAI_Lab. For vulnerabilities, follow the repository security policy and
its activation status. No commercial support or response-time guarantee is offered.
