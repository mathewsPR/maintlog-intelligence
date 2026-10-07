"""Gate the small synthetic comparison; this is not a model-quality benchmark."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def main() -> int:
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Python 3.11 required")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--trials", type=int, required=True)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if args.trials < 1:
        raise SystemExit("At least one trial is required")
    case_ids = [case["id"] for case in cases["cases"]]
    if not case_ids or len(case_ids) != len(set(case_ids)):
        raise SystemExit("Case IDs must be nonempty and unique")
    digest = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    if (
        report.get("schema_version") != 1
        or report.get("backend") != "replay"
        or report.get("evidence_kind") != "synthetic_replay_mechanics"
        or report.get("data_kind") != "synthetic"
        or cases["source"].get("data_kind") != "synthetic"
        or report.get("cases_sha256") != digest
        or report.get("trials") != args.trials
    ):
        raise SystemExit("Wrong replay configuration, case hash, or provenance")
    expected = {
        (trial, case_id, workflow)
        for trial in range(1, args.trials + 1)
        for case_id in case_ids
        for workflow in ("deterministic", "fixed", "agent")
    }
    seen = set()
    for row in report["results"]:
        identity = (row["trial"], row["case_id"], row["workflow"])
        if identity not in expected or identity in seen:
            raise SystemExit(f"Unexpected or repeated result: {identity}")
        seen.add(identity)
        metrics = row["metrics"]
        if (
            metrics.get("workflow_complete") is not True
            or metrics.get("exact_record_set") is not True
            or (
                row["workflow"] != "deterministic"
                and metrics.get("labeled_task_success") is not True
            )
        ):
            raise SystemExit(f"Synthetic replay regression: {identity}")
    if seen != expected:
        raise SystemExit("Comparison results are missing")
    print(f"Synthetic replay checks passed for {len(seen)} workflow trials")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
