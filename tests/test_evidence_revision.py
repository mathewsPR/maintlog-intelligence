"""Evidence revisions are bounded, source checked, and auditable."""

import unittest

from test_evidence_review import example

from maintlog.agent import run_agent
from maintlog.backends import Replay
from maintlog.comparison import FixedWorkflow


def decision(proposal):
    return {
        "tool": "extract",
        "args": {
            "record_id": proposal["record_id"],
            "fields": {
                name: {key: span[key] for key in ("field", "start", "end")}
                if span is not None
                else None
                for name, span in proposal["fields"].items()
            },
            "action_status": proposal["action_status_proposal"],
        },
    }


def actions(original, revised):
    return [
        {"tool": "search", "args": {"query": "Warning"}},
        {"tool": "record", "args": {"record_id": "R1"}},
        decision(original),
        decision(revised),
        {"tool": "aggregate", "args": {}},
        {"tool": "finish", "args": {"record_ids": ["R1"]}},
    ]


class EvidenceRevisionTests(unittest.TestCase):
    def test_flagged_component_can_be_corrected_with_original_retained(self):
        record, original = example()
        _, revised = example(component="SENSOR ELECTRICAL CONNECTOR")

        report = run_agent([record], "Review", Replay(actions(original, revised)))

        self.assertEqual(report["status"], "ready_for_review")
        self.assertEqual(report["history_review"]["status"], "available_for_review")
        self.assertEqual(report["evidence_revision_attempted"], ["R1"])
        self.assertEqual(
            report["trace"][2]["tool_result"]["fields"]["component"]["quote"],
            "SENSOR",
        )
        self.assertEqual(
            report["trace"][3]["evidence_revision"]["previous_proposal"]["fields"][
                "component"
            ]["quote"],
            "SENSOR",
        )
        self.assertEqual(
            report["extraction_proposals"][0]["fields"]["component"]["quote"],
            "SENSOR ELECTRICAL CONNECTOR",
        )

    def test_unchanged_warning_is_not_retried_forever(self):
        record, original = example()
        report = run_agent([record], "Review", Replay(actions(original, original)))

        self.assertEqual(report["status"], "ready_for_review")
        self.assertEqual(report["history_review"]["status"], "needs_evidence_review")
        self.assertEqual(
            len([step for step in report["trace"] if "evidence_revision" in step]),
            1,
        )

    def test_unflagged_field_change_is_rejected(self):
        record, original = example()
        _, revised = example(
            component="SENSOR ELECTRICAL CONNECTOR",
            problem="FOUND SENSOR ELECTRICAL CONNECTOR LOOSE",
        )

        report = run_agent([record], "Review", Replay(actions(original, revised)))

        self.assertIn("unflagged field", report["trace"][3]["tool_error"])
        self.assertEqual(
            report["extraction_proposals"][0]["fields"],
            original["fields"],
        )
        self.assertEqual(report["history_review"]["status"], "needs_evidence_review")

    def test_status_change_is_rejected(self):
        record, original = example()
        _, revised = example(component="SENSOR ELECTRICAL CONNECTOR")
        revised["action_status_proposal"] = "unknown"

        report = run_agent([record], "Review", Replay(actions(original, revised)))

        self.assertIn("preserve action status", report["trace"][3]["tool_error"])
        self.assertEqual(
            report["extraction_proposals"][0]["action_status_proposal"],
            "completed",
        )

    def test_fixed_workflow_uses_same_revision_without_advancing_schedule(self):
        record, original = example()
        _, revised = example(component="SENSOR ELECTRICAL CONNECTOR")

        backend = FixedWorkflow(
            Replay([decision(original), decision(revised)]),
            "Warning",
            "history",
        )
        report = run_agent([record], "Review", backend)

        self.assertEqual(report["status"], "ready_for_review")
        self.assertEqual(report["history_review"]["status"], "available_for_review")
        self.assertEqual(report["evidence_revision_attempted"], ["R1"])

    def test_null_cannot_hide_a_flagged_component(self):
        record, original = example()
        _, revised = example(component="SENSOR ELECTRICAL CONNECTOR")
        revised["fields"]["component"] = None

        report = run_agent([record], "Review", Replay(actions(original, revised)))

        self.assertIn("cannot discard", report["trace"][3]["tool_error"])
        self.assertEqual(report["history_review"]["status"], "needs_evidence_review")

    def test_existing_step_limit_is_preserved(self):
        record, original = example()
        _, revised = example(component="SENSOR ELECTRICAL CONNECTOR")

        report = run_agent(
            [record],
            "Review",
            Replay(actions(original, revised)),
            max_steps=5,
        )

        self.assertEqual(report["status"], "budget_exhausted")
        self.assertEqual(report["steps"], 5)
        self.assertIsNone(report["history_review"])


if __name__ == "__main__":
    unittest.main()
