# Architecture and code quality

Maintlog is a Python package and CLI inside the AppliedAI_Lab monorepo. Keep its
existing flat module structure; no service framework or new plugin layer is needed.

| Responsibility | Modules |
| --- | --- |
| Source and settings boundaries | ingestion, cli, scope, vocabulary |
| Records and task requirements | domain, tasks |
| Deterministic reasoning | normalization, retrieval, extraction, brief |
| Model workflow and transport | agent, backends, http_worker |
| Review output and persistence | review, review_store |
| Evaluation and development | comparison, evaluation, normalization_probe |

The CLI parses settings and handles file paths. Core functions take records,
scope, and explicit options. Keep file reads, model calls, HTML rendering, and
database writes at their boundaries. Model output is a proposal that passes
deterministic validation before being included in a report.

Records retain original text and source evidence. Review storage records human
decisions separately. Reports distinguish operational completion, source validity,
and semantic correctness. No layer should silently turn one into another.

## Rules

- Python 3.11 only; annotate new and changed public functions.
- Use snake_case for modules/functions, PascalCase for classes, and UPPER_CASE
  for constants. Prefer domain names such as record_id over vague names.
- Use pathlib, dataclasses, context managers, timezone-aware timestamps, and
  standard-library types. Immutable records fit dataclass(frozen=True).
- Ruff applies import sorting, Python upgrades, basic error checks, and formatting
  at 88 columns. It does not perform full static type checking.
- Reject invalid input at boundaries using clear domain exceptions. Catch only
  errors the boundary can handle. Preserve useful causes; never swallow failures.
- Map failures to documented CLI outcomes; do not return success after partial
  failure or call a budget stop a completed answer.
- Diagnostic logging uses logging.getLogger(__name__). Logs go to stderr;
  machine-readable output goes to stdout or an explicit file. Do not log raw
  narratives, prompts, credentials, or personal details by default.
- Treat detailed traces as sensitive, opt-in evidence with deliberate retention.
- Avoid global mutable state and import-time network or file operations.

A mandatory strict type-checker migration is not needed for this controls change.
Add it when typed boundaries support a useful, consistently passing check.

## Decisions expensive to change

Source identity and provenance fields, review-event schemas, report schemas,
CLI compatibility, package naming, licensing, and dataset split/label semantics
affect existing users or published evidence. Version those changes deliberately.
Internal function layout and tool pins are easier to revise.

## Tests

Keep current test filenames and unittest discovery. Tests may mix unit and
integration cases in one file while the suite is small:

| Layer | Focus |
| --- | --- |
| Unit | Scope, normalization, retrieval, extraction validation, task requirements |
| Integration | CSV to CLI JSON; tool workflow with replay; review to SQLite |
| Installation | Fresh base wheel, console command, result and evidence assertions |
| Evaluation | Synthetic comparison; public audit; independent live comparison |

Important cases include malformed CSV, duplicate IDs, empty scope, output/input
collision, out-of-scope tool requests, invalid quotes/spans, ambiguous action status,
negation, budgets, transport failure, and closed SQLite handles on Windows.

The 75% combined coverage floor is a regression floor, informed by the previously
reported 75.76%. Recompute with branch coverage enabled before accepting this
configuration. The percentage is not proof of reasoning correctness. Prioritize
uncovered transport, recovery, and evidence-handling behavior; do not hide it.
