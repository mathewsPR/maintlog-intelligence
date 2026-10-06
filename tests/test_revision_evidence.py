"""Source alternatives preserve evidence and the existing revision limits."""

import unittest

from test_evidence_review import example
from test_evidence_revision import actions

from maintlog.agent import run_agent
from maintlog.backends import Replay
from maintlog.decision_schema import _valid
from maintlog.evidence_review import review_evidence
from maintlog.revision_evidence import excerpt_contract, excerpt_options


class ExcerptChoiceTests(unittest.TestCase):
    def fixture(self):
        record, previous = example(
            component="SENSOR ELECTRICAL CONNECTOR",
            problem="FOUND SENSOR ELECTRICAL CONNECTOR LOOSE",
            action="CORRECTIVE ACTION- FOUND SENSOR ELECTRICAL CONNECTOR LOOSE. RESECURED SENSOR ELECTRICAL CONNECTOR",
        )
        revision = {
            "previous_proposal": previous,
            "concerns": review_evidence([record], [previous])["concerns"],
        }
        return (
            record,
            previous,
            revision,
            {
                "record_id": record.record_id,
                "narrative_raw": record.narrative_raw,
            },
        )

    def test_symptom_and_work_choices_come_from_source(self):
        _, _, revision, source = self.fixture()
        options = excerpt_options(source, revision)
        self.assertIn("Warning light on", self.quotes(source, options["problem"]))
        self.assertIn(
            "RESECURED SENSOR ELECTRICAL CONNECTOR",
            self.quotes(source, options["action"]),
        )

    def quotes(self, source, options):
        return [source[s["field"]][s["start"] : s["end"]] for s in options]

    def test_abbreviation_is_not_a_sentence_boundary(self):
        _, previous, revision, source = self.fixture()
        source["narrative_raw"] = source["narrative_raw"].replace(
            "SENSOR", "FWD. SENSOR"
        )
        text = source["narrative_raw"]
        for span in previous["fields"].values():
            span["quote"] = span["quote"].replace("SENSOR", "FWD. SENSOR")
            span["start"] = text.index(span["quote"])
            span["end"] = span["start"] + len(span["quote"])
        options = excerpt_options(source, revision)
        self.assertIn(
            "RESECURED FWD. SENSOR ELECTRICAL CONNECTOR",
            self.quotes(source, options["action"]),
        )

    def test_no_warning_produces_no_contract(self):
        _, _, revision, source = self.fixture()
        revision["concerns"] = []
        self.assertIsNone(excerpt_contract(source, revision))

    def test_reporting_prefix_is_optional_not_automatically_removed(self):
        _, previous, revision, source = self.fixture()
        source["narrative_raw"] = "Operator reported " + source["narrative_raw"]
        for span in previous["fields"].values():
            span["start"] += len("Operator reported ")
            span["end"] += len("Operator reported ")
        quotes = self.quotes(source, excerpt_options(source, revision)["problem"])
        self.assertIn("Operator reported Warning light on", quotes)
        self.assertIn("Warning light on", quotes)

    def test_wrong_record_and_forged_excerpt_are_rejected(self):
        _, _, revision, source = self.fixture()
        with self.assertRaises(ValueError):
            excerpt_options(dict(source, record_id="other"), revision)
        revision["previous_proposal"]["fields"]["problem"]["quote"] = "invented"
        with self.assertRaises(ValueError):
            excerpt_options(source, revision)

    def test_schema_locks_status_and_unchanged_component(self):
        _, previous, revision, source = self.fixture()
        schema, shown = excerpt_contract(source, revision)
        decision = {
            "tool": "extract",
            "args": {
                "record_id": source["record_id"],
                "fields": {
                    name: {k: choices[0][k] for k in ("field", "start", "end")}
                    for name, choices in shown.items()
                },
                "action_status": previous["action_status_proposal"],
            },
        }
        self.assertTrue(_valid(decision, schema))
        decision["args"]["action_status"] = "unknown"
        self.assertFalse(_valid(decision, schema))

    def test_complete_graph_accepts_source_choices(self):
        record, original, _, _ = self.fixture()
        _, revised = example(component="SENSOR ELECTRICAL CONNECTOR")
        report = run_agent([record], "Review", Replay(actions(original, revised)))
        self.assertEqual(report["status"], "ready_for_review")
        self.assertEqual(report["extraction_proposals"][0]["fields"], revised["fields"])
        self.assertEqual(report["evidence_revision_attempted"], [record.record_id])

    def test_graph_rejects_non_candidate_even_if_source_valid(self):
        record, original, _, _ = self.fixture()
        _, revised = example(
            component="SENSOR ELECTRICAL CONNECTOR", problem="light on"
        )
        report = run_agent([record], "Review", Replay(actions(original, revised)))
        self.assertIn("source excerpt choices", report["trace"][3]["tool_error"])
        self.assertEqual(
            report["extraction_proposals"][0]["fields"], original["fields"]
        )


if __name__ == "__main__":
    unittest.main()
