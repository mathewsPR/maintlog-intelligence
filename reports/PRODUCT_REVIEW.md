# Equipment-history review assistant — independent product assessment

Version 0.3 · 2026-09-30 · implementation and measured evidence review

## Recommendation

Build a reusable assistant for reviewing equipment history, beginning with one
validated maintenance workflow. The immediate job is: find relevant earlier
records before an investigation or planning review, inspect what was reported
and what actions were proposed/performed, and retain source evidence and review
choices. The common core can serve different organizations through source-column
profiles and an optional, explicitly selected vocabulary profile.

The current release is an engineering prototype. It has a plausible use case and
reviewable evidence handling, but live model quality and willingness to pay have
not been established. A claim that it helps every person and every company would
exceed the evidence. Companies with recurring equipment records and expensive
history searches are the strongest prospective fit.

## Weaknesses addressed in version 0.3

| Weakness | Implemented correction | Assessment |
| --- | --- | --- |
| Agent could finish without doing the requested work | Explicit history/search/inspect/extract contracts; history requires search, full-scope aggregate, inspected final records and narrative field proposals or explicit unknowns. Empty completion requires a no-hit search. Abstention is explicit. | Workflow bypass fixed; semantic success remains independently scored |
| Action text could be assigned as a component; copied spans could omit negation | Shared field validator constrains source columns, rejects obvious action/component contradictions and nearby negation clipping, and requires explicit cues for non-unknown action status. | Demonstrated regressions fixed; rules do not understand every sentence |
| Six-entry dictionary had very low correction coverage and invented action tense | Default noun-only aliases preserve action wording and identifiers; optional 84-entry vocabulary fitted from training annotations, with policy hashes in source/run provenance. Original dictionary_v0 evaluation remains frozen. | Tense distortion reduced; broader coverage improved on development data only |
| Reviewer could only accept/reject an entire record | Offline per-field acceptance/rejection/correction, exact source spans, explicit action status and SQLite events; complete accepted fields can generate reviewed briefs. Latest incomplete/rejected review supersedes prior approval; changed source/profile invalidates reuse. | Implemented and integration-tested; actual browser interaction unverified |
| No evidence that agent complexity earns its cost | Paired deterministic, fixed-model and tool-choosing-agent harness; common source/scope/query/model settings, rotated workflow order, independent labels for records, fields, status and aggregate counts, latency/request/token reporting. | Measurement capability implemented; model superiority not established |
| HTTP work could exceed the client deadline | Local requests execute in a separate process that can be terminated; stalled-server fixture verifies termination. | Client request bounded; model-server computation is not cancelled |

The source-column profiles, exact asset/inclusive date filters, source spans,
full-scope counts, append-only review events, loopback-only backend and pinned
Python 3.11 installation remain part of the common core. Structured counts use
all scoped rows rather than top-k hits. Reviewed narrative counts include only
eligible reviewed records and report how many scoped rows were excluded.

The model chooses the next tool through a bounded two-node LangGraph loop.
Replay files contain handwritten decisions and are labeled accordingly. Local
inference uses JSON-object responses checked by Python validators. Source-bound
reviewed fields are human judgments, not automatically verified facts.

## What the evidence establishes

| Evidence | Result | Boundary |
| --- | --- | --- |
| Python 3.11.16 behavioral/integration tests | 113 passed with agent dependencies installed | Software contracts and replay graph mechanics; not model accuracy |
| Ruff 0.16.9 | Lint and format checks passed | Code-quality checks, not functional or product proof |
| Fresh locked installation and CLI smoke run | Version 0.3 installed; history replay and comparison CLI passed on Linux Python 3.11.16, LangGraph 1.2.12 | Windows/GPU/model installation not executed |
| Field review download/import/reuse | Node DOM fixture produced a correction; SQLite import and reviewed brief reused its source-bound fields | Actual browser layout/interaction unverified; browser download failed |
| MaintNorm nominal test splits | 1,200 documents; dictionary casefold lexical accuracy 77.18%; unchanged-input 76.96% | Adapted lexical task with privacy-mask units excluded |
| MaintNorm correction quality | Precision 12.79%; recall 0.93%; TP 11, FP 75, FN 1171 | The six-entry dictionary is inadequate for broad normalization |
| Identifier-labeled units | 909/909 source units preserved by dictionary | No measured model preservation or real asset-identity resolution |
| MaintNorm exact-overlap-filtered subset | 1,177 documents; accuracy 77.79%; precision 12.79%; recall 0.98% | Supplementary project-specific subset; near duplicates remain unchecked |
| MaintIE gold snapshot audit | 1,076 records, 3,397 entities, 2,341 relations; valid spans and indices | Schema audit only; no model extraction predictions/scoring |
| Synthetic narrative replay | Search → inspect → extract → aggregate → finish, ready for review | Handwritten decisions; no local LLM call occurred |
| Normalization development comparison | 1,200 validation documents; learned vocabulary accuracy 86.11%, correction precision 99.40%, recall 41.26%; TP 496, FP 3, FN 706 | Development diagnostic after earlier test errors were inspected; not fresh holdout or model accuracy |
| Paired workflow harness | 27 outcomes: three synthetic cases × three workflows × three replay trials | Identical handwritten repetitions verify mechanics; no live-model comparison |
| HTTP deadline | Stalled local HTTP fixture terminated at the client timeout | Does not prove model-server cancellation or hard real-time execution |

See `DATASET_EVALUATION_REPORT.md` and `results.json` for definitions, denominators,
strict/casefold metrics, split overlap, source revisions and hashes. The frozen
dictionary was not tuned after observing its test errors. The new agent does not
change those scores or convert them into agent-performance evidence.

The frozen six-entry dictionary has poor correction precision and recall.
Version 0.3 addresses its specific tense mistake by leaving `repl`, `chk` and
`lub` unchanged in the default retrieval policy. The optional learned vocabulary
makes 499 corrections on validation data, with 496 correct and three incorrect.
It still misses 706 of 1,202 required corrections. Training uses 9,600 documents;
all 1,235 masked source units, including 914 identifier units, were preserved
in this validation run. These numbers do not establish transfer to another company.

The synthetic bearing-history comparison shows the deterministic workflow has
no narrative field predictions, whereas the fixed and agent replay fixtures
supply all six labeled spans. Both model-shaped fixtures pass their handwritten
labels. This does not show an agent advantage over the fixed workflow. Repeated
replays are not independent model trials. Raw measurements and traces are in
`NORMALIZATION_DEVELOPMENT.json` and `WORKFLOW_COMPARISON.json`.

## Why it could be useful

A reviewer can gather relevant records, distinguish a proposed action from a
completed action proposal, inspect unresolved wording after a replacement, and
share a reproducible source-linked review. This could reduce reading and search
time and make missing evidence visible. Those benefits must be measured against
the user’s current spreadsheet or CMMS search workflow.

The synthetic WO-01/WO-02 example illustrates the intended distinction: one
record plans a bearing replacement; the later record says a bearing was replaced
and vibration remains high. The software preserves both statements. It does not
conclude that replacement resolved the fault or identify its cause.

| Prospective user | Possible job | Adaptation needed | Validation status |
| --- | --- | --- | --- |
| Pump service workshop or maintenance contractor | Prepare for an investigation using prior repair records | Stable asset/date fields, source mapping and reviewed terminology | Proposed first pilot; synthetic demonstration only |
| Small equipment owner/facilities team | Review repeated reports before weekly planning | Facility export profile and equipment vocabulary | Candidate next domain; not tested |
| Fleet or manufacturing maintenance team | Review vehicle/machine histories | Organization-specific identities, status semantics, query labels | Not tested |
| Individual with dated equipment service records | Organize and inspect their own history | Suitable CSV and clear identities; simpler packaging | Possible use, not validated demand |
| Large enterprise | Complement existing asset systems with export review | Identity/access controls, integrations, deployment, large-file performance | Current prototype lacks these capabilities |

Accessibility for nontechnical users needs an installer, a guided import/profile
editor, clear data-quality feedback, and a model setup path. Those are release
requirements if “helpful for everyone” includes people who do not use Python.
Language coverage also needs testing; UTF-8 support is not multilingual model
accuracy. The current product is maintenance-specific, not a general assistant
for every business function.

## Principal gaps, in priority order

1. **Live model evidence.** Run the selected local model and record GGUF/model
   version/license, llama.cpp version, context settings, hardware, prompts,
   tool choices, errors, latency and server-reported token usage. This delivery
   did not run Phi-4-mini or the user’s RTX 4060.
2. **Real workflow and data fit.** Observe users performing equipment-history
   reviews; obtain permitted representative exports. Required IDs/dates may be
   missing or inconsistent. Public corpora do not establish real chronology,
   unique events or recurrence.
3. **Extraction quality.** A copied span can still be assigned to the wrong
   field or action status. Column/wording rules reject selected contradictions,
   but a valid span is not proof of the right meaning. Field corrections and reuse
   are implemented; independently labeled live extraction remains unmeasured.
4. **Retrieval quality.** Lexical ranking misses paraphrases and can retrieve
   negated statements. Synthetic relevance labels now exercise the oracle; real
   reviewer relevance judgments, ranking metrics and paraphrase coverage are absent.
5. **Cross-company semantics.** Column mapping does not solve terminology,
   action-state definitions, duplicate event reports, multilingual text or
   organization-specific grouping. Keep explicit profiles and reviewed examples.
6. **Operational delivery.** The strict step limit works; the time deadline is
   enforced on client HTTP work and checked between tools; it does not cancel
   server-side model computation or preempt every local tool. Conversational resume,
   large-file handling, Windows execution, a nontechnical
   installer, cloud adapter and enterprise integrations remain future work.

A single run’s corpus is fixed by explicit flags. Prose in the question does not
set or override asset/date scope. Clarification pauses the run; the user starts a
new one with a clearer question/scope. An empty scope is reported explicitly.

## Next evaluation design

Keep four separate studies, each with its own claim and held-out examples.

| Study | Data and labels | Comparisons | Report |
| --- | --- | --- | --- |
| Normalization | MaintNorm under the existing scoring policy; fresh held-out data for test-informed improvements | Unchanged input, frozen dictionary_v0, improved method | Strict/casefold accuracy, correction precision/recall, identifier preservation, uncertainty and failure classes |
| Extraction | Reviewed MaintIE task mapping plus separately annotated raw narratives/action-status examples | Fixed local-model workflow and agent using the same model/settings | Task-appropriate entity/field precision/recall/F1, exact-span validity, abstention, action-status accuracy and unsupported claims |
| History review | Permitted records with real asset/date identities, relevance judgments and verified counting rules | Current spreadsheet/CMMS search, deterministic search/brief, fixed-model workflow, bounded agent | Recall at k, ranking quality, scope/count correctness, missed relevant records and reviewed task completion |
| Usability/value | Users solving the same representative tasks with balanced task/order assignment | Current workflow versus prototype | Review time, edits, accepted/rejected findings, repeat use, latency and willingness to pay |

PhysicalObject, State and Activity labels in MaintIE are not automatically
component, problem and completed action. Review the mapping before scoring.
The current tool proposes one span per field; it is not a full multi-entity or
relation extractor. MaintIE also lacks labels for all proposed action statuses.
Do not invent dates or asset IDs to score recurrence on that corpus.

Group duplicate texts, keep development/test records separate, and split by
organization/equipment domain where feasible. Previously examined MaintNorm test
errors cannot serve as fresh evidence for an improved dictionary. Start with
approximately 50–100 reviewed examples as an exploratory check, then size the
study to the performance claim and observed uncertainty.

The agent must demonstrate an advantage over a fixed model workflow to justify
its complexity. If it does not improve reviewed task completion enough to offset
extra latency, cost and failure modes, retain the simpler workflow for that task.
Do not set a universal numeric release threshold without learning the actual
cost of missed records and incorrect interpretations in the selected workflow.

## Positioning and market plan

The initial positioning hypothesis is **local, source-linked equipment-history
review from your existing exports**. A service contractor or workshop is a
reasonable first segment to investigate because the export workflow fits the
current product. This is a hypothesis, not measured demand.

The category already has incumbent assistants. MaintainX documents an assistant
that searches asset documentation and work-order history. UpKeep markets Nova
with record-based conversational assistance, scheduled reviews and approval
queues. These are vendor capability descriptions, not independent performance
evidence. Their existence means an agent label or generic maintenance chatbot
is insufficient differentiation.

Sources checked 2026-09-30:
- [MaintainX AI documentation](https://help.getmaintainx.com/ai-basics)
- [UpKeep AI maintenance management](https://upkeep.com/product/ai-maintenance-management/)

The proposed advantage to test is low-friction review of exported records with
local inference and visible source evidence, alongside existing systems. Do not
claim better accuracy, lower cost, reduced downtime or broad superiority until
comparative measurements support it.

Proceed with five to eight discovery interviews, two or three permitted sample
exports, and a timed pilot on the actual review task. Demonstrate a source-linked
review with mistakes and corrections visible. Discuss paid pilots after useful
repeat behavior appears. With authorization, publish a case study reporting
measured review time and missed-record changes, sample size and limitations.
No outreach, customer contact, pricing test or paid pilot occurred in this work.

Pricing should follow observed value, deployment/support costs and willingness
to pay. Avoid estimating subscriptions or promising downtime savings from a
synthetic demo. Expansion should follow independent results in a second company
and equipment domain, then additional profile packs and integrations.

## Release decision

Version 0.3 is ready for developer review and controlled local-model experiments.
The provided README contains installation, replay, local-server, company-profile
and review-import commands. The next decisive gate is actual local inference
plus a permitted real task comparison. Production and universal-usefulness
claims remain unsupported.
