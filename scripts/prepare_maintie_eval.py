"""Prepare a project-specific MaintIE split without changing source data."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

EXPECTED_SHA256 = "ef811cf4ffd0c90e6a13b1369e24e9d1d08f9a294d873ab4fb1a580096d7d6e0"
TOP_CLASSES = {
    "PhysicalObject",
    "State",
    "Process",
    "Activity",
    "Property",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return " ".join(text.casefold().split())


def prepare(path):
    raw = path.read_bytes()
    source_hash = digest(raw)
    if source_hash != EXPECTED_SHA256:
        raise ValueError("Dataset hash differs from the inspected checkpoint")

    records = json.loads(raw)
    if not isinstance(records, list) or len(records) != 1076:
        raise ValueError("Expected the inspected 1,076-record corpus")

    parents = list(range(len(records)))

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left, right):
        left, right = root(left), root(right)
        if left != right:
            parents[max(left, right)] = min(left, right)

    signatures = {}
    class_counts = Counter()
    max_tokens = 0

    for index, record in enumerate(records):
        text = record.get("text")
        tokens = record.get("tokens")
        entities = record.get("entities")

        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Invalid text at record {index}")
        if (
            not isinstance(tokens, list)
            or not tokens
            or any(not isinstance(token, str) or not token for token in tokens)
        ):
            raise ValueError(f"Invalid tokens at record {index}")
        if not isinstance(entities, list):
            raise ValueError(f"Invalid entities at record {index}")

        max_tokens = max(max_tokens, len(tokens))

        for entity in entities:
            start, end = entity.get("start"), entity.get("end")
            label = entity.get("type")
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(tokens)
                or not isinstance(label, str)
                or label.split("/")[0] not in TOP_CLASSES
            ):
                raise ValueError(f"Invalid entity at record {index}")
            class_counts[label.split("/")[0]] += 1

        keys = (
            ("text", normalized(text)),
            ("tokens", tuple(token.casefold() for token in tokens)),
        )
        for key in keys:
            if key in signatures:
                union(index, signatures[key])
            else:
                signatures[key] = index

    groups = {}
    for index in range(len(records)):
        groups.setdefault(root(index), []).append(index)

    ranked = []
    for indices in groups.values():
        # Ranking depends on source content, never entity labels.
        content = sorted(
            [
                normalized(records[index]["text"]),
                [token.casefold() for token in records[index]["tokens"]],
            ]
            for index in indices
        )
        group_hash = digest(json.dumps(content, ensure_ascii=False).encode("utf-8"))
        rank = digest(("maintie-project-split-v1:" + group_hash).encode())
        ranked.append((rank, group_hash, indices))

    ranked.sort()
    train_end = int(len(ranked) * 0.6)
    validation_end = int(len(ranked) * 0.8)
    splits = {"train": [], "validation": [], "test": []}
    assignments = []

    for position, (_, group_hash, indices) in enumerate(ranked):
        split = (
            "train"
            if position < train_end
            else "validation"
            if position < validation_end
            else "test"
        )
        # Record zero was printed during setup, so its entire duplicate
        # group is explicitly reserved for development.
        if 0 in indices:
            split = "train"

        splits[split].extend(indices)
        assignments.append(
            {
                "group_sha256": group_hash,
                "record_indices": indices,
                "split": split,
            }
        )

    for indices in splits.values():
        indices.sort()

    assigned = [index for indices in splits.values() for index in indices]
    if sorted(assigned) != list(range(len(records))):
        raise ValueError("Split does not partition the corpus exactly")

    return {
        "protocol": "maintie_project_top_level_entities_v1",
        "official_split": False,
        "source_sha256": source_hash,
        "records": len(records),
        "duplicate_groups": len(groups),
        "max_tokens": max_tokens,
        "top_classes": sorted(TOP_CLASSES),
        "entity_counts_before_coarse_deduplication": dict(sorted(class_counts.items())),
        "split_method": (
            "Content-hash-ranked duplicate groups, approximately 60/20/20 "
            "by group count. Record-zero group forced into development."
        ),
        "split_counts": {split: len(indices) for split, indices in splits.items()},
        "splits": splits,
        "groups": assignments,
        "interpretation": (
            "Project-specific split, not a reproduction of published scores. "
            "Duplicate grouping uses source text/tokens only. Near duplicates "
            "and unknown model pretraining exposure are not ruled out. "
            "This evaluates entity extraction, not the full application agent."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/public/maintie/gold_release.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/benchmarks/maintie/split_manifest.json"),
    )
    args = parser.parse_args()

    if args.output.resolve() == args.data.resolve():
        parser.error("Output must not overwrite the dataset")

    manifest = prepare(args.data)
    content = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )

    if args.output.exists() and args.output.read_bytes() != content:
        raise ValueError("Different manifest already exists; review before replacing")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists():
        args.output.write_bytes(content)

    summary = {
        key: manifest[key]
        for key in (
            "protocol",
            "official_split",
            "source_sha256",
            "records",
            "duplicate_groups",
            "max_tokens",
            "split_counts",
        )
    }
    print(json.dumps(summary, indent=2))
    print(f"Saved: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
