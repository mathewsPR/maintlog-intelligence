"""Component recovery during an existing constrained status-repair call."""

import unittest
from copy import deepcopy

from maintlog.component_selection import (
    component_candidates,
    resolve_component_choice,
)
from maintlog.decision_schema import validate_decision
from maintlog.evidence_policy import (
    source_record,
    status_repair_contract,
    validate_status_repair,
)
from maintlog.extraction import resolve_span, validate_fields


class ComponentRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "record_id": "TEST-01",
            "component": "",
            "issue_raw": "",
            "action_raw": "",
            "narrative_raw": "Pump vibrating. Did not replace PMP-741.",
        }
        self.fields = {
            "component": None,
            "problem": {
                "field": "narrative_raw",
                "quote": "Pump vibrating",
            },
            "action": {
                "field": "narrative_raw",
                "quote": "Did not replace PMP-741",
            },
        }
        self.candidates = component_candidates(self.source)

    def contract(self, fields=None, candidates=None):
        fields = deepcopy(self.fields if fields is None else fields)
        record = source_record(self.source)
        feedback = {
            "rejected_decision": {
                "tool": "extract",
                "args": {
                    "record_id": self.source["record_id"],
                    "fields": fields,
                    "action_status": "attempted",
                },
            },
            "status_repair": {
                "validated_fields": {
                    name: resolve_span(record, span, name)
                    for name, span in fields.items()
                },
            },
        }
        return status_repair_contract(
            feedback,
            self.source,
            candidates=self.candidates if candidates is None else candidates,
        )

    def decision(self, fields):
        return {
            "tool": "extract",
            "args": {
                "record_id": self.source["record_id"],
                "fields": deepcopy(fields),
                "action_status": "unknown",
            },
        }

    def test_missing_component_can_be_recovered_without_changing_evidence(self):
        schema, locked, statuses = self.contract()
        choices = schema["properties"]["args"]["properties"]["fields"]["properties"][
            "component"
        ]["anyOf"][1]["enum"]
        self.assertEqual(choices, list(self.candidates))
        self.assertEqual(statuses, ["unknown"])

        decision = self.decision(locked)
        decision["args"]["fields"]["component"] = next(iter(self.candidates))
        validate_status_repair(decision, locked, statuses, self.candidates)

        translated = resolve_component_choice(decision, self.candidates)
        validate_decision(translated)
        resolved = validate_fields(
            source_record(self.source),
            translated["args"]["fields"],
            translated["args"]["action_status"],
        )
        self.assertEqual(resolved["component"]["quote"], "PMP-741")
        self.assertEqual(translated["args"]["fields"]["problem"], locked["problem"])
        self.assertEqual(translated["args"]["fields"]["action"], locked["action"])

    def test_null_remains_allowed(self):
        _, locked, statuses = self.contract()
        validate_status_repair(self.decision(locked), locked, statuses, self.candidates)

    def test_unknown_candidate_and_changed_evidence_are_rejected(self):
        _, locked, statuses = self.contract()
        mutations = {
            "component": "missing-candidate",
            "problem": None,
            "action": None,
        }
        for name, value in mutations.items():
            with self.subTest(field=name):
                decision = self.decision(locked)
                decision["args"]["fields"][name] = value
                with self.assertRaises(ValueError):
                    validate_status_repair(decision, locked, statuses, self.candidates)

    def test_existing_component_stays_locked(self):
        fields = deepcopy(self.fields)
        fields["component"] = {
            "field": "narrative_raw",
            "quote": "PMP-741",
        }
        _, locked, statuses = self.contract(fields=fields)
        validate_status_repair(self.decision(locked), locked, statuses, self.candidates)

        for replacement in (None, next(iter(self.candidates))):
            with self.subTest(replacement=replacement):
                decision = self.decision(locked)
                decision["args"]["fields"]["component"] = replacement
                with self.assertRaises(ValueError):
                    validate_status_repair(decision, locked, statuses, self.candidates)

    def test_without_candidates_component_remains_null(self):
        _, locked, statuses = self.contract(candidates={})
        decision = self.decision(locked)
        validate_status_repair(decision, locked, statuses, {})

        decision["args"]["fields"]["component"] = "c1"
        with self.assertRaises(ValueError):
            validate_status_repair(decision, locked, statuses, {})


if __name__ == "__main__":
    unittest.main()
