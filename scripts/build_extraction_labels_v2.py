"""Build separately versioned development labels; never overwrite v1."""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from maintlog.comparison import load_cases

ROOT = Path(__file__).resolve().parents[1]

SPECS = (
    (
        "data/demo/comparison_cases.json",
        "data/demo/comparison_cases_v2.json",
        "2dbf8dbd3ca2b82d0a34a1dd45db03c914b110fc9178e38c9770bd0f3abb60b7",
    ),
    (
        "data/release/cases.json",
        "data/release/cases_v2.json",
        "5e4b0d1245bc71087599a6967349445896be80926cb4a96f1378c8c62f788981",
    ),
)

CHANGES = (
    {
        "suite": "data/demo/comparison_cases.json",
        "case": "bearing-actions",
        "record_id": "WO-01",
        "field": "component",
        "old": "brg",
        "new": "BRG-204",
        "reason": "Prefer the explicit identifier in the selected work statement.",
    },
    {
        "suite": "data/demo/comparison_cases.json",
        "case": "bearing-actions",
        "record_id": "WO-01",
        "field": "action",
        "old": "Plan to replace BRG-204 next week.",
        "new": "Plan to replace BRG-204 next week",
        "reason": "Exclude sentence-ending punctuation consistently.",
    },
    {
        "suite": "data/demo/comparison_cases.json",
        "case": "bearing-actions",
        "record_id": "WO-02",
        "field": "action",
        "old": "Replaced BRG-204.",
        "new": "Replaced BRG-204",
        "reason": "Exclude sentence-ending punctuation consistently.",
    },
    {
        "suite": "data/release/cases.json",
        "case": "no-action",
        "record_id": "RL-07",
        "field": "component",
        "old": None,
        "new": "Compressor",
        "reason": (
            "The explicit equipment object qualifies under the broader "
            "v2 definition; hierarchy is not inferred from its name."
        ),
    },
)


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha(path):
    return sha_bytes(path.read_bytes())


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "docs/EXTRACTION_CONTRACT_V2.md",
    )
    args = parser.parse_args()

    if not args.contract.is_file():
        parser.error(f"Contract not found: {args.contract}")

    pending = []
    manifest = {
        "annotation_version": 2,
        "contract_sha256": sha(args.contract),
        "provenance": (
            "Explicit contract-driven revisions of exposed synthetic "
            "development labels. Not independent annotation or holdout data."
        ),
        "runtime_changed": False,
        "v1_release_gate_changed": False,
        "suites": [],
    }

    for input_name, output_name, expected_hash in SPECS:
        input_path = ROOT / input_name
        output_path = ROOT / output_name
        input_hash = sha(input_path)

        if input_hash != expected_hash:
            raise ValueError(
                f"Unexpected v1 annotation hash: {input_name}. "
                "No files written; review the changed input."
            )

        # This validates source hashes and resolves existing label spans.
        resolved_payload, _ = load_cases(input_path)
        original = json.loads(input_path.read_text(encoding="utf-8"))
        updated = deepcopy(original)
        changes = []

        resolved_cases = {case["id"]: case for case in resolved_payload["cases"]}
        updated_cases = {case["id"]: case for case in updated["cases"]}

        for change in CHANGES:
            if change["suite"] != input_name:
                continue

            case_id = change["case"]
            record_id = change["record_id"]
            name = change["field"]
            before = resolved_cases[case_id]["expected_fields"][record_id]["fields"][
                name
            ]

            old_quote = None if before is None else before["quote"]
            if old_quote != change["old"]:
                raise ValueError(
                    f"Unexpected old annotation: {case_id}/{record_id}/{name}"
                )

            fields = updated_cases[case_id]["expected_fields"][record_id]["fields"]
            fields[name] = {
                "field": "narrative_raw",
                "quote": change["new"],
            }

            changes.append(
                {
                    "case_id": case_id,
                    "record_id": record_id,
                    "field": name,
                    "before": before,
                    "after": deepcopy(fields[name]),
                    "reason": change["reason"],
                }
            )

        updated["annotation_version"] = 2
        updated["annotation_contract_sha256"] = manifest["contract_sha256"]
        updated["derived_from_cases_sha256"] = input_hash
        updated["label_provenance"] = manifest["provenance"]

        pending.append((output_path, encode(updated)))
        manifest["suites"].append(
            {
                "input": input_name,
                "input_sha256": input_hash,
                "output": output_name,
                "output_sha256": sha_bytes(pending[-1][1]),
                "source_identity": original["source"],
                "changes": changes,
            }
        )

    manifest_path = ROOT / "data/extraction_labels_v2_manifest.json"
    pending.append((manifest_path, encode(manifest)))

    # Check every destination before writing any file.
    for path, content in pending:
        if path.exists() and path.read_bytes() != content:
            raise ValueError(
                f"Different output already exists: {path}. "
                "No files written; review it before replacing it."
            )

    for path, content in pending:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)

    # Independently validate both generated annotation files.
    for _, output_name, _ in SPECS:
        load_cases(ROOT / output_name)

    # Verify original annotation files remain untouched.
    for input_name, _, expected_hash in SPECS:
        if sha(ROOT / input_name) != expected_hash:
            raise ValueError(f"V1 input changed: {input_name}")

    print("Created and validated v2 labels; v1 files remain unchanged.")
    for path, _ in pending:
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
