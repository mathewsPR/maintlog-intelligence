"""Audit preservation and bounded missing-action reconsideration."""

import unittest
from copy import deepcopy
from dataclasses import asdict, replace

from test_record_progress_guard import source

from maintlog.agent import run_agent
from maintlog.backends import Replay
from maintlog.decision_schema import _valid
from maintlog.evidence_review import review_evidence
from maintlog.extraction import validate_fields
from maintlog.revision_evidence import excerpt_contract
from maintlog.working_context import compact_context


class SearchAndOmissionTests(unittest.TestCase):
    def test_duplicate_searches_keep_latest_result_and_original_audit(self):
        search = {"tool": "search", "result": {"hits": [{"record_id": "R1"}]}}
        context = {
            "observations": [deepcopy(search), deepcopy(search), deepcopy(search)]
        }
        original = deepcopy(context)

        result = compact_context(context)

        self.assertEqual(context, original)
        self.assertEqual(result["observations"], [search])
        self.assertEqual(
            result["search_progress_notice"]["duplicate_results_compacted"], 2
        )

    def test_changed_search_results_and_errors_are_retained(self):
        observations = [
            {"tool": "search", "result": {"hits": []}},
            {"tool": "search", "result": {"hits": [{"record_id": "R1"}]}},
            {"tool": "search", "result": {"error": "failure"}},
        ]
        self.assertEqual(
            compact_context({"observations": observations})["observations"],
            observations,
        )

    def record_and_proposal(self, text="BOOT HAS CRACK. REPLACED BOOT"):
        record = replace(source(), narrative_raw=text)
        fields = {"component": None, "problem": None, "action": None}
        proposal = {
            "record_id": "R1",
            "fields": validate_fields(record, fields, "unknown"),
            "action_status_proposal": "unknown",
        }
        return record, proposal

    def test_negated_and_future_work_do_not_trigger_completed_work_hint(self):
        for text in ("DID NOT REPLACE BOOT", "BOOT WILL BE REPLACED"):
            record, proposal = self.record_and_proposal(text)
            review = review_evidence([record], [proposal])
            self.assertEqual(review["concerns"], [])

    def test_revision_contract_retains_null_and_locks_status(self):
        record, proposal = self.record_and_proposal()
        revision = {
            "previous_proposal": proposal,
            "concerns": review_evidence([record], [proposal])["concerns"],
        }
        schema, _ = excerpt_contract(asdict(record), revision)
        decision = {
            "tool": "extract",
            "args": {
                "record_id": "R1",
                "fields": proposal["fields"],
                "action_status": "unknown",
            },
        }

        self.assertTrue(_valid(decision, schema))
        decision["args"]["action_status"] = "completed"
        self.assertFalse(_valid(decision, schema))

    def test_complete_agent_reconsiders_once_and_preserves_original(self):
        record, _ = self.record_and_proposal()
        original = {
            "tool": "extract",
            "args": {
                "record_id": "R1",
                "fields": {"component": None, "problem": None, "action": None},
                "action_status": "unknown",
            },
        }
        revised = deepcopy(original)
        revised["args"]["fields"]["action"] = {
            "field": "narrative_raw",
            "quote": "REPLACED BOOT",
        }

        report = run_agent(
            [record],
            "Review history",
            Replay(
                [
                    {"tool": "search", "args": {"query": "BOOT"}},
                    {"tool": "record", "args": {"record_id": "R1"}},
                    original,
                    revised,
                    {"tool": "aggregate", "args": {}},
                    {"tool": "finish", "args": {"record_ids": ["R1"]}},
                ]
            ),
        )

        self.assertEqual(report["status"], "ready_for_review")
        self.assertEqual(report["evidence_revision_attempted"], ["R1"])
        self.assertIsNone(report["trace"][2]["tool_result"]["fields"]["action"])
        self.assertEqual(
            report["extraction_proposals"][0]["fields"]["action"]["quote"],
            "REPLACED BOOT",
        )
        self.assertEqual(
            report["extraction_proposals"][0]["action_status_proposal"], "unknown"
        )


if __name__ == "__main__":
    unittest.main()
