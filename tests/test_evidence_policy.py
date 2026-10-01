"""Boundary preservation and status-repair contract regressions."""

import unittest
from copy import deepcopy

from maintlog.evidence_policy import (
    adapt_boundaries,
    source_record,
    status_repair_contract,
)
from maintlog.extraction import resolve_span


def decision(action, status="completed"):
    return {
        "tool": "extract",
        "args": {
            "record_id": "R",
            "fields": {
                "component": None,
                "problem": None,
                "action": {
                    "field": "narrative_raw",
                    "quote": action,
                },
            },
            "action_status": status,
        },
    }


class EvidencePolicyTests(unittest.TestCase):
    def test_boundary_adjustment_preserves_source_and_original_proposal(self):
        source = {"record_id": "R", "narrative_raw": "Replaced CPL-218."}
        proposed = decision(source["narrative_raw"])
        original = deepcopy(proposed)

        adjusted, audit = adapt_boundaries(proposed, source)

        self.assertEqual(proposed, original)
        span = adjusted["args"]["fields"]["action"]
        self.assertEqual(
            source["narrative_raw"][span["start"] : span["end"]],
            "Replaced CPL-218",
        )
        self.assertEqual(audit["original_decision"], original)
        self.assertEqual(len(audit["changes"]), 1)

    def test_conservative_abbreviations_and_numbers_are_preserved(self):
        for text in (
            "Checked rev.",
            "Checked U.S.",
            "Measured 2.5.",
            "Checked RPM.",
        ):
            with self.subTest(text=text):
                proposed = decision(text)
                adjusted, audit = adapt_boundaries(
                    proposed, {"record_id": "R", "narrative_raw": text}
                )
                self.assertEqual(adjusted, proposed)
                self.assertEqual(audit["changes"], [])

    def test_repeated_action_offsets_remain_unambiguous(self):
        text = "Replaced CPL-218. Replaced CPL-218."
        start = text.rfind("Replaced")
        proposed = decision("unused")
        proposed["args"]["fields"]["action"] = {
            "field": "narrative_raw",
            "start": start,
            "end": len(text),
        }

        adjusted, _ = adapt_boundaries(
            proposed, {"record_id": "R", "narrative_raw": text}
        )
        span = adjusted["args"]["fields"]["action"]
        self.assertEqual(span["start"], start)
        self.assertEqual(text[span["start"] : span["end"]], "Replaced CPL-218")

    def test_negated_status_repair_preserves_action_and_excludes_attempted(self):
        source = {"record_id": "R", "narrative_raw": "Did not replace CPL-218"}
        proposed = decision(source["narrative_raw"], "attempted")
        record = source_record(source)
        fields = proposed["args"]["fields"]
        validated = {
            name: resolve_span(record, span, name) for name, span in fields.items()
        }
        feedback = {
            "rejected_decision": proposed,
            "status_repair": {"validated_fields": validated},
        }

        contract = status_repair_contract(feedback, source)

        self.assertIsNotNone(contract)
        _, locked, statuses = contract
        self.assertEqual(locked, fields)
        self.assertEqual(statuses, ["unknown"])

    def test_invalid_evidence_cannot_be_locked_for_status_repair(self):
        source = {"record_id": "R", "narrative_raw": "Checked coupling"}
        feedback = {
            "rejected_decision": decision("Invented action", "attempted"),
            "status_repair": {"validated_fields": {}},
        }
        self.assertIsNone(status_repair_contract(feedback, source))
