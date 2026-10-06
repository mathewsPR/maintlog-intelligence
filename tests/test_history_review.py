"""History output must preserve sources and never claim its own accuracy."""

import unittest
from datetime import date

from maintlog.agent import run_agent
from maintlog.backends import Replay
from maintlog.domain import Evidence, Record
from maintlog.history_review import build_history_review


def source(record_id="R1", event_date=date(2024, 1, 1)):
    return Record(
        record_id,
        event_date,
        "A1",
        "",
        "",
        "",
        "",
        "",
        Evidence(
            "records.csv",
            "a" * 64,
            2,
            "synthetic",
            {"narrative": "Notes"},
        ),
        "Connector loose. RESECURED CONNECTOR. Test passed.",
    )


def proposal(record_id="R1"):
    return {
        "record_id": record_id,
        "fields": {
            "component": {
                "field": "narrative_raw",
                "quote": "CONNECTOR",
            },
            "problem": {
                "field": "narrative_raw",
                "quote": "Connector loose",
            },
            "action": {
                "field": "narrative_raw",
                "quote": "RESECURED CONNECTOR",
            },
        },
        "action_status_proposal": "completed",
    }


class HistoryReviewTests(unittest.TestCase):
    def test_date_order_and_source_citations(self):
        first = source("R1", date(2024, 2, 14))
        second = source("R2", date(2024, 4, 17))

        review = build_history_review(
            [second, first],
            [proposal("R2"), proposal("R1")],
        )

        self.assertEqual(
            [entry["record_id"] for entry in review["entries"]],
            ["R1", "R2"],
        )

        entry = review["entries"][0]
        self.assertEqual(entry["citation"]["source_sha256"], "a" * 64)

        span = entry["fields"]["action"]
        self.assertEqual(
            first.narrative_raw[span["start"] : span["end"]],
            span["quote"],
        )
        self.assertEqual(span["source_column"], "Notes")

    def test_checks_and_qualifications_remain_in_full_source(self):
        record = source()
        review = build_history_review([record], [proposal()])

        self.assertEqual(
            review["entries"][0]["source_text"]["narrative_raw"],
            record.narrative_raw,
        )
        self.assertIn("Test passed.", review["text"])
        self.assertIsNone(review["semantic_task_success"])
        self.assertIn(
            "do not establish a common cause",
            review["limitations"],
        )

    def test_unselected_proposal_is_not_rendered(self):
        review = build_history_review(
            [source()],
            [proposal(), proposal("UNSELECTED")],
        )

        self.assertEqual(len(review["entries"]), 1)
        self.assertNotIn("UNSELECTED", review["text"])

    def test_missing_extraction_and_duplicate_proposals_are_rejected(self):
        with self.assertRaises(ValueError):
            build_history_review([source()], [])

        with self.assertRaises(ValueError):
            build_history_review(
                [source()],
                [proposal(), proposal()],
            )

    def test_invented_source_excerpt_is_rejected(self):
        value = proposal()
        value["fields"]["action"]["quote"] = "REPLACED CONNECTOR"

        with self.assertRaises(ValueError):
            build_history_review([source()], [value])

    def test_history_output_is_attached_to_completed_graph_run(self):
        value = proposal()

        decisions = [
            {"tool": "search", "args": {"query": "Connector"}},
            {"tool": "record", "args": {"record_id": "R1"}},
            {
                "tool": "extract",
                "args": {
                    "record_id": "R1",
                    "fields": value["fields"],
                    "action_status": "completed",
                },
            },
            {"tool": "aggregate", "args": {}},
            {"tool": "finish", "args": {"record_ids": ["R1"]}},
        ]

        report = run_agent(
            [source()],
            "Review history",
            Replay(decisions),
        )

        self.assertEqual(report["status"], "ready_for_review")
        self.assertEqual(
            report["history_review"]["status"],
            "available_for_review",
        )
        self.assertEqual(
            report["history_review"]["entries"][0]["record_id"],
            "R1",
        )
        self.assertEqual(report["model_calls"], 0)
        self.assertIsNone(report["history_review"]["semantic_task_success"])

    def test_incomplete_run_does_not_get_history_output(self):
        report = run_agent(
            [source()],
            "Review history",
            Replay(
                [
                    {
                        "tool": "abstain",
                        "args": {"reason": "Insufficient evidence"},
                    }
                ]
            ),
        )

        self.assertEqual(report["status"], "abstained")
        self.assertIsNone(report["history_review"])


if __name__ == "__main__":
    unittest.main()
