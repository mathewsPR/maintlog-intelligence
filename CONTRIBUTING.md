# Contributing to Maintlog Intelligence

Use a focused issue or change. Follow the
[code of conduct](../.github/CODE_OF_CONDUCT.md).
Maintlog is an ordinary folder in AppliedAI_Lab, maintained by @mathewsPR.

## Setup

```bash
git clone https://github.com/mathewsPR/AppliedAI_Lab.git
cd AppliedAI_Lab
git switch -c fix/maintlog-focused-change
cd maintlog-intelligence
```

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

Then, from the project folder:

```bash
python -m pip install -r requirements-agent.lock
python -m pip install -r requirements-ci.txt
python -m pip check
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m coverage run -m unittest discover -s tests -v
python -m coverage report --fail-under=75
maintlog-compare data/demo/comparison_cases.json --backend replay --trials 3 --output artifacts/ci-comparison.json
python scripts/check_replay_report.py artifacts/ci-comparison.json data/demo/comparison_cases.json --trials 3
git diff --check
```

The snapshot includes `-e .[agent]`, so it installs the editable agent extra.
It has no hashes. Update runtime pins deliberately in a fresh Python 3.11
environment, separate from CI tools. Inspect `pip freeze`, replace filesystem
editable paths with `-e .[agent]`, and validate installation on both CI platforms.
Dependabot does not automatically synchronize this custom snapshot filename.

Add regression tests for changed behavior, including rejection or recovery where
relevant. Use synthetic minimal records. Keep the existing unittest runner and
test discovery intact. Do not weaken validators, labels, or coverage exclusions.

Run the security, build, and fresh-install commands in
[release guidance](docs/RELEASE.md). Run the relevant live evaluation for changes
to model behavior, extraction, prompts, budgets, or evaluation semantics.
Replay is a mechanics check, not measured model quality.

## Pull requests

Use the Maintlog PR template, explain final behavior, and report checks actually
run. Select it using `template=maintlog.md` in the PR URL if needed. Update relevant
docs and the Unreleased changelog. Wait for CI and maintainer review; solo-owned
changes must not depend on an unavailable second reviewer. Discuss substantial
architecture changes in an issue first.

Original contributions use Apache-2.0. Retain third-party notices and explain the
origin and permissions of copied code or new data. Do not commit private records,
credentials, model weights, or unsanitized traces. Stage reviewed files explicitly.
