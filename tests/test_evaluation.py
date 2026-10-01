"""Scoring, dataset parsing, and provenance regression tests: Python 3.11."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from maintlog.evaluation import (
    NormDocument,
    Unit,
    maintie_audit,
    normalization_audit,
    read_maintie,
    read_norm,
    score_normalization,
    verify_manifest,
    wilson,
)

if sys.version_info[:2] != (3, 11):
    raise RuntimeError("Run project tests with Python 3.11 only")


def score(pairs, predictions=None, casefold=False):
    document = NormDocument(
        tuple(
            Unit(source, target, index + 1)
            for index, (source, target) in enumerate(pairs)
        )
    )
    return score_normalization(
        [document],
        lambda source: (predictions or {}).get(source, source),
        casefold=casefold,
    )


class MetricTests(unittest.TestCase):
    def test_correct_wrong_and_missed_corrections(self):
        result = score(
            [("a", "alpha"), ("b", "beta"), ("c", "c"), ("d", "delta")],
            {"a": "alpha", "b": "bad", "c": "changed"},
        )
        self.assertEqual(
            (result["correction_tp"], result["correction_fp"], result["correction_fn"]),
            (1, 2, 2),
        )
        self.assertEqual(result["correction_precision"], 1 / 3)
        self.assertEqual(result["correction_recall"], 1 / 3)
        self.assertEqual(result["unit_accuracy"], 1 / 4)

    def test_identity_precision_undefined(self):
        result = score([("a", "alpha"), ("b", "b")])
        self.assertIsNone(result["correction_precision"])
        self.assertEqual(result["correction_recall"], 0)
        self.assertEqual(result["error_reduction_vs_identity"], 0)

    def test_correct_input_rewrite_is_collateral_error(self):
        result = score([("a", "a"), ("b", "beta")], {"a": "wrong"})
        self.assertEqual(result["error_reduction_vs_identity"], -1)

    def test_masks_excluded_and_identifier_preservation_separate(self):
        result = score([("ID-001", "<id>"), ("24V", "<num> V"), ("a", "a")])
        self.assertEqual(result["lexical_units"], 1)
        self.assertEqual(result["masked_units_excluded"], 2)
        self.assertEqual(result["identifier_preservation"], 1)

    def test_identifier_rewrite_detected(self):
        result = score([("ID-001", "<id>")], {"ID-001": "ID-002"})
        self.assertEqual(result["identifier_preservation"], 0)
        self.assertIsNone(result["unit_accuracy"])
        self.assertIsNone(result["document_exact_accuracy"])

    def test_casefold_is_a_separate_metric(self):
        pairs = [("ENGINE", "engine")]
        self.assertEqual(score(pairs)["unit_accuracy"], 0)
        self.assertEqual(score(pairs, casefold=True)["unit_accuracy"], 1)

    def test_insertions_and_deletions_remain_scored(self):
        result = score([("", "new"), ("old", "")])
        self.assertEqual(result["required_corrections"], 2)
        self.assertEqual(result["lexical_units"], 2)

    def test_no_corrections_needed_has_null_recall(self):
        result = score([("a", "a")])
        self.assertIsNone(result["correction_recall"])
        self.assertIsNone(result["error_reduction_vs_identity"])
        self.assertEqual(result["document_exact_accuracy"], 1)

    def test_empty_set_has_no_fabricated_scores(self):
        result = score_normalization([], lambda text: text, casefold=False)
        self.assertEqual(result["documents"], 0)
        self.assertIsNone(result["unit_accuracy"])

    def test_wilson_bounds_and_empty(self):
        self.assertIsNone(wilson(0, 0))
        low, high = wilson(5, 10)
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)

    def test_source_signature_does_not_use_gold_labels(self):
        first = NormDocument((Unit("input", "gold1", 1),))
        second = NormDocument((Unit("input", "gold2", 5),))
        self.assertEqual(first.signature(), second.signature())


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "source.txt"

    def test_norm_blank_separators_and_no_final_newline(self):
        self.path.write_text("a\talpha\n\nb\tb", encoding="utf-8")
        self.assertEqual(len(read_norm(self.path)), 2)

    def test_norm_empty_target_and_empty_source(self):
        self.path.write_text("a\t\n\tinserted\n", encoding="utf-8")
        units = read_norm(self.path)[0].units
        self.assertEqual(units[0].target, "")
        self.assertEqual(units[1].source, "")

    def test_norm_malformed_row_rejected(self):
        self.path.write_text("a b\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "tab-separated"):
            read_norm(self.path)

    def test_norm_empty_dataset_rejected(self):
        self.path.write_text("\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no paired"):
            read_norm(self.path)

    def test_overlap_filter_checks_all_companies_and_test_duplicates(self):
        for company in "abc":
            for split in ("train", "val", "test"):
                path = self.root / f"{split}_company_{company}.norm"
                text = f"{split}_{company}\t{split}_{company}\n"
                if company == "a" and split == "train":
                    text += "\nshared\tshared\n"
                if company == "b" and split == "test":
                    text += "\nshared\tshared\n\nunique\tunique\n\nunique\tunique\n"
                path.write_text(text)
        result = normalization_audit(self.root)
        company_b = result["company_results"]["b"]
        self.assertEqual(company_b["test_documents_overlapping_any_train_or_val"], 1)
        self.assertEqual(company_b["test_documents_overlapping_own_train_or_val"], 0)
        self.assertEqual(company_b["test_duplicate_occurrences_beyond_first"], 1)
        self.assertEqual(company_b["clean_test_documents"], 2)
        self.assertEqual(
            result["pooled"]["dictionary_v0"]["clean_casefold"]["documents"], 4
        )

    def ie_record(self):
        return {
            "text": "replace seal",
            "tokens": ["replace", "seal"],
            "entities": [
                {"start": 0, "end": 1, "type": "Activity/Replace"},
                {"start": 1, "end": 2, "type": "PhysicalObject/Seal"},
            ],
            "relations": [{"head": 0, "tail": 1, "type": "hasPatient"}],
        }

    def write_ie(self, records):
        self.path.write_text(json.dumps(records), encoding="utf-8")

    def test_maintie_schema_and_counts(self):
        self.write_ie([self.ie_record(), self.ie_record()])
        result = maintie_audit(self.path)
        self.assertEqual(
            (result["records"], result["entities"], result["relations"]), (2, 4, 2)
        )
        self.assertEqual(result["duplicate_text_occurrences_beyond_first"], 1)
        self.assertIsNone(result["extraction_f1"])

    def test_maintie_out_of_bounds_span_rejected(self):
        record = self.ie_record()
        record["entities"][0]["end"] = 3
        self.write_ie([record])
        with self.assertRaisesRegex(ValueError, "span/type"):
            read_maintie(self.path)

    def test_maintie_boolean_index_rejected(self):
        record = self.ie_record()
        record["entities"][0]["start"] = False
        self.write_ie([record])
        with self.assertRaisesRegex(ValueError, "span/type"):
            read_maintie(self.path)

    def test_maintie_invalid_relation_reference_rejected(self):
        record = self.ie_record()
        record["relations"][0]["tail"] = 2
        self.write_ie([record])
        with self.assertRaisesRegex(ValueError, "relation index"):
            read_maintie(self.path)

    def test_manifest_cannot_omit_evaluated_files(self):
        (self.root / "manifest.json").write_text(
            json.dumps({"files": [{"relative_path": "unknown.txt"}]})
        )
        with self.assertRaisesRegex(ValueError, "every required"):
            verify_manifest(self.root)

    def test_real_snapshot_integrity_and_tamper_detection(self):
        import shutil

        actual = Path(__file__).resolve().parents[1] / "data/public"
        shutil.copytree(actual, self.root / "public")
        root = self.root / "public"
        self.assertEqual(len(verify_manifest(root)["files"]), 12)
        path = root / "maintnorm/test_company_a.norm"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            verify_manifest(root)


if __name__ == "__main__":
    unittest.main()
