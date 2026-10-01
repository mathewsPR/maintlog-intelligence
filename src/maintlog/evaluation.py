"""Offline dataset audit and normalization evaluation; Python 3.11 only.

Application normalization excludes whole source units whose target contains a
privacy mask. This is an adapted task, not MaintNorm's official combined task.
"""

import argparse
import hashlib
import json
import math
import platform
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .normalization import ABBREVIATIONS, normalize

MASK = re.compile(r"<(id|num|date|sensitive)>")
TOP_CLASSES = {"PhysicalObject", "State", "Activity", "Process", "Property"}


@dataclass(frozen=True)
class Unit:
    source: str
    target: str
    line: int


@dataclass(frozen=True)
class NormDocument:
    units: tuple[Unit, ...]

    def signature(self) -> str:
        # Exact source content only: labels are never used to detect split overlap.
        blob = json.dumps([u.source for u in self.units], ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def read_norm(path: Path) -> list[NormDocument]:
    documents: list[NormDocument] = []
    current: list[Unit] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not line.strip() and "\t" not in line:
            if current:
                documents.append(NormDocument(tuple(current)))
                current = []
            continue
        fields = line.split("\t")
        if len(fields) != 2:
            raise ValueError(
                f"{path.name}:{line_number}: expected two tab-separated fields"
            )
        current.append(Unit(fields[0], fields[1], line_number))
    if current:
        documents.append(NormDocument(tuple(current)))
    if not documents:
        raise ValueError(f"{path.name}: no paired documents")
    return documents


def divide(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    fraction = successes / total
    denominator = 1 + z * z / total
    center = (fraction + z * z / (2 * total)) / denominator
    radius = (
        z
        * math.sqrt(fraction * (1 - fraction) / total + z * z / (4 * total * total))
        / denominator
    )
    return [max(0.0, center - radius), min(1.0, center + radius)]


def score_normalization(
    documents: list[NormDocument], predictor: Callable[[str], str], *, casefold: bool
) -> dict:
    lexical = correct = required = tp = fp = fn = changed = 0
    exact_docs = eligible_docs = 0
    masks = Counter()
    protected = protected_preserved = identifiers = identifiers_preserved = 0
    failures: Counter[tuple[str, str, str]] = Counter()
    compare = str.casefold if casefold else (lambda text: text)
    for document in documents:
        document_correct = True
        document_lexical = 0
        for unit in document.units:
            prediction = predictor(unit.source)
            tags = MASK.findall(unit.target)
            if tags:
                masks.update(tags)
                protected += 1
                protected_preserved += prediction == unit.source
                if "id" in tags:
                    identifiers += 1
                    identifiers_preserved += prediction == unit.source
                continue
            source, target, predicted = map(
                compare, (unit.source, unit.target, prediction)
            )
            needs_change = target != source
            made_change = predicted != source
            is_correct = predicted == target
            lexical += 1
            document_lexical += 1
            correct += is_correct
            required += needs_change
            changed += made_change
            tp += needs_change and made_change and is_correct
            fp += made_change and not is_correct
            fn += needs_change and not is_correct
            document_correct = document_correct and is_correct
            if not is_correct:
                failures[(unit.source, unit.target, prediction)] += 1
        if document_lexical:
            eligible_docs += 1
            exact_docs += document_correct
    return {
        "casefold": casefold,
        "documents": len(documents),
        "eligible_documents": eligible_docs,
        "lexical_units": lexical,
        "correct_units": correct,
        "unit_accuracy": divide(correct, lexical),
        "required_corrections": required,
        "predicted_corrections": changed,
        "correction_tp": tp,
        "correction_fp": fp,
        "correction_fn": fn,
        "correction_precision": divide(tp, tp + fp),
        "correction_recall": divide(tp, tp + fn),
        "correction_f1": divide(2 * tp, 2 * tp + fp + fn),
        "error_reduction_vs_identity": divide(required - (lexical - correct), required),
        "exact_documents": exact_docs,
        "document_exact_accuracy": divide(exact_docs, eligible_docs),
        "document_exact_wilson95": wilson(exact_docs, eligible_docs),
        "masked_units_excluded": protected,
        "mask_tag_counts": dict(sorted(masks.items())),
        "masked_source_units_preserved": protected_preserved,
        "masked_source_preservation": divide(protected_preserved, protected),
        "identifier_units": identifiers,
        "identifier_units_preserved": identifiers_preserved,
        "identifier_preservation": divide(identifiers_preserved, identifiers),
        "most_frequent_errors": [
            {
                "source": source,
                "target": target,
                "prediction": predicted,
                "count": count,
            }
            for (source, target, predicted), count in sorted(
                failures.items(), key=lambda item: (-item[1], item[0])
            )[:10]
        ],
    }


def normalization_audit(root: Path) -> dict:
    companies = {}
    pooled_test: list[NormDocument] = []
    pooled_clean: list[NormDocument] = []
    all_train_val_signatures = set()
    loaded = {}
    for company in "abc":
        loaded[company] = {
            split: read_norm(root / f"{split}_company_{company}.norm")
            for split in ("train", "val", "test")
        }
        all_train_val_signatures.update(
            doc.signature()
            for split in ("train", "val")
            for doc in loaded[company][split]
        )
    global_seen_test = set()
    for company in "abc":
        splits = loaded[company]
        test = splits["test"]
        prior = {d.signature() for split in ("train", "val") for d in splits[split]}
        repeated = sum(
            count - 1 for count in Counter(d.signature() for d in test).values()
        )
        clean = []
        for document in test:
            key = document.signature()
            if key not in all_train_val_signatures and key not in global_seen_test:
                clean.append(document)
                global_seen_test.add(key)
        scores = {}
        for name, predictor in (
            ("identity", lambda text: text),
            ("dictionary_v0", normalize),
        ):
            scores[name] = {
                "strict": score_normalization(test, predictor, casefold=False),
                "casefold": score_normalization(test, predictor, casefold=True),
                "clean_casefold": score_normalization(clean, predictor, casefold=True),
            }
        companies[company] = {
            "split_document_counts": {
                split: len(docs) for split, docs in splits.items()
            },
            "test_documents_overlapping_own_train_or_val": sum(
                d.signature() in prior for d in test
            ),
            "test_documents_overlapping_any_train_or_val": sum(
                d.signature() in all_train_val_signatures for d in test
            ),
            "test_duplicate_occurrences_beyond_first": repeated,
            "clean_test_documents": len(clean),
            "scores": scores,
        }
        pooled_test.extend(test)
        pooled_clean.extend(clean)
    return {
        "status": "measured",
        "task": "lexical-unit normalization with mask-containing targets excluded",
        "dictionary": ABBREVIATIONS,
        "company_results": companies,
        "pooled": {
            name: {
                "strict": score_normalization(pooled_test, predictor, casefold=False),
                "casefold": score_normalization(pooled_test, predictor, casefold=True),
                "clean_casefold": score_normalization(
                    pooled_clean, predictor, casefold=True
                ),
            }
            for name, predictor in (
                ("identity", lambda text: text),
                ("dictionary_v0", normalize),
            )
        },
        "clean_subset_policy": (
            "Exclude exact source documents present in any company train/val split; "
            "deduplicate remaining test source documents across companies in A/B/C order. "
            "Labels are not used for filtering. Near duplicates are not removed."
        ),
        "limits": [
            "Not the official combined normalization/masking benchmark.",
            "Compound targets containing masks are excluded as whole units; some lexical corrections are omitted.",
            "Per-unit predictions do not evaluate sentence-context disambiguation.",
            "Casefold metrics suppress case errors; strict metrics retain them.",
            "Wilson intervals are descriptive; correlated maintenance records weaken independence assumptions.",
            "No training or dictionary tuning was performed on these downloaded splits.",
        ],
    }


def read_maintie(path: Path) -> list[dict]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError("MaintIE must be a nonempty JSON array")
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("text"), str):
            raise ValueError(f"MaintIE record {index}: missing text")
        tokens = record.get("tokens")
        if not isinstance(tokens, list) or not all(isinstance(t, str) for t in tokens):
            raise ValueError(f"MaintIE record {index}: invalid tokens")
        entities, relations = record.get("entities"), record.get("relations")
        if not isinstance(entities, list) or not isinstance(relations, list):
            raise ValueError(f"MaintIE record {index}: missing entities/relations")
        for entity in entities:
            if not isinstance(entity, dict):
                raise ValueError(f"MaintIE record {index}: invalid entity")
            start, end = entity.get("start"), entity.get("end")
            label = entity.get("type")
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(tokens)
                or not isinstance(label, str)
                or label.split("/")[0] not in TOP_CLASSES
            ):
                raise ValueError(f"MaintIE record {index}: invalid entity span/type")
        for relation in relations:
            if not isinstance(relation, dict):
                raise ValueError(f"MaintIE record {index}: invalid relation")
            head, tail = relation.get("head"), relation.get("tail")
            if (
                type(head) is not int
                or type(tail) is not int
                or not 0 <= head < len(entities)
                or not 0 <= tail < len(entities)
                or not isinstance(relation.get("type"), str)
            ):
                raise ValueError(f"MaintIE record {index}: invalid relation index/type")
    return records


def maintie_audit(path: Path) -> dict:
    records = read_maintie(path)
    entity_counts = Counter()
    relation_counts = Counter()
    for record in records:
        entity_counts.update(
            entity["type"].split("/")[0] for entity in record["entities"]
        )
        relation_counts.update(relation["type"] for relation in record["relations"])
    unique_texts = len({record["text"] for record in records})
    return {
        "status": "schema_audited_extraction_not_evaluated",
        "records": len(records),
        "tokens": sum(len(record["tokens"]) for record in records),
        "entities": sum(entity_counts.values()),
        "relations": sum(relation_counts.values()),
        "top_level_entity_counts": dict(sorted(entity_counts.items())),
        "relation_counts": dict(sorted(relation_counts.items())),
        "unique_texts": unique_texts,
        "duplicate_text_occurrences_beyond_first": len(records) - unique_texts,
        "invalid_spans_or_relation_indices": 0,
        "extraction_precision": None,
        "extraction_recall": None,
        "extraction_f1": None,
        "interpretation": (
            "Only the real source file's schema, spans, relation references, and label "
            "distribution were checked. M0 has no narrative extractor, so extraction "
            "metrics are unavailable rather than zero. PhysicalObject/State/Activity "
            "require a reviewed mapping to component/problem/action; raw-text "
            "normalization is not measured on this normalized corpus."
        ),
    }


def verify_manifest(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest.get("files"), list) or not manifest["files"]:
        raise ValueError("Missing dataset file manifest")
    expected = {
        f"maintnorm/{split}_company_{company}.norm"
        for split in ("train", "val", "test")
        for company in "abc"
    } | {"maintnorm/LICENSE.md", "maintie/LICENSE.md", "maintie/gold_release.json"}
    declared = [entry["relative_path"] for entry in manifest["files"]]
    if len(declared) != len(set(declared)) or set(declared) != expected:
        raise ValueError(
            "Manifest must declare every required snapshot file exactly once"
        )
    for entry in manifest["files"]:
        path = root / entry["relative_path"]
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Dataset manifest path escapes its root")
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != entry["sha256"]:
            raise ValueError(f"Snapshot hash mismatch: {entry['relative_path']}")
        if len(blob) != entry["size_bytes"]:
            raise ValueError(f"Snapshot size mismatch: {entry['relative_path']}")
    return manifest


def percentage(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def render_report(result: dict) -> str:
    norm = result["maintnorm"]
    ie = result["maintie"]
    measured = norm["pooled"]["dictionary_v0"]["casefold"]
    lines = [
        "# Maintenance-log intelligence: public dataset evaluation",
        "",
        f"Run UTC: {result['run_utc']}. Runtime: Python {result['python_version']}.",
        "",
        "## Assessment",
        "",
        "This run evaluates the frozen six-entry dictionary baseline, not an agent. "
        "It compares against returning input unchanged. Dataset scores establish "
        "normalization behavior only; they do not validate a full maintenance application.",
        "",
        f"The dictionary corrects only {measured['correction_tp']} of "
        f"{measured['required_corrections']} required lexical changes "
        f"({percentage(measured['correction_recall'])} correction recall), with "
        f"{percentage(measured['correction_precision'])} correction precision. "
        "It preserves the labeled identifier source units, but its coverage and "
        "word-form choices are inadequate for general maintenance-text normalization. "
        "A working CSV/search demo is not evidence of useful text understanding.",
        "",
        "## MaintNorm: measured normalization results",
        "",
        "Primary table uses casefold comparison to separate lexical corrections from "
        "capitalization. Any target unit containing <id>, <num>, <date>, or <sensitive> "
        "is excluded from lexical scoring. Empty targets/insertions remain eligible. "
        "Strict case-sensitive scores and all denominators are in results.json.",
        "",
        "| Scope | Test documents | Lexical units | Unchanged accuracy | Dictionary accuracy | Correction precision | Correction recall | Error reduction |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    rows = [
        (f"Company {company.upper()}", entry["scores"])
        for company, entry in norm["company_results"].items()
    ]
    rows.append(("All nominal test splits", norm["pooled"]))
    for label, scores in rows:
        baseline, model = (
            scores["identity"]["casefold"],
            scores["dictionary_v0"]["casefold"],
        )
        lines.append(
            f"| {label} | {model['documents']} | {model['lexical_units']} | "
            f"{percentage(baseline['unit_accuracy'])} | {percentage(model['unit_accuracy'])} | "
            f"{percentage(model['correction_precision'])} | {percentage(model['correction_recall'])} | "
            f"{percentage(model['error_reduction_vs_identity'])} |"
        )
    pooled = norm["pooled"]["dictionary_v0"]["casefold"]
    strict = norm["pooled"]["dictionary_v0"]["strict"]
    clean = norm["pooled"]["dictionary_v0"]["clean_casefold"]
    lines.extend(
        [
            "",
            f"Nominal correction counts: TP={pooled['correction_tp']}, FP={pooled['correction_fp']}, FN={pooled['correction_fn']}. "
            f"Required corrections={pooled['required_corrections']}; predicted corrections={pooled['predicted_corrections']}.",
            "",
            f"Strict dictionary lexical-unit accuracy: {percentage(strict['unit_accuracy'])}. "
            f"Strict document exact accuracy: {percentage(strict['document_exact_accuracy'])}. "
            f"Casefold document exact accuracy: {percentage(pooled['document_exact_accuracy'])}.",
            "",
            f"Masked units excluded: {pooled['masked_units_excluded']}. Identifier units checked: "
            f"{pooled['identifier_units']}; unchanged identifier units: {pooled['identifier_units_preserved']} "
            f"({percentage(pooled['identifier_preservation'])}). This checks obfuscated source-unit "
            "preservation by the dictionary, not confidentiality or real asset-history linkage.",
            "",
            "## Split overlap and interpretation",
            "",
            "| Company | Train | Validation | Test | Test rows also in any train/validation | Within-test duplicate occurrences | Globally clean test documents |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for company, entry in norm["company_results"].items():
        counts = entry["split_document_counts"]
        lines.append(
            f"| {company.upper()} | {counts['train']} | {counts['val']} | {counts['test']} | "
            f"{entry['test_documents_overlapping_any_train_or_val']} | "
            f"{entry['test_duplicate_occurrences_beyond_first']} | {entry['clean_test_documents']} |"
        )
    lines.extend(
        [
            "",
            norm["clean_subset_policy"],
            "",
            f"On the clean subset ({clean['documents']} documents; {clean['lexical_units']} lexical units), "
            f"dictionary accuracy={percentage(clean['unit_accuracy'])}, correction precision="
            f"{percentage(clean['correction_precision'])}, correction recall={percentage(clean['correction_recall'])}. "
            "This is a supplementary project-specific subset, not a replacement official split.",
            "",
            "The dictionary was authored before these files were downloaded and was not "
            "tuned during this run. Changes informed by these test errors must be evaluated "
            "on a fresh held-out set. Exact-duplicate filtering does not remove near duplicates. "
            "Mining-equipment text is a domain-transfer test for the pump demo.",
            "",
            "## Frequent dictionary failures",
            "",
            "| Source unit | Reference | Prediction | Count |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for example in pooled["most_frequent_errors"]:
        values = [
            str(example[key]).replace("|", "\\|").replace("\n", " ")
            for key in ("source", "target", "prediction", "count")
        ]
        lines.append("| " + " | ".join(values) + " |")
    lines.extend(
        [
            "",
            "A six-entry dictionary has deliberately limited coverage. Wrong expansions "
            "and tense/word-form mismatches are real errors under this task. High accuracy "
            "on unchanged units can hide poor correction recall; inspect both. Model-based "
            "normalization should be compared with this baseline under identical scoring.",
            "",
            "## MaintIE: measured schema audit, extraction not evaluated",
            "",
            f"Actual downloaded gold file: {ie['records']} records; {ie['tokens']} tokens; "
            f"{ie['entities']} entities; {ie['relations']} relations. "
            f"All spans and relation indices passed schema validation. "
            f"Duplicate text occurrences beyond the first: {ie['duplicate_text_occurrences_beyond_first']}.",
            "",
            "| Top-level entity class | Annotated entities |",
            "| --- | ---: |",
        ]
    )
    lines.extend(
        f"| {label} | {count} |"
        for label, count in ie["top_level_entity_counts"].items()
    )
    lines.extend(
        [
            "",
            "Extraction precision, recall, and F1 are unavailable: this evaluation runs no "
            "model or extraction predictions. The separate agent prototype can propose source spans; "
            "that capability has not been scored on this corpus. The gold corpus "
            "can support selected entity/relation tests after a reviewed mapping; its already "
            "normalized/sanitized text does not test raw-text normalization or real chronology. "
            "Published README counts differ in different sections; this report uses the "
            "measured downloaded file count. A split must group duplicate texts and check "
            "cross-corpus overlap before prompts or models are tuned.",
            "",
            "## Capability coverage and release decision",
            "",
            "| Capability | Evidence in this run | Status |",
            "| --- | --- | --- |",
            "| Dictionary normalization | MaintNorm reference targets and unchanged-input baseline | Measured |",
            "| Identifier preservation | MaintNorm source units labeled with identifier masks | Measured for dictionary only |",
            "| Narrative field extraction | MaintIE schema and annotations audited | Prototype separate; no model score |",
            "| Historical retrieval relevance | No query relevance labels loaded | Not measured |",
            "| Real recurring issues | No verified asset/event histories loaded | Not measured |",
            "| LangGraph agent behavior | Separate replay/behavioral tests; no model calls in this run | Live model quality not measured |",
            "| MaintNet transfer evaluation | No snapshot/access/license audit completed | Not run |",
            "",
            "This is an evaluated software baseline, not a production-ready agent. Close "
            "the real-data/application gate with a representative authorized sample. Evaluate "
            "the bounded agent and compare it with a fixed model workflow and the deterministic "
            "baseline. Evaluate source-span support, abstention, malformed outputs, retrieval "
            "relevance, citation/count validity, latency, cost, and tool budgets. Do not use "
            "invented asset identities/dates to claim public-data recurrence performance.",
            "",
            "## Reproduction and provenance",
            "",
            "```bash",
            "export PYTHONPATH=src",
            "python -m unittest discover -s tests -v",
            "python -m maintlog.evaluation --data-root data/public --output-dir reports",
            "```",
            "",
            "Use Python 3.11 only. Bundled source snapshots are checked against manifest.json "
            "before scoring. results.json contains all denominators, task definitions, hashes, "
            "versions, limits, and descriptive document-accuracy intervals. No model/API calls "
            "or training occurred; there is no model cost or agent latency measurement.",
            "",
            "Sources and MIT notices:",
            "",
            "- MaintNorm: https://github.com/nlp-tlp/maintnorm",
            "- Dataset mirror: https://huggingface.co/datasets/nlp-tlp/MaintNorm",
            "- MaintIE: https://github.com/nlp-tlp/maintie",
            "- Dataset-local LICENSE.md files are included with the source snapshots.",
            "",
        ]
    )
    return "\n".join(lines)


def run(root: Path) -> dict:
    started = time.perf_counter()
    manifest = verify_manifest(root)
    result = {
        "run_utc": datetime.now(UTC).isoformat(),
        "python_version": platform.python_version(),
        "system": platform.platform(),
        "implementation": "dictionary_v0, no model or agent",
        "implementation_sha256": {
            name: hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in ("normalization.py", "evaluation.py")
        },
        "dataset_manifest": manifest,
        "maintnorm": normalization_audit(root / "maintnorm"),
        "maintie": maintie_audit(root / "maintie/gold_release.json"),
    }
    result["elapsed_seconds"] = time.perf_counter() - started
    return result


def main(argv: list[str] | None = None) -> int:
    if sys.version_info[:2] != (3, 11):
        print("Dataset evaluation requires Python 3.11 only.", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data/public"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    args = parser.parse_args(argv)
    try:
        if args.output_dir.resolve().is_relative_to(args.data_root.resolve()):
            raise ValueError("Reports must not be written inside the dataset snapshots")
        result = run(args.data_root)
        report = render_report(result)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "results.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (args.output_dir / "DATASET_EVALUATION_REPORT.md").write_text(
            report, encoding="utf-8"
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2
    print(f"Dataset evaluation complete: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
