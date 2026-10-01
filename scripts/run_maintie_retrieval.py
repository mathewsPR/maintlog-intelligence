"""Training-only BM25 demonstrations and a model-free phrase baseline."""

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from run_maintie_fewshot import build_prompt, select_examples

from maintlog import maintie_benchmark as benchmark

VERSION = "bm25-demonstrations-v4"
FIXED_COUNT = 4
RETRIEVED_COUNT = 4
MIN_SUPPORT = 2
MIN_CONFIDENCE = 0.9


def retrieval_terms(tokens):
    """Use source tokens only; remove placeholders and punctuation."""
    return [
        token.casefold()
        for token in tokens
        if not re.fullmatch(r"<[^>]+>", token)
        and any(character.isalnum() for character in token)
    ]


class BM25:
    """Small deterministic BM25 index fitted only on training texts."""

    def __init__(self, records, indices):
        self.indices = sorted(indices)
        self.documents = {}
        self.document_frequency = Counter()
        lengths = []

        for index in self.indices:
            terms = retrieval_terms(records[index]["tokens"])
            self.documents[index] = Counter(terms)
            self.document_frequency.update(set(terms))
            lengths.append(len(terms))

        self.lengths = dict(zip(self.indices, lengths))
        self.average_length = sum(lengths) / len(lengths) if lengths else 1
        self.average_length = self.average_length or 1

    def retrieve(self, tokens, excluded, count):
        query = set(retrieval_terms(tokens))
        ranked = []
        size = len(self.indices)
        k1 = 1.5
        b = 0.75

        for index in self.indices:
            if index in excluded:
                continue

            score = 0.0
            document = self.documents[index]
            length = self.lengths[index]

            for term in sorted(query):
                frequency = document.get(term, 0)
                if not frequency:
                    continue

                df = self.document_frequency[term]
                idf = math.log(1 + (size - df + 0.5) / (df + 0.5))
                denominator = frequency + k1 * (
                    1 - b + b * length / self.average_length
                )
                score += idf * frequency * (k1 + 1) / denominator

            ranked.append((index, score))

        ranked.sort(key=lambda item: (-item[1], item[0]))
        if len(ranked) < count:
            raise ValueError("Insufficient training examples")

        # Zero-score fallback remains visible in the recorded scores.
        return ranked[:count]


def training_item(records, index):
    source = records[index]
    return {
        "record_index": index,
        "keys": benchmark.entity_keys(
            source["entities"], len(source["tokens"]), gold=True
        ),
    }


def fit_phrase_dictionary(records, train_indices):
    """Learn phrase/class counts exclusively from annotated training spans."""
    phrase_counts = defaultdict(Counter)

    for index in train_indices:
        source = records[index]
        tokens = source["tokens"]
        keys = benchmark.entity_keys(source["entities"], len(tokens), gold=True)

        for start, end, label in sorted(keys):
            phrase = tuple(token.casefold() for token in tokens[start:end])
            phrase_counts[phrase][label] += 1

    accepted = {}
    for phrase, labels in sorted(phrase_counts.items()):
        label, support = sorted(labels.items(), key=lambda item: (-item[1], item[0]))[0]
        confidence = support / sum(labels.values())

        if support >= MIN_SUPPORT and confidence >= MIN_CONFIDENCE:
            accepted[phrase] = label

    return accepted


def phrase_prediction(tokens, dictionary):
    folded = [token.casefold() for token in tokens]
    lengths = sorted({len(phrase) for phrase in dictionary})
    entities = []

    for start in range(len(tokens)):
        for length in lengths:
            end = start + length
            if end > len(tokens):
                break

            label = dictionary.get(tuple(folded[start:end]))
            if label is not None:
                entities.append({"start": start, "end": end, "type": label})

    # Preserve nested matches; do not apply a longest-match filter.
    return {"entities": entities}


def compare_reference(reference, summary, current_exact):
    old_f1 = reference["micro"]["f1"]
    new_f1 = summary["micro"]["f1"]
    previous = {
        row["record_index"]: row["exact_entity_set"] for row in reference["rows"]
    }

    changes = [
        {
            "record_index": index,
            "reference_exact": previous[index],
            "current_exact": current_exact[index],
        }
        for index in previous
        if previous[index] != current_exact[index]
    ]

    return {
        "reference_f1": old_f1,
        "current_f1": new_f1,
        "micro_f1_change": (
            new_f1 - old_f1 if old_f1 is not None and new_f1 is not None else None
        ),
        "improved_exact_records": sum(item["current_exact"] for item in changes),
        "regressed_exact_records": sum(item["reference_exact"] for item in changes),
        "changed_exact_outcomes": changes,
    }


def write_new(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


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
    parser.add_argument("--reference-run", type=Path, required=True)
    parser.add_argument("--phrase-output", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--phrase-only", action="store_true")
    args = parser.parse_args()

    if sys.version_info[:2] != (3, 11):
        parser.error("Python 3.11 required")
    if not 0 < args.timeout <= 120:
        parser.error("timeout must be >0 and <=120")
    if not args.phrase_only and args.output is None:
        parser.error("--output required unless --phrase-only")

    outputs = [args.phrase_output]
    if not args.phrase_only:
        outputs.append(args.output)
    if len({path.resolve() for path in outputs}) != len(outputs):
        parser.error("Output paths must be different")
    if any(path.exists() for path in outputs):
        parser.error("An output already exists; choose new filenames")

    raw = args.data.read_bytes()
    records = json.loads(raw)
    manifest_raw = args.manifest.read_bytes()
    manifest = json.loads(manifest_raw)

    if benchmark.sha(raw) != manifest["source_sha256"]:
        raise ValueError("Dataset does not match manifest")
    if benchmark.sha(benchmark.SYSTEM.encode("utf-8")) != (
        benchmark.BASELINE_PROMPT_SHA256
    ):
        raise ValueError("Baseline instruction prompt changed")

    splits = benchmark.validate_manifest(records, manifest)
    selected = splits["validation"]
    train = set(splits["train"])

    identity = {
        "protocol": manifest["protocol"],
        "split": "validation",
        "official_split": False,
        "dataset_sha256": benchmark.sha(raw),
        "manifest_sha256": benchmark.sha(manifest_raw),
    }

    reference_raw = args.reference_run.read_bytes()
    reference = json.loads(reference_raw)
    for name, value in identity.items():
        if reference.get(name) != value:
            raise ValueError(f"V3 reference mismatch: {name}")

    if reference.get("prompt_version") != "train-examples-v3":
        raise ValueError("Expected the frozen train-examples-v3 reference")
    if [row["record_index"] for row in reference["rows"]] != selected:
        raise ValueError("V3 reference record selection differs")

    reproduced, _ = benchmark.score_rows(reference["rows"], records)
    for name, value in reproduced.items():
        if reference.get(name) != value:
            raise ValueError(f"V3 metric does not reproduce: {name}")

    provenance = {
        "wrapper_sha256": benchmark.sha(Path(__file__).read_bytes()),
        "reference_run_sha256": benchmark.sha(reference_raw),
        "reference_run": str(args.reference_run),
        "training_records": len(train),
        "uses_evaluation_labels_for_selection": False,
    }

    # First evaluate a model-free baseline.
    dictionary = fit_phrase_dictionary(records, splits["train"])
    phrase_rows = []
    for index in selected:
        source = records[index]
        prediction = phrase_prediction(source["tokens"], dictionary)
        predicted = benchmark.entity_keys(prediction["entities"], len(source["tokens"]))
        expected = benchmark.entity_keys(
            source["entities"], len(source["tokens"]), gold=True
        )
        phrase_rows.append(
            {
                "record_index": index,
                "prediction": prediction,
                "error": None,
                "exact_entity_set": predicted == expected,
            }
        )

    phrase_summary, phrase_exact = benchmark.score_rows(phrase_rows, records)
    phrase_report = {
        **identity,
        **provenance,
        "method": "training_phrase_dictionary_v1",
        "model_calls_attempted": 0,
        "minimum_support": MIN_SUPPORT,
        "minimum_label_fraction": MIN_CONFIDENCE,
        "dictionary_entries": len(dictionary),
        **phrase_summary,
        "comparison_to_v3": compare_reference(reference, phrase_summary, phrase_exact),
        "rows": phrase_rows,
        "interpretation": (
            "Training-only phrase matching, with casefolded matching and "
            "original token offsets. Nested matches are retained. Label "
            "fractions measure annotated training occurrences, not semantic "
            "confidence. Unannotated phrase occurrences are not counted "
            "as negative training examples."
        ),
    }
    write_new(args.phrase_output, phrase_report)
    print("PHRASE BASELINE")
    print(json.dumps(phrase_summary, indent=2), flush=True)

    if args.phrase_only:
        return 0

    # Validate both reference configurations before live model calls.
    provider = benchmark.LocalServer(base_url=args.base_url, model=args.model)
    configuration = {
        "model": provider.model,
        "base_url": provider.base_url,
        "max_tokens": provider.max_tokens,
        "temperature": 0,
    }
    if reference["model_configuration"] != configuration:
        raise ValueError("Model configuration differs from V3")
    benchmark.load_baseline(
        args.baseline_run, records, selected, identity, configuration
    )

    fixed = select_examples(records, splits["train"])[:FIXED_COUNT]
    fixed_ids = {item["record_index"] for item in fixed}
    index = BM25(records, splits["train"])
    original_request = benchmark.request

    def retrieved_request(
        provider, row, timeout, *, system=benchmark.SYSTEM, audit=None
    ):
        del system
        if audit is None:
            audit = {}

        retrieved = index.retrieve(row["tokens"], fixed_ids, RETRIEVED_COUNT)
        ids = [item["record_index"] for item in fixed]
        ids.extend(record_id for record_id, _ in retrieved)

        if len(ids) != 8 or len(set(ids)) != 8:
            raise ValueError("Expected eight unique demonstrations")
        if not set(ids) <= train:
            raise ValueError("Demonstration escaped the training partition")

        examples = fixed + [
            training_item(records, record_id) for record_id, _ in retrieved
        ]
        prompt, _ = build_prompt(records, examples)

        audit["demonstrations"] = {
            "fixed_record_indices": sorted(fixed_ids),
            "retrieved": [
                {"record_index": record_id, "bm25_score": score}
                for record_id, score in retrieved
            ],
            "prompt_sha256": benchmark.sha(prompt.encode("utf-8")),
            "system_prompt": prompt,
        }
        return original_request(provider, row, timeout, system=prompt, audit=audit)

    benchmark.PROMPTS[VERSION] = benchmark.SYSTEM
    benchmark.request = retrieved_request
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
        str(len(selected)),
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
        benchmark.request = original_request
        sys.argv = original_argv

    report = json.loads(args.output.read_text(encoding="utf-8"))
    summary, exact = benchmark.score_rows(report["rows"], records)
    report["demonstration_retrieval"] = {
        **provenance,
        "method": "bm25",
        "k1": 1.5,
        "b": 0.75,
        "fixed_count": FIXED_COUNT,
        "retrieved_count": RETRIEVED_COUNT,
        "fixed_record_indices": sorted(fixed_ids),
        "prompt_scope": "Per-record prompts stored in response_audit",
    }
    report["instruction_prompt_sha256"] = report["prompt_sha256"]
    report["prompt_sha256"] = None
    report["comparison_to_v3"] = compare_reference(reference, summary, exact)
    report["interpretation"] += (
        " Input-specific demonstrations are retrieved from training only. "
        "Prompt SHA256 is per record; there is no single complete run prompt."
    )

    temporary = args.output.with_name(args.output.name + ".metadata.tmp")
    write_new(temporary, report)
    temporary.replace(args.output)

    print("COMPARISON TO V3")
    print(
        json.dumps(
            {
                name: report["comparison_to_v3"][name]
                for name in (
                    "reference_f1",
                    "current_f1",
                    "micro_f1_change",
                    "improved_exact_records",
                    "regressed_exact_records",
                )
            },
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
