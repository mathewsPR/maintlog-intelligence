# Versions and releases

Use MAJOR.MINOR.PATCH. During 0.x, incompatible CLI, report, or review-schema
changes advance MINOR; compatible fixes advance PATCH. For 1.x onward, incompatible
public changes advance MAJOR. Internal refactoring alone does not justify a release.

Use Conventional Commits: type(scope): summary. Examples:

```text
fix(maintlog): reject out-of-scope record selection
ci(maintlog): assert synthetic replay metrics
docs(maintlog): clarify development evaluation limits
```

Use `!` and a `BREAKING CHANGE:` footer for incompatible behavior.
Keep reviewed changes under Unreleased in CHANGELOG.md. At release, assign the
verified version and date, summarize user-visible changes and compatibility,
and include validation and known limitations. Do not invent historical entries.

## Local checks

From the project directory in Python 3.11, after contributor checks:

```bash
python -m pip install -r requirements-security.txt
python -m pip check
python -m bandit -r src --severity-level medium --confidence-level medium
python -m pip_audit --skip-editable --strict
python -m build
python -m twine check dist/*
python scripts/check_wheel_install.py
git diff --check
```

Move old dist output aside before building. Keep exactly one current wheel.
The wheel smoke check covers the base package; check fresh agent-extra installation
and live acceptance separately before an agent release.

## Acceptance

- Windows and Ubuntu Python 3.11 CI pass, including security checks.
- No unresolved blocking security findings; unavailable audit service is not a pass.
- Wheel and source distribution build and metadata checks pass.
- Fresh base-wheel check and required agent/live checks pass separately.
- Version agrees across pyproject, README badge, and release entry.
- License, third-party notices, and dataset redistribution rights are reviewed.
- Confirmed copyright declaration and operational private reporting contacts exist.
- Relevant independent answer evaluation and limitations are preserved.
- No private inputs, credentials, model weights, or sensitive traces are included.

Require the `Maintlog required gate` status check after its first successful run.
Do not require an unavailable second reviewer for the solo maintainer. Avoid
commit messages that skip CI. Major Action tags are retained; reviewed immutable
SHA pinning is a later hardening task, not a claim made by this package.

Use project-scoped tags `maintlog-vMAJOR.MINOR.PATCH`. Check generated notes for
unrelated monorepo commits. Publish manually only after acceptance. No automated
publication workflow or release committee is needed now.
