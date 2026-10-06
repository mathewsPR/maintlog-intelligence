"""Repeated-quote repairs retain exact evidence and existing validation."""

import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from maintlog.backends import EXTRACTION_SYSTEM, LocalServer
from maintlog.decision_schema import _valid
from maintlog.evidence_policy import source_record
from maintlog.extraction import validate_fields
from maintlog.occurrence_repair import occurrence_contract


class OccurrenceRepairTests(unittest.TestCase):
    def fixture(self):
        source = {
            "record_id": "R1",
            "narrative_raw": "BATTERY failed. Replaced BATTERY.",
        }
        rejected = {
            "tool": "extract",
            "args": {
                "record_id": "R1",
                "fields": {
                    "component": {"field": "narrative_raw", "quote": "BATTERY"},
                    "problem": {"field": "narrative_raw", "quote": "BATTERY failed"},
                    "action": {"field": "narrative_raw", "quote": "Replaced BATTERY"},
                },
                "action_status": "completed",
            },
        }
        return source, {"rejected_decision": rejected}

    def test_choices_are_all_exact_occurrences_and_valid_fields_locked(self):
        source, feedback = self.fixture()
        schema, shown = occurrence_contract(source, feedback)
        self.assertEqual([s["start"] for s in shown["component"]], [0, 25])
        decision = deepcopy(feedback["rejected_decision"])
        decision["args"]["fields"] = {
            name: {key: spans[-1][key] for key in ("field", "start", "end")}
            for name, spans in shown.items()
        }
        self.assertTrue(_valid(decision, schema))
        validate_fields(source_record(source), decision["args"]["fields"], "completed")
        decision["args"]["fields"]["component"]["start"] += 1
        self.assertFalse(_valid(decision, schema))

    def test_status_cannot_change(self):
        source, feedback = self.fixture()
        schema, shown = occurrence_contract(source, feedback)
        decision = deepcopy(feedback["rejected_decision"])
        decision["args"]["fields"] = {
            name: {key: spans[0][key] for key in ("field", "start", "end")}
            for name, spans in shown.items()
        }
        decision["args"]["action_status"] = "verified"
        self.assertFalse(_valid(decision, schema))

    def test_mismatch_missing_quote_and_excessive_choices_refuse_contract(self):
        source, feedback = self.fixture()
        self.assertIsNone(
            occurrence_contract(dict(source, record_id="other"), feedback)
        )
        altered = deepcopy(feedback)
        altered["rejected_decision"]["args"]["fields"]["action"]["quote"] = "invented"
        self.assertIsNone(occurrence_contract(source, altered))
        source["narrative_raw"] += " BATTERY" * 9
        self.assertIsNone(occurrence_contract(source, feedback))

    def test_omitted_negation_is_not_repaired(self):
        source, feedback = self.fixture()
        source["narrative_raw"] = (
            "BATTERY failed. Not Replaced BATTERY. Replaced BATTERY."
        )
        self.assertIsNone(occurrence_contract(source, feedback))

    def test_backend_uses_contract_and_preserves_audit(self):
        source, feedback = self.fixture()
        _, shown = occurrence_contract(source, feedback)
        decision = deepcopy(feedback["rejected_decision"])
        decision["args"]["fields"] = {
            name: {key: spans[-1][key] for key in ("field", "start", "end")}
            for name, spans in shown.items()
        }
        decoded = {"choices": [{"message": {"content": json.dumps(decision)}}]}
        process = SimpleNamespace(returncode=0, stdout=json.dumps(decoded), stderr="")
        with patch("maintlog.backends.subprocess.run", return_value=process) as call:
            response = LocalServer().decide(
                EXTRACTION_SYSTEM,
                {
                    "extraction_record": source,
                    "validation_feedback": feedback,
                },
                30,
            )
        body = json.loads(call.call_args.kwargs["input"])["body"]
        self.assertIn("occurrence_options", body["messages"][1]["content"])
        self.assertIsNotNone(response["extraction_audit"]["occurrence_repair_options"])

    def test_drilling_status_keeps_negation_and_planning_constraints(self):
        fields = {
            "component": None,
            "problem": None,
            "action": {
                "field": "narrative_raw",
                "quote": "Drilled beam",
            },
        }
        validate_fields(
            source_record({"narrative_raw": "Drilled beam"}), fields, "completed"
        )
        for text in ("Not drilled beam", "Will be drilled beam", "DRLLED beam"):
            fields["action"]["quote"] = text
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_fields(
                    source_record({"narrative_raw": text}), fields, "completed"
                )


if __name__ == "__main__":
    unittest.main()
