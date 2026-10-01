"""Run local release acceptance; emit a freeze manifest only when all agent cases pass."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from maintlog.comparison import compare, load_cases

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot():
    paths = []
    for directory in ("src", "tests", "data/demo", "data/release", "scripts"):
        paths.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    paths.extend(ROOT.glob("requirements*.lock"))
    paths.append(ROOT / "pyproject.toml")
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-file", type=Path, required=True)
    parser.add_argument("--server-file", type=Path, required=True)
    parser.add_argument("--model", default="qwen35-4b")
    parser.add_argument("--base-url", default="http://127.0.0.1:8081/v1")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11):
        parser.error("Python 3.11 required")
    for path in (args.model_file, args.server_file):
        if not path.is_file():
            parser.error(f"File not found: {path}")
    before = snapshot()
    output = (
        ROOT
        / "artifacts"
        / ("release-check-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    )
    output.mkdir(parents=True)
    model_identity = {
        "model_file": str(args.model_file),
        "model_sha256": sha(args.model_file),
        "server_file": str(args.server_file),
        "server_sha256": sha(args.server_file),
        "alias": args.model,
        "base_url": args.base_url,
    }
    # Stop before live tests if regression checks fail.
    checks = [
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"],
        [sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "scripts"],
        [
            sys.executable,
            "-m",
            "maintlog.evaluation",
            "--data-root",
            "data/public",
            "--output-dir",
            str(output / "public"),
        ],
    ]
    for index, command in enumerate(checks):
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (output / f"check-{index + 1}.txt").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
        if result.returncode:
            print(f"BLOCKED: check {index + 1} failed. See {output}", flush=True)
            return 1
    results = []
    for suite in ("data/demo/comparison_cases.json", "data/release/cases.json"):
        path = ROOT / suite
        payload, _ = load_cases(path)
        # Each complete suite is saved; interrupted suites must be rerun.
        # Reuse compare's order rotation and identical inputs for both model workflows.
        print(f"Running {suite}: {len(payload['cases'])} cases x 3 trials.", flush=True)
        report = compare(
            path,
            backend="local",
            model=args.model,
            base_url=args.base_url,
            trials=3,
            max_steps=12,
            timeout=120,
        )
        target = output / (
            "demo-comparison.json" if "demo" in suite else "release-comparison.json"
        )
        target.write_text(
            json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
        )
        results.extend(report["results"])
    after = snapshot()
    agent = [r for r in results if r["workflow"] == "agent"]
    summaries = {}
    for workflow in ("agent", "fixed", "deterministic"):
        rows = [r for r in results if r["workflow"] == workflow]
        summaries[workflow] = {
            "runs": len(rows),
            "labeled_successes": sum(
                r["metrics"]["labeled_task_success"] for r in rows
            ),
            "invalid_decisions": sum(r["metrics"]["invalid_decisions"] for r in rows),
            "model_calls": sum(r["metrics"]["model_calls"] for r in rows),
        }
    passed = (
        bool(agent)
        and all(r["metrics"]["labeled_task_success"] for r in agent)
        and before == after
    )
    summary = {
        "status": "pass" if passed else "blocked",
        "python": platform.python_version(),
        "model_identity": model_identity,
        "source_unchanged": before == after,
        "workflows": summaries,
        "failed_agent_cases": [
            {"trial": r["trial"], "case_id": r["case_id"], "metrics": r["metrics"]}
            for r in agent
            if not r["metrics"]["labeled_task_success"]
        ],
        "gate": "Every agent run must meet strict record, span, status and aggregate labels. Baselines are comparisons, not release gates.",
        "limitations": "Synthetic acceptance only; exact span boundaries; no production claim. Model/server file identities are declared local files, not proof of loaded server configuration. Recovery is tested offline; live retries depend on model behavior.",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    if passed:
        manifest = {
            "accepted_at_utc": datetime.now(UTC).isoformat(),
            "source_sha256": after,
            "model_identity": model_identity,
            "evidence_directory": output.name,
            "summary_sha256": sha(output / "summary.json"),
        }
        (output / "freeze-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    print(f"{summary['status'].upper()}: {output}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
