"""Rescore frozen predictions against v1/v2 labels without model calls."""

import argparse
import hashlib
import json
from pathlib import Path

from maintlog.comparison import load_cases, score_case

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rescore(report_path, v1_path, v2_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    v1, _ = load_cases(v1_path)
    v2, _ = load_cases(v2_path)

    if report.get("source") != v1["source"]:
        raise ValueError(f"Report source identity differs: {report_path}")
    if v1["source"] != v2["source"]:
        raise ValueError("V1 and v2 must use identical source identities")
    if report.get("cases_sha256") != sha(v1_path):
        raise ValueError(f"Report annotation hash differs: {report_path}")

    v1_cases = {case["id"]: case for case in v1["cases"]}
    v2_cases = {case["id"]: case for case in v2["cases"]}
    if set(v1_cases) != set(v2_cases):
        raise ValueError("V1 and v2 case IDs differ")

    seen = set()
    rows = []

    for row in report["results"]:
        key = row["trial"], row["workflow"], row["case_id"]
        if key in seen:
            raise ValueError(f"Duplicate saved result: {key}")
        seen.add(key)

        case_id = row["case_id"]
        old_metrics = score_case(row["run"], v1_cases[case_id])
        new_metrics = score_case(row["run"], v2_cases[case_id])

        if old_metrics != row["metrics"]:
            raise ValueError(
                f"Recorded v1 metrics were not reproduced: {key}. "
                "Check scorer-version differences before interpreting results."
            )

        rows.append(
            {
                "trial": row["trial"],
                "case_id": case_id,
                "workflow": row["workflow"],
                "v1_success": old_metrics["labeled_task_success"],
                "v2_success": new_metrics["labeled_task_success"],
                "v1_metrics": old_metrics,
                "v2_metrics": new_metrics,
            }
        )

    trials = report["trials"]
    expected = {
        (trial, workflow, case_id)
        for trial in range(1, trials + 1)
        for workflow in ("agent", "fixed", "deterministic")
        for case_id in v1_cases
    }
    if seen != expected:
        raise ValueError(f"Incomplete or unexpected report rows: {report_path}")

    return {
        "report": str(report_path),
        "report_sha256": sha(report_path),
        "v1_cases_sha256": sha(v1_path),
        "v2_cases_sha256": sha(v2_path),
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-run", type=Path, required=True)
    parser.add_argument("--release-run", type=Path, required=True)
    args = parser.parse_args()

    suites = [
        rescore(
            args.demo_run,
            ROOT / "data/demo/comparison_cases.json",
            ROOT / "data/demo/comparison_cases_v2.json",
        ),
        rescore(
            args.release_run,
            ROOT / "data/release/cases.json",
            ROOT / "data/release/cases_v2.json",
        ),
    ]

    rows = [row for suite in suites for row in suite["rows"]]
    summary = {}

    for workflow in ("agent", "fixed", "deterministic"):
        selected = [row for row in rows if row["workflow"] == workflow]
        summary[workflow] = {
            "runs": len(selected),
            "v1_successes": sum(row["v1_success"] for row in selected),
            "v2_successes": sum(row["v2_success"] for row in selected),
            "changed_outcomes": [
                {
                    "trial": row["trial"],
                    "case_id": row["case_id"],
                    "v1_success": row["v1_success"],
                    "v2_success": row["v2_success"],
                }
                for row in selected
                if row["v1_success"] != row["v2_success"]
            ],
        }

    output = {
        "model_calls_made_by_rescoring": 0,
        "predictions_changed": False,
        "interpretation": (
            "Same frozen predictions scored against two annotation versions. "
            "Differences measure annotation effects, not model improvement. "
            "This does not change the v1 release gate or establish a v2 release."
        ),
        "summary": summary,
        "suites": suites,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
