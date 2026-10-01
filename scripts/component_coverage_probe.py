"""Measure source-backed component candidate coverage without model calls."""

import argparse
import json
import re
from pathlib import Path

from maintlog.comparison import load_cases
from maintlog.component_selection import component_candidates

# Manually declared development terminology, not learned from evaluation labels.
# These suites have already been inspected: this is a development experiment,
# not evidence of performance on unseen data.
COMPONENT_TERMS = (
    "bearing",
    "bearings",
    "brg",
    "belt",
    "belts",
    "compressor",
    "coupling",
    "couplings",
    "fan",
    "fans",
    "filter",
    "filters",
    "gear",
    "gears",
    "gearbox",
    "gasket",
    "gaskets",
    "impeller",
    "motor",
    "motors",
    "pump",
    "pumps",
    "seal",
    "seals",
    "sensor",
    "sensors",
    "shaft",
    "shafts",
    "valve",
    "valves",
)

# Avoid extracting a term from inside a longer identifier.
TERM_PATTERN = re.compile(
    r"(?<![\w/-])(?:"
    + "|".join(
        re.escape(term)
        for term in sorted(COMPONENT_TERMS, key=lambda term: (-len(term), term))
    )
    + r")(?![\w/-])",
    re.IGNORECASE,
)


def expanded_candidates(source):
    """Append literal terminology matches; preserve existing candidate IDs."""
    candidates = dict(component_candidates(source))
    seen = {(span["field"], span["start"], span["end"]) for span in candidates.values()}

    for field in ("issue_raw", "narrative_raw"):
        text = source[field]
        for match in TERM_PATTERN.finditer(text):
            location = (field, match.start(), match.end())
            if location in seen:
                continue
            seen.add(location)
            candidates[f"c{len(candidates) + 1}"] = {
                "field": field,
                "start": match.start(),
                "end": match.end(),
                "quote": match.group(),
            }

    return candidates


def location(span):
    return span["field"], span["start"], span["end"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "suites",
        nargs="+",
        type=Path,
    )
    args = parser.parse_args()

    totals = {
        "labeled_nonnull_components": 0,
        "baseline_exact_coverage": 0,
        "expanded_exact_coverage": 0,
        "baseline_candidates": 0,
        "expanded_candidates": 0,
    }

    for path in args.suites:
        payload, records = load_cases(path)
        by_id = {record.record_id: record for record in records}

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

                # Generate both candidate sets from source fields only.
                baseline = component_candidates(source)
                expanded = expanded_candidates(source)

                totals["baseline_candidates"] += len(baseline)
                totals["expanded_candidates"] += len(expanded)

                # Consult labels only after candidate generation, for scoring.
                gold = reference["fields"]["component"]
                baseline_covered = None
                expanded_covered = None

                if gold is not None:
                    totals["labeled_nonnull_components"] += 1
                    baseline_covered = any(
                        location(span) == location(gold) for span in baseline.values()
                    )
                    expanded_covered = any(
                        location(span) == location(gold) for span in expanded.values()
                    )
                    totals["baseline_exact_coverage"] += int(baseline_covered)
                    totals["expanded_exact_coverage"] += int(expanded_covered)

                print(
                    json.dumps(
                        {
                            "suite": str(path),
                            "case": case["id"],
                            "record_id": record_id,
                            "baseline_exact_coverage": baseline_covered,
                            "expanded_exact_coverage": expanded_covered,
                            "baseline_candidates": baseline,
                            "expanded_candidates": expanded,
                            "gold_component": gold,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    print(json.dumps({"totals": totals}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
