"""Targeted checks must flag ambiguity without rewriting evidence."""

import unittest
from copy import deepcopy
from datetime import date

from maintlog.domain import Evidence, Record
from maintlog.evidence_review import review_evidence
from maintlog.extraction import validate_fields
from maintlog.history_review import build_history_review


def example(
    component="SENSOR",
    problem="Warning light on",
    action="RESECURED SENSOR ELECTRICAL CONNECTOR",
):
    text = (
        "Warning light on. CORRECTIVE ACTION- "
        "FOUND SENSOR ELECTRICAL CONNECTOR LOOSE. "
        "RESECURED SENSOR ELECTRICAL CONNECTOR"
    )

    record = Record(
        "R1",
        date(2024, 1, 1),
        "A1",
        "",
        "",
        "",
        "",
        "",
        Evidence("records.csv", "a" * 64, 2, "synthetic"),
        text,
    )

    start = text.index(component)
    fields = {
        "component": {
            "field": "narrative_raw",
            "start": start,
            "end": start + len(component),
        },
        "problem": {
            "field": "narrative_raw",
            "quote": problem,
        },
        "action": {
            "field": "narrative_raw",
            "quote": action,
        },
    }

    proposal = {
        "record_id": "R1",
        "fields": validate_fields(record, fields, "completed"),
        "action_status_proposal": "completed",
    }
    return record, proposal


class EvidenceReviewTests(unittest.TestCase):
    def test_short_parent_phrase_is_flagged(self):
        record, proposal = example()
        before = deepcopy(proposal)

        result = review_evidence([record], [proposal])
        codes = [item["code"] for item in result["concerns"]]

        self.assertIn("possible_omitted_subpart", codes)
        self.assertEqual(proposal, before)
        self.assertIsNone(result["semantic_accuracy"])

    def test_complete_component_has_no_subpart_warning(self):
        record, proposal = example(component="SENSOR ELECTRICAL CONNECTOR")
        result = review_evidence([record], [proposal])

        self.assertEqual(result["concerns"], [])
        self.assertIsNone(result["semantic_accuracy"])

    def test_diagnostic_finding_after_heading_is_flagged(self):
        record, proposal = example(problem="FOUND SENSOR ELECTRICAL CONNECTOR LOOSE")
        result = review_evidence([record], [proposal])
        codes = [item["code"] for item in result["concerns"]]

        self.assertIn("possible_diagnosis_in_symptom_field", codes)

    def test_symptom_before_heading_has_no_diagnosis_warning(self):
        record, proposal = example()
        result = review_evidence([record], [proposal])
        codes = [item["code"] for item in result["concerns"]]

        self.assertNotIn("possible_diagnosis_in_symptom_field", codes)

    def test_action_heading_is_flagged(self):
        record, proposal = example(
            action=(
                "CORRECTIVE ACTION- "
                "FOUND SENSOR ELECTRICAL CONNECTOR LOOSE. "
                "RESECURED SENSOR ELECTRICAL CONNECTOR"
            )
        )
        result = review_evidence([record], [proposal])
        codes = [item["code"] for item in result["concerns"]]

        self.assertIn("action_contains_administrative_heading", codes)

    def test_history_discloses_concerns_without_repairing_fields(self):
        record, proposal = example()
        history = build_history_review([record], [proposal])

        self.assertEqual(history["status"], "needs_evidence_review")
        self.assertEqual(
            history["entries"][0]["fields"]["component"]["quote"],
            "SENSOR",
        )
        self.assertIn("Evidence review required", history["text"])
        self.assertIsNone(history["semantic_task_success"])


if __name__ == "__main__":
    unittest.main()
