"""Regression tests for MaintIE token-span scoring."""

import unittest

from maintlog.maintie_benchmark import counts, entity_keys, metrics


class MaintIEBenchmarkTests(unittest.TestCase):
    def test_gold_projection_deduplicates_identical_coarse_spans(self):
        entities = [
            {"start": 0, "end": 2, "type": "PhysicalObject/A"},
            {"start": 0, "end": 2, "type": "PhysicalObject/B"},
        ]
        self.assertEqual(
            entity_keys(entities, 3, gold=True),
            {(0, 2, "PhysicalObject")},
        )

    def test_wrong_boundary_or_type_is_not_an_exact_match(self):
        gold = {(0, 2, "PhysicalObject")}
        for predicted in (
            {(0, 1, "PhysicalObject")},
            {(0, 2, "Activity")},
        ):
            with self.subTest(predicted=predicted):
                self.assertEqual(
                    counts(predicted, gold),
                    {"tp": 0, "fp": 1, "fn": 1},
                )

    def test_invalid_span_and_duplicate_prediction_are_rejected(self):
        for entities in (
            [{"start": True, "end": 2, "type": "State"}],
            [{"start": 2, "end": 2, "type": "State"}],
            [{"start": 0, "end": 4, "type": "State"}],
            [
                {"start": 0, "end": 1, "type": "State"},
                {"start": 0, "end": 1, "type": "State"},
            ],
        ):
            with self.subTest(entities=entities):
                with self.assertRaises(ValueError):
                    entity_keys(entities, 3)

    def test_failed_prediction_preserves_false_negatives(self):
        result = metrics(counts(set(), {(0, 1, "State")}))
        self.assertEqual(result["fn"], 1)
        self.assertEqual(result["recall"], 0)
        self.assertEqual(result["f1"], 0)
        self.assertIsNone(result["precision"])


if __name__ == "__main__":
    unittest.main()
