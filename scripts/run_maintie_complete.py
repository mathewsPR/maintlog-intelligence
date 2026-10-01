"""Partitioned MaintIE evaluation using frozen v4 helpers, with checkpoints."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import run_maintie_fewshot as fewshot
import run_maintie_retrieval as retrieval

from maintlog import maintie_benchmark as benchmark


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def signatures(row):
    return (
        " ".join(row["text"].casefold().split()),
        tuple(token.casefold() for token in row["tokens"]),
    )


def demonstration_prompt(records, train, target, fixed=None, index=None):
    text, tokens = signatures(records[target])
    excluded = {
        item
        for item in train
        if signatures(records[item])[0] == text
        or signatures(records[item])[1] == tokens
    }

    if excluded:
        pool = [item for item in train if item not in excluded]
        fixed = fewshot.select_examples(records, pool)[:4]
        index = retrieval.BM25(records, pool)
    else:
        pool = train
        if fixed is None:
            fixed = fewshot.select_examples(records, pool)[:4]
        if index is None:
            index = retrieval.BM25(records, pool)

    fixed_ids = [item["record_index"] for item in fixed]
    ranked = index.retrieve(records[target]["tokens"], set(fixed_ids), 4)
    ids = fixed_ids + [item for item, _ in ranked]

    if len(ids) != 8 or len(set(ids)) != 8:
        raise ValueError("Expected eight unique demonstrations")
    if not set(ids) <= set(pool) or set(ids) & excluded:
        raise ValueError("Demonstration leakage")

    examples = fixed + [retrieval.training_item(records, item) for item, _ in ranked]
    prompt, _ = fewshot.build_prompt(records, examples)

    return prompt, {
        "fixed_record_indices": fixed_ids,
        "retrieved": [
            {"record_index": item, "bm25_score": score} for item, score in ranked
        ],
        "excluded_target_duplicate_indices": sorted(excluded),
        "prompt_sha256": benchmark.sha(prompt.encode("utf-8")),
    }


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
    parser.add_argument("--v4-run", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--model", default="qwen35-4b")
    parser.add_argument("--base-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if sys.version_info[:2] != (3, 11):
        parser.error("Python 3.11 required")
    if not 0 < args.timeout <= 120:
        parser.error("Timeout must be >0 and <=120")
    if retrieval.FIXED_COUNT != 4 or retrieval.RETRIEVED_COUNT != 4:
        raise ValueError("Frozen v4 demonstration counts changed")
    if benchmark.sha(benchmark.SYSTEM.encode()) != benchmark.BASELINE_PROMPT_SHA256:
        raise ValueError("Frozen instruction prompt changed")

    raw = args.data.read_bytes()
    manifest_raw = args.manifest.read_bytes()
    records = json.loads(raw)
    manifest = json.loads(manifest_raw)

    if benchmark.sha(raw) != manifest["source_sha256"]:
        raise ValueError("Dataset hash mismatch")

    splits = benchmark.validate_manifest(records, manifest)
    provider = benchmark.LocalServer(
        base_url=args.base_url,
        model=args.model,
    )
    configuration = {
        "model": provider.model,
        "base_url": provider.base_url,
        "max_tokens": provider.max_tokens,
        "temperature": 0,
    }

    reference = read_json(args.v4_run)
    identity = {
        "dataset_sha256": benchmark.sha(raw),
        "manifest_sha256": benchmark.sha(manifest_raw),
        "protocol": manifest["protocol"],
        "official_split": False,
    }
    expected_reference = {
        **identity,
        "split": "validation",
        "model_configuration": configuration,
        "prompt_version": retrieval.VERSION,
    }

    for key, value in expected_reference.items():
        if reference.get(key) != value:
            raise ValueError(f"Frozen v4 reference mismatch: {key}")

    if [row["record_index"] for row in reference["rows"]] != splits["validation"]:
        raise ValueError("Reference selection mismatch")

    reproduced, _ = benchmark.score_rows(reference["rows"], records)
    if any(reference.get(key) != value for key, value in reproduced.items()):
        raise ValueError("Reference metrics do not reproduce")

    train = splits["train"]
    fixed = fewshot.select_examples(records, train)[:4]
    index = retrieval.BM25(records, train)

    for row in reference["rows"]:
        _, audit = demonstration_prompt(
            records,
            train,
            row["record_index"],
            fixed,
            index,
        )
        stored = row["response_audit"]["demonstrations"]

        if audit["prompt_sha256"] != stored["prompt_sha256"]:
            raise ValueError("Generated validation prompt differs from frozen v4")
        if stored["prompt_sha256"] != benchmark.sha(stored["system_prompt"].encode()):
            raise ValueError("Stored reference prompt hash mismatch")

    modules = {
        "runner": sys.modules[__name__],
        "fewshot": fewshot,
        "retrieval": retrieval,
        "benchmark": benchmark,
        "backends": sys.modules["maintlog.backends"],
    }
    plan = {
        **identity,
        "evaluation_protocol": "maintie_complete_v4_partitioned_v1",
        "model_configuration": configuration,
        "timeout": args.timeout,
        "v4_reference_sha256": benchmark.sha(args.v4_run.read_bytes()),
        "implementation_sha256": {
            name: benchmark.sha(Path(module.__file__).read_bytes())
            for name, module in modules.items()
        },
        "splits": splits,
        "order": ["validation", "test", "train"],
        "train_policy": (
            "Refit selection and BM25 excluding target and exact source "
            "duplicates; development diagnostic, not cross-validation."
        ),
        "interpretation": (
            "Project-specific five-class extraction only. "
            "No full-agent score and no pooled headline score. "
            "Server metadata does not prove loaded weights or settings."
        ),
    }

    if args.preflight:
        targets = {
            train[0],
            *(item["record_index"] for item in fixed),
        }
        for target in sorted(targets):
            demonstration_prompt(records, train, target, fixed, index)

        print(
            json.dumps(
                {
                    "preflight": "passed",
                    "model_calls": 0,
                    "records": len(records),
                    "split_counts": {key: len(value) for key, value in splits.items()},
                    "validation_prompts_reproduced": len(reference["rows"]),
                },
                indent=2,
            )
        )
        return 0

    if args.resume:
        if read_json(args.run_dir / "plan.json") != plan:
            raise ValueError("Resume configuration or source changed")
    else:
        args.run_dir.mkdir(parents=True, exist_ok=False)
        write_json(args.run_dir / "plan.json", plan)

    for split in plan["order"]:
        rows = []

        for target in splits[split]:
            prompt, demonstrations = demonstration_prompt(
                records, train, target, fixed, index
            )
            path = args.run_dir / f"{split}-{target:04d}.json"

            if path.exists():
                row = read_json(path)
                if (
                    row["record_index"] != target
                    or row["split"] != split
                    or row["demonstrations"] != demonstrations
                ):
                    raise ValueError("Checkpoint identity mismatch")
                benchmark.score_rows([row], records)
            else:
                source = records[target]
                audit = {}
                prediction = None
                predicted = set()
                error = None
                started = time.monotonic()

                try:
                    prediction, predicted, _ = benchmark.request(
                        provider,
                        source,
                        args.timeout,
                        system=prompt,
                        audit=audit,
                    )
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    IndexError,
                    TypeError,
                    subprocess.TimeoutExpired,
                ) as exc:
                    error = f"{type(exc).__name__}: {exc}"

                expected = benchmark.entity_keys(
                    source["entities"],
                    len(source["tokens"]),
                    gold=True,
                )
                row = {
                    "record_index": target,
                    "split": split,
                    "prediction": prediction,
                    "error": error,
                    "response_audit": audit,
                    "demonstrations": demonstrations,
                    "system_prompt": prompt,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "exact_entity_set": (error is None and predicted == expected),
                }
                write_json(path, row)

            rows.append(row)
            print(
                f"{split} {len(rows)}/{len(splits[split])} "
                f"record={target} valid={row['error'] is None}",
                flush=True,
            )

        summary, _ = benchmark.score_rows(rows, records)
        write_json(
            args.run_dir / f"{split}-summary.json",
            {"split": split, **summary},
        )
        print(
            json.dumps({"split": split, **summary}, indent=2),
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
