"""Run local release acceptance; freeze only when all agent cases pass."""

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
            path
            for path in (ROOT / directory).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )
    paths.extend(ROOT.glob("requirements*.lock"))
    paths.append(ROOT / "pyproject.toml")
    return {
        str(path.relative_to(ROOT)).replace("\\", "/"): sha(path)
        for path in sorted(paths)
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-file", type=Path, required=True)
    parser.add_argument("--server-file", type=Path, required=True)
    parser.add_argument("--model", default="qwen35-4b")
    parser.add_argument("--base-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--component-selection", action="store_true")
    parser.add_argument("--boundary-adapter", action="store_true")
    parser.add_argument("--focused-status-repair", action="store_true")
    args = parser.parse_args()

    if sys.version_info[:2] != (3, 11):
        parser.error("Python 3.11 required")

    for path in (args.model_file, args.server_file):
        if not path.is_file():
            parser.error(f"File not found: {path}")

    extraction_configuration = {
        "component_selection": args.component_selection,
        "boundary_adapter": args.boundary_adapter,
        "focused_status_repair": args.focused_status_repair,
    }

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

    print(
        "Extraction configuration: "
        + json.dumps(extraction_configuration, sort_keys=True),
        flush=True,
    )

    # Stop before live evaluation if regression checks fail.
    checks = [
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"],
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "src",
            "tests",
            "scripts",
        ],
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
            result.stdout + result.stderr,
            encoding="utf-8",
        )
        if result.returncode:
            print(
                f"BLOCKED: check {index + 1} failed. See {output}",
                flush=True,
            )
            return 1

    results = []
    suites = (
        "data/demo/comparison_cases.json",
        "data/release/cases.json",
    )

    for suite in suites:
        path = ROOT / suite
        payload, _ = load_cases(path)

        # Completed suites are saved; interrupted suites must be rerun.
        # Both model workflows use identical extraction settings.
        print(
            f"Running {suite}: {len(payload['cases'])} cases x 3 trials.",
            flush=True,
        )
        report = compare(
            path,
            backend="local",
            model=args.model,
            base_url=args.base_url,
            trials=3,
            max_steps=12,
            timeout=120,
            **extraction_configuration,
        )

        target = output / (
            "demo-comparison.json" if "demo" in suite else "release-comparison.json"
        )
        target.write_text(
            json.dumps(report, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        results.extend(report["results"])

    after = snapshot()
    agent = [row for row in results if row["workflow"] == "agent"]

    summaries = {}
    for workflow in ("agent", "fixed", "deterministic"):
        rows = [row for row in results if row["workflow"] == workflow]
        summaries[workflow] = {
            "runs": len(rows),
            "labeled_successes": sum(
                row["metrics"]["labeled_task_success"] for row in rows
            ),
            "invalid_decisions": sum(
                row["metrics"]["invalid_decisions"] for row in rows
            ),
            "model_calls": sum(row["metrics"]["model_calls"] for row in rows),
        }

    passed = (
        bool(agent)
        and all(row["metrics"]["labeled_task_success"] for row in agent)
        and before == after
    )

    summary = {
        "status": "pass" if passed else "blocked",
        "python": platform.python_version(),
        "model_identity": model_identity,
        "extraction_configuration": extraction_configuration,
        "source_unchanged": before == after,
        "workflows": summaries,
        "failed_agent_cases": [
            {
                "trial": row["trial"],
                "case_id": row["case_id"],
                "metrics": row["metrics"],
            }
            for row in agent
            if not row["metrics"]["labeled_task_success"]
        ],
        "gate": (
            "Every agent run must meet strict record, span, status and "
            "aggregate labels. Baselines are comparisons, not release gates."
        ),
        "limitations": (
            "Synthetic acceptance only; exact span boundaries; no production "
            "claim. Model/server file identities are declared local files, "
            "not proof of loaded server configuration. Recovery is tested "
            "offline; live retries depend on model behavior."
        ),
    }

    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    if passed:
        manifest = {
            "accepted_at_utc": datetime.now(UTC).isoformat(),
            "source_sha256": after,
            "model_identity": model_identity,
            "extraction_configuration": extraction_configuration,
            "evidence_directory": output.name,
            "summary_sha256": sha(output / "summary.json"),
        }
        (output / "freeze-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )

    agent_summary = summaries["agent"]
    print(
        f"Agent strict successes: "
        f"{agent_summary['labeled_successes']}/{agent_summary['runs']}",
        flush=True,
    )
    print(f"{summary['status'].upper()}: {output}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
