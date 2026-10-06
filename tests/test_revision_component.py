"""Component revisions must stay inside source-derived boundaries."""

import unittest

from test_evidence_review import example
from test_evidence_revision import actions

from maintlog.agent import run_agent
from maintlog.backends import Replay
from maintlog.revision_component import component_revision_candidate


class RevisionComponentTests(unittest.TestCase):
    def context(self):
        record, original = example()
        source = {
            "record_id": "R1",
            "narrative_raw": record.narrative_raw,
        }
        revision = {
            "previous_proposal": original,
            "concerns": [
                {
                    "field": "component",
                    "code": "possible_omitted_subpart",
                }
            ],
        }
        return record, source, revision

    def test_exact_subpart_boundary_excludes_condition(self):
        _, source, revision = self.context()
        span = component_revision_candidate(source, revision)

        self.assertEqual(
            source[span["field"]][span["start"] : span["end"]],
            "SENSOR ELECTRICAL CONNECTOR",
        )

    def test_wrong_source_identity_is_rejected(self):
        _, source, revision = self.context()
        source["record_id"] = "R2"

        with self.assertRaises(ValueError):
            component_revision_candidate(source, revision)

    def test_offsets_disagreeing_with_quote_are_rejected(self):
        _, source, revision = self.context()
        revision["previous_proposal"]["fields"]["component"]["end"] += 1

        with self.assertRaises(ValueError):
            component_revision_candidate(source, revision)

    def test_other_concerns_do_not_trigger_component_extension(self):
        _, source, revision = self.context()
        revision["concerns"] = [
            {
                "field": "problem",
                "code": "possible_diagnosis_in_symptom_field",
            }
        ]

        self.assertIsNone(component_revision_candidate(source, revision))

    def test_overextended_revision_is_rejected_in_complete_graph(self):
        record, original = example()
        _, revised = example(component="SENSOR ELECTRICAL CONNECTOR")

        span = revised["fields"]["component"]
        span["end"] += len(" LOOSE")
        span["quote"] = record.narrative_raw[span["start"] : span["end"]]

        report = run_agent(
            [record],
            "Review",
            Replay(actions(original, revised)),
        )

        self.assertIn(
            "boundary choices",
            report["trace"][3]["tool_error"],
        )
        self.assertEqual(
            report["extraction_proposals"][0]["fields"],
            original["fields"],
        )
        self.assertEqual(
            report["history_review"]["status"],
            "needs_evidence_review",
        )


if __name__ == "__main__":
    unittest.main()
