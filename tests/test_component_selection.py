"""Component selection contract regressions."""

import unittest
from copy import deepcopy

from maintlog.component_selection import (
    component_candidates,
    resolve_component_choice,
    selection_schema,
)
from maintlog.decision_schema import ARGS, validate_decision


class ComponentSelectionTests(unittest.TestCase):
    def test_repeated_identifiers_preserve_distinct_source_locations(self):
        source = "Checked CPL-218. Replaced CPL-218."
        candidates = component_candidates(
            {
                "component": "",
                "issue_raw": "",
                "narrative_raw": source,
            }
        )

        self.assertEqual(len(candidates), 2)
        starts = []
        for span in candidates.values():
            self.assertEqual(
                source[span["start"] : span["end"]],
                "CPL-218",
            )
            starts.append(span["start"])
        self.assertEqual(len(set(starts)), 2)

    def test_no_identifier_does_not_fabricate_candidates(self):
        candidates = component_candidates(
            {
                "component": "",
                "issue_raw": "",
                "narrative_raw": "Coupling noisy; cause unknown.",
            }
        )
        self.assertEqual(candidates, {})

    def test_translation_preserves_other_fields_and_status(self):
        candidates = component_candidates(
            {
                "component": "",
                "issue_raw": "",
                "narrative_raw": "Coupling noisy. Replaced CPL-218.",
            }
        )
        decision = {
            "tool": "extract",
            "args": {
                "record_id": "TEST-1",
                "fields": {
                    "component": "c1",
                    "problem": {
                        "field": "narrative_raw",
                        "quote": "Coupling noisy",
                    },
                    "action": {
                        "field": "narrative_raw",
                        "quote": "Replaced CPL-218",
                    },
                },
                "action_status": "completed",
            },
        }
        original = deepcopy(decision)

        translated = resolve_component_choice(decision, candidates)

        self.assertEqual(decision, original)
        self.assertEqual(
            translated["args"]["fields"]["problem"],
            original["args"]["fields"]["problem"],
        )
        self.assertEqual(
            translated["args"]["fields"]["action"],
            original["args"]["fields"]["action"],
        )
        self.assertEqual(translated["args"]["action_status"], "completed")
        validate_decision(translated)

    def test_unknown_candidate_is_rejected(self):
        decision = {
            "tool": "extract",
            "args": {
                "record_id": "TEST-1",
                "fields": {
                    "component": "missing",
                    "problem": None,
                    "action": None,
                },
                "action_status": "unknown",
            },
        }
        with self.assertRaisesRegex(ValueError, "supplied candidate"):
            resolve_component_choice(decision, {"c1": {}})

    def test_schema_does_not_mutate_shared_extraction_contract(self):
        original = deepcopy(ARGS["extract"])
        schema = selection_schema("TEST-1", ARGS["extract"], {"c1": {}})

        self.assertEqual(ARGS["extract"], original)
        component = schema["properties"]["args"]["properties"]["fields"]["properties"][
            "component"
        ]
        self.assertEqual(
            component["anyOf"],
            [
                {"type": "null"},
                {"type": "string", "enum": ["c1"]},
            ],
        )
