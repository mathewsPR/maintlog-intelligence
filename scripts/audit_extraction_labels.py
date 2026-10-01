"""Audit existing extraction labels without changing annotations or scores."""

import argparse
import hashlib
import json
from pathlib import Path

from maintlog.comparison import load_cases
from maintlog.component_selection import component_candidates


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def location(span):
    return span["field"], span["start"], span["end"]


def audit_suite(path):
    payload, records = load_cases(path)
    by_id = {record.record_id: record for record in records}
    findings = []

    labeled_components = 0
    covered_components = 0
    period_counts = {
        name: {"with_terminal_period": 0, "without_terminal_period": 0}
        for name in ("problem", "action")
    }

    for case in payload["cases"]:
        for record_id, reference in case.get("expected_fields", {}).items():
            record = by_id[record_id]
            source = {
                name: getattr(record, name)
                for name in (
                    "component",
                    "issue_raw",
                    "action_raw",
                    "narrative_raw",
                )
            }

            # Candidate generation receives only original source fields.
            candidates = component_candidates(source)

            # Labels are consulted exclusively for this offline audit.
            fields = reference["fields"]
            component = fields["component"]
            flags = []

            if component is not None:
                labeled_components += 1
                covered = any(
                    location(candidate) == location(component)
                    for candidate in candidates.values()
                )
                covered_components += int(covered)
                if not covered:
                    flags.append("gold_component_absent_from_identifier_candidates")
            else:
                covered = None
                if candidates:
                    flags.append("null_component_with_identifier_candidates")

            for name in ("problem", "action"):
                span = fields[name]
                if span is None:
                    continue

                quote = span["quote"]
                period_key = (
                    "with_terminal_period"
                    if quote.endswith(".")
                    else "without_terminal_period"
                )
                period_counts[name][period_key] += 1

                if quote != quote.strip():
                    flags.append(f"{name}_contains_boundary_whitespace")

                if ";" in quote:
                    flags.append(f"{name}_contains_semicolon_review_needed")

            findings.append(
                {
                    "case_id": case["id"],
                    "record_id": record_id,
                    "identifier_candidate_coverage": covered,
                    "flags": flags,
                    "component_candidates": candidates,
                    "labeled_fields": fields,
                    "action_status": reference.get("action_status", "unknown"),
                }
            )

    return {
        "suite": str(path),
        "cases_sha256": sha(path),
        "source_identity": payload["source"],
        "labeled_nonnull_components": labeled_components,
        "identifier_candidate_coverage": covered_components,
        "terminal_period_counts": period_counts,
        "findings": findings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suites", nargs="+", type=Path)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("docs/EXTRACTION_CONTRACT_V2_DRAFT.md"),
    )
    args = parser.parse_args()

    report = {
        "audit_version": 1,
        "contract": {
            "path": str(args.contract),
            "sha256": sha(args.contract),
            "status": "draft_not_runtime_policy",
        },
        "interpretation": (
            "Review flags only. Candidate absence measures generator coverage; "
            "candidate presence does not establish semantic relevance. "
            "A final period may belong to an abbreviation. "
            "No annotations, runtime settings, or release gates were changed."
        ),
        "suites": [audit_suite(path) for path in args.suites],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
