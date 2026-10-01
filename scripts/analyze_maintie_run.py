"""Inspect frozen MaintIE predictions without making model calls."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

CLASSES = {
    "PhysicalObject",
    "State",
    "Process",
    "Activity",
    "Property",
}


def entity_keys(entities, tokens, *, gold=False):
    result = set()

    for entity in entities:
        start = entity["start"]
        end = entity["end"]
        kind = entity["type"]

        if gold:
            kind = kind.split("/")[0]

        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(tokens)
            or kind not in CLASSES
        ):
            raise ValueError(f"Invalid entity: {entity}")

        key = (start, end, kind)
        if not gold and key in result:
            raise ValueError(f"Duplicate prediction: {entity}")

        result.add(key)

    return result


def describe(keys, tokens):
    return [
        {
            "start": start,
            "end": end,
            "type": kind,
            "text": " ".join(tokens[start:end]),
        }
        for start, end, kind in sorted(keys)
    ]


def calculate_metrics(tp, fp, fn):
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/public/maintie/gold_release.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        parser.error("Output already exists; choose a new filename.")

    source_bytes = args.data.read_bytes()
    dataset = json.loads(source_bytes)
    run = json.loads(args.run.read_text(encoding="utf-8"))

    digest = hashlib.sha256(source_bytes).hexdigest()
    if digest != run["dataset_sha256"]:
        raise ValueError("Dataset hash does not match the frozen run.")

    if run.get("split") != "validation":
        raise ValueError("This diagnostic tool is restricted to validation.")

    totals = Counter()
    categories = Counter()
    failures = Counter()
    details = []
    seen = set()
    exact_matches = 0

    for row in run["rows"]:
        index = row["record_index"]
        if type(index) is not int or not 0 <= index < len(dataset) or index in seen:
            raise ValueError(f"Invalid or duplicate record index: {index}")
        seen.add(index)

        source = dataset[index]
        tokens = source["tokens"]
        gold = entity_keys(source["entities"], tokens, gold=True)

        error = row.get("error")
        if error is not None:
            predicted = set()
            failures[error] += 1
        else:
            prediction = row["prediction"]
            if not isinstance(prediction, dict):
                raise ValueError(f"Missing valid prediction for record {index}")
            predicted = entity_keys(prediction["entities"], tokens)

        missing = gold - predicted
        extra = predicted - gold
        matched = gold & predicted
        exact_matches += predicted == gold

        totals["tp"] += len(matched)
        totals["fp"] += len(extra)
        totals["fn"] += len(missing)

        for start, end, kind in missing:
            if error is not None:
                category = "failed_response"
            elif any(a == start and b == end for a, b, _ in predicted):
                category = "same_span_wrong_class"
            elif any(
                label == kind and a < end and start < b for a, b, label in predicted
            ):
                category = "same_class_overlapping_span"
            else:
                category = "no_overlapping_same_class_prediction"
            categories[category] += 1

        if missing or extra or error is not None:
            details.append(
                {
                    "record_index": index,
                    "text": source["text"],
                    "tokens": tokens,
                    "error": error,
                    "gold": describe(gold, tokens),
                    "predicted": describe(predicted, tokens),
                    "missing": describe(missing, tokens),
                    "extra": describe(extra, tokens),
                }
            )

    if len(seen) != run["records"]:
        raise ValueError("Record count disagrees with the run metadata.")

    reproduced = calculate_metrics(totals["tp"], totals["fp"], totals["fn"])
    for name in ("tp", "fp", "fn"):
        if reproduced[name] != run["micro"][name]:
            raise ValueError(f"Frozen metric does not reproduce: {name}")

    if exact_matches != run["exact_record_matches"]:
        raise ValueError("Exact-record count does not reproduce.")

    if sum(failures.values()) != run["failed_responses"]:
        raise ValueError("Failure count does not reproduce.")

    summary = {
        "records": len(seen),
        "exact_record_matches": exact_matches,
        "failed_responses": sum(failures.values()),
        "micro": reproduced,
        "missed_entity_diagnostics": dict(categories),
        "response_errors": dict(failures),
    }
    report = {
        "source_run": str(args.run),
        "source_run_sha256": hashlib.sha256(args.run.read_bytes()).hexdigest(),
        "dataset_sha256": digest,
        "model_calls": 0,
        "predictions_changed": False,
        "summary": summary,
        "interpretation": (
            "Validation diagnostics only. Overlap categories explain errors; "
            "they do not relax exact-span scoring. Failed responses remain "
            "empty predictions. Raw failed responses are unavailable when "
            "the original runner did not preserve them."
        ),
        "errors": details,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    print(json.dumps(summary, indent=2))
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
