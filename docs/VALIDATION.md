# Version 0.3 validation — 2026-09-30

Python 3.11.16, Linux. Full output: `reports/test-results.txt`.

- 113 behavioral/integration tests passed with actual LangGraph dependencies.
- Ruff 0.16.9 lint and format checks passed.
- Fresh locked version 0.3 installation completed an installed CLI history replay
  and installed `maintlog-compare` replay comparison.
- HTTP request worker passed local fixture request/usage/redirect checks; a stalled
  HTTP fixture was terminated at the configured client deadline.
- Field correction download logic executed with a Node DOM fixture; its decisions
  imported to SQLite and were reused in a source-bound reviewed brief.
- All 12 public snapshot files passed size/hash checks. Frozen dictionary_v0 test
  baseline scores remain unchanged.
- Normalization development: 9,600 training documents, 1,200 validation documents;
  84 learned entries; reported metrics are development evidence only.
- Paired comparisons: three synthetic cases, three workflows, three replay trials
  (27 outcomes), explicitly labeled mechanics rather than model performance.

The real browser check remains unavailable after the earlier binary download
failure. Windows, Phi-4-mini/RTX 4060 execution, live model accuracy, retrieval
relevance on real queries, and commercial value remain unverified.

## Important regressions

The old empty finish now fails workflow requirements. History reviews require
search, aggregation and inspected final evidence. Narrative finals require field
proposals or explicit unknowns. No-hit search, empty scope, abstention, workflow
completion and independently scored task success are separate outcomes.

Source columns constrain field roles. Clear action/component contradictions,
nearby negation clipping and unsupported non-unknown action states are rejected.
These rules are conservative constraints, not a universal semantic validator.

Review tests verify corrected spans reach counted evidence, record acceptance
alone/partial reviews cannot promote fields, latest rejections supersede approvals,
changed sources invalidate reuse, and invalid corrections create no database write.

Comparison tests verify a completed-but-wrong result fails its external oracle,
wrong aggregate counts fail, scopes match, and fixed-model inputs omit scoring labels.
Replay counters stay zero even on fixture failure; attempted local requests are
counted separately from graph steps.

## Reproduce

```bash
python -m pip install -r requirements-agent.lock
python -m unittest discover -s tests -v
python -m ruff check src tests
python -m ruff format --check src tests
python -m maintlog.evaluation --data-root data/public --output-dir reports
python -m maintlog.normalization_probe --output reports/NORMALIZATION_DEVELOPMENT.json
maintlog-compare data/demo/comparison_cases.json --backend replay --trials 3 --output artifacts/comparison.json
```

Install Ruff 0.16.9 separately for lint reproduction. Agent tests are skipped if
the optional graph dependency is absent; a skipped suite does not validate it.
See README for local model and reviewed-brief commands.
