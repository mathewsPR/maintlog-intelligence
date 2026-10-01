"""The evaluation gate must independently require workflow completion."""

import unittest

from maintlog.comparison import score_case


class ComparisonCompletionTests(unittest.TestCase):
    def report(self, completion):
        return {
            "status": "no_matches",
            "records_for_review": [],
            "extraction_proposals": [],
            "completion": completion,
            "trace": [],
            "elapsed_seconds": 0.0,
            "model_calls": 0,
        }

    def score(self, report):
        return score_case(
            report,
            {
                "relevant_record_ids": [],
                "expected_fields": {},
            },
        )

    def test_matching_output_cannot_pass_an_incomplete_workflow(self):
        metrics = self.score(
            self.report(
                {
                    "requirements_met": False,
                    "missing": ["perform a search"],
                }
            )
        )

        self.assertTrue(metrics["exact_record_set"])
        self.assertFalse(metrics["workflow_complete"])
        self.assertFalse(metrics["labeled_task_success"])

    def test_missing_completion_cannot_pass(self):
        report = self.report({})
        del report["completion"]

        metrics = self.score(report)

        self.assertFalse(metrics["workflow_complete"])
        self.assertFalse(metrics["labeled_task_success"])

    def test_complete_matching_workflow_can_pass(self):
        metrics = self.score(
            self.report(
                {
                    "requirements_met": True,
                    "missing": [],
                }
            )
        )

        self.assertTrue(metrics["workflow_complete"])
        self.assertTrue(metrics["labeled_task_success"])


if __name__ == "__main__":
    unittest.main()
