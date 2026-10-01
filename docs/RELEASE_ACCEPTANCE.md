# Release acceptance candidate — 2026-10-01

## Verified evidence

- Python 3.11: 125 tests passed; lint and formatting passed.
- Public snapshots: bundled evaluator completed with hash-checked inputs. These results concern normalization and schema coverage, not live model extraction accuracy.
- Existing synthetic comparison: 27 replay workflow runs (three cases, three trials, three workflows); all nine agent replay runs met declared labels. Replay is mechanics evidence.
- Nine new synthetic release cases: source/label validation and scripted graph checks passed. These cases have not been run with the live model here.
- User-supplied Qwen run 06: ready_for_review; requirements met; seven calls; 13.391 seconds; zero errors. Planned and completed statuses match source wording. Repair-outcome qualification is preserved in the source/HTML, but not included in the extracted problem. No live retry recovery was exercised.

## Frozen acceptance protocol

Run scripts/release_check.py on the user's Windows server with Python 3.11 and Ruff 0.16.9 installed. It first runs regression checks and public evaluation, then compares deterministic, fixed model workflow and agent on both suites, three trials each. Total: 36 runs per workflow, 108 workflow runs; 72 use a model backend, although the empty-scope cases need no requests. Trials use temperature zero and are repeated executions, not independent random samples. The existing demo is tuned development data; nine new cases are synthetic acceptance data, not a credible general-purpose benchmark or blinded holdout.

The gate requires every agent run to satisfy the existing strict oracle: exact record set, exact labeled span boundaries, statuses and aggregate groups. Alternative semantically valid span boundaries can fail this strict gate; report that distinction when reviewing failures. Fixed/deterministic results are comparison evidence, not agent release gates. No quality threshold is changed after observing results. No prompt or source changes during a run.

The runner writes complete raw traces, metrics and summary into a timestamped artifacts directory. A suite interrupted before completion must be rerun; completed earlier suites remain saved. It creates freeze-manifest.json only if all agent checks pass and source hashes remain unchanged. The manifest includes source hashes and model/server file hashes. Supplied file identities do not prove the running server loaded those files; record server startup configuration separately.

A passing gate freezes a synthetic acceptance release, not production readiness, commercial usefulness, public-dataset LLM performance or robust live error recovery. The current claim is evidence-linked equipment-history review requiring human approval. No autonomous diagnosis, repair verification or device control is established.

## User command

From maintlog-intelligence with the activated Python 3.11 environment:

```bash
python -m pip install ruff==0.16.9
python scripts/release_check.py \
  --model qwen35-4b \
  --base-url http://127.0.0.1:8081/v1 \
  --model-file "F:/AI/2.llamacpp/models/_unpinned/Qwen3.5-4B-Q4_K_M.gguf" \
  --server-file "F:/AI/2.llamacpp/llama-server.exe"
```

If BLOCKED, preserve the summary and raw traces; no freeze manifest is issued. If PASS, review baseline comparisons and remaining limitations before creating a Git tag. This package does not commit, push or tag the user's repository.
