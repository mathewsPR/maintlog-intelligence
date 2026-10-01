"""Run a fixed training-only few-shot MaintIE validation experiment."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from maintlog import maintie_benchmark as benchmark

VERSION = "train-examples-v3"
EXAMPLE_COUNT = 8


def digest(data):
    return hashlib.sha256(data).hexdigest()


def example_features(keys):
    """Describe annotation structures without consulting evaluation labels."""
    features = {kind for _, _, kind in keys}

    if any(end - start > 1 and kind == "Activity" for start, end, kind in keys):
        features.add("multiword_activity")

    objects = [(start, end) for start, end, kind in keys if kind == "PhysicalObject"]
    if len(objects) > 1:
        features.add("multiple_objects")

    if any(
        a <= c and d <= b and (a, b) != (c, d) for a, b in objects for c, d in objects
    ):
        features.add("nested_objects")

    if "Activity" not in features and ("State" in features or "Process" in features):
        features.add("condition_without_activity")

    return features


def select_examples(records, train_indices):
    """Deterministically cover classes and structures using training only."""
    candidates = []

    for index in train_indices:
        record = records[index]
        keys = benchmark.entity_keys(
            record["entities"], len(record["tokens"]), gold=True
        )
        if not keys:
            continue

        rank = digest(
            json.dumps(
                {
                    "text": record["text"],
                    "tokens": record["tokens"],
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        )
        candidates.append(
            {
                "record_index": index,
                "keys": keys,
                "features": example_features(keys),
                "rank": rank,
            }
        )

    if len(candidates) < EXAMPLE_COUNT:
        raise ValueError("Insufficient nonempty training examples")

    # Rare classes receive greater weight, calculated from training only.
    frequencies = {
        label: sum(label in item["features"] for item in candidates)
        for label in benchmark.CLASSES
    }
    weights = {
        label: 1 / frequency for label, frequency in frequencies.items() if frequency
    }
    weights.update(
        {
            "multiword_activity": 1,
            "multiple_objects": 1,
            "nested_objects": 1,
            "condition_without_activity": 1,
        }
    )

    covered = set()
    selected = []

    for _ in range(EXAMPLE_COUNT):

        def priority(item):
            gain = sum(
                weights.get(feature, 1) for feature in item["features"] - covered
            )
            # Prefer compact examples after feature coverage.
            return (
                -gain,
                len(records[item["record_index"]]["tokens"]),
                item["rank"],
                item["record_index"],
            )

        chosen = min(candidates, key=priority)
        candidates.remove(chosen)
        selected.append(chosen)
        covered.update(chosen["features"])

    required = {label for label, frequency in frequencies.items() if frequency}
    if not required <= covered:
        raise ValueError("Selected examples do not cover training classes")

    return selected


def build_prompt(records, selected):
    examples = []

    for item in selected:
        record = records[item["record_index"]]
        examples.append(
            {
                "input": {
                    "text": record["text"],
                    "tokens": [
                        {"index": index, "token": token}
                        for index, token in enumerate(record["tokens"])
                    ],
                },
                "output": {
                    "entities": [
                        {"start": start, "end": end, "type": kind}
                        for start, end, kind in sorted(item["keys"])
                    ]
                },
            }
        )

    # Do not include record identifiers or fine-grained labels in the prompt.
    prompt = (
        benchmark.SYSTEM
        + "\nThe following are annotated training examples of the same task.\n"
        + "Follow their entity boundaries and top-level class usage.\n"
        + json.dumps(examples, ensure_ascii=False, separators=(",", ":"))
        + "\nApply the same annotation task to the next supplied input.\n"
    )
    return prompt, examples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/public/maintie/gold_release.json"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/benchmarks/maintie/split_manifest.json"),
    )
    parser.add_argument("--model", default="qwen35-4b")
    parser.add_argument("--base-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if sys.version_info[:2] != (3, 11):
        parser.error("Python 3.11 required")
    if args.output.exists():
        parser.error("Output already exists; choose a new filename")

    raw = args.data.read_bytes()
    records = json.loads(raw)
    manifest_raw = args.manifest.read_bytes()
    manifest = json.loads(manifest_raw)

    if digest(raw) != manifest["source_sha256"]:
        raise ValueError("Dataset does not match split manifest")
    if digest(benchmark.SYSTEM.encode("utf-8")) != (benchmark.BASELINE_PROMPT_SHA256):
        raise ValueError("Frozen baseline prompt was modified")

    splits = benchmark.validate_manifest(records, manifest)
    selected = select_examples(records, splits["train"])
    selected_ids = [item["record_index"] for item in selected]

    if not set(selected_ids) <= set(splits["train"]):
        raise ValueError("Example selection escaped the training partition")
    if set(selected_ids) & (set(splits["validation"]) | set(splits["test"])):
        raise ValueError("Training examples overlap evaluation records")

    prompt, examples = build_prompt(records, selected)
    provenance = {
        "method": "fixed_train_feature_coverage_v1",
        "example_count": EXAMPLE_COUNT,
        "example_record_indices": selected_ids,
        "example_features": {
            str(item["record_index"]): sorted(item["features"]) for item in selected
        },
        "examples_sha256": digest(
            json.dumps(
                examples,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ),
        "dataset_sha256": digest(raw),
        "manifest_sha256": digest(manifest_raw),
        "wrapper_sha256": digest(Path(__file__).read_bytes()),
        "selection_uses_validation_labels": False,
        "selection_uses_test_labels": False,
    }

    print(json.dumps(provenance, indent=2), flush=True)

    # Register one experiment without modifying the benchmark module.
    benchmark.PROMPTS[VERSION] = prompt
    original_argv = sys.argv
    sys.argv = [
        original_argv[0],
        "--data",
        str(args.data),
        "--manifest",
        str(args.manifest),
        "--model",
        args.model,
        "--base-url",
        args.base_url,
        "--timeout",
        str(args.timeout),
        "--limit",
        str(len(splits["validation"])),
        "--prompt-version",
        VERSION,
        "--baseline-run",
        str(args.baseline_run),
        "--output",
        str(args.output),
    ]

    try:
        result = benchmark.main()
    finally:
        sys.argv = original_argv

    # Add experiment provenance to the newly produced report.
    report = json.loads(args.output.read_text(encoding="utf-8"))
    report["training_examples"] = provenance
    temporary = args.output.with_name(args.output.name + ".provenance.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    temporary.replace(args.output)

    return result


if __name__ == "__main__":
    raise SystemExit(main())
