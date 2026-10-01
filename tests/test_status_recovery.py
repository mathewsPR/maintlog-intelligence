"""Execution status and rejected-decision recovery regressions."""

import json
import unittest
from pathlib import Path

from maintlog.agent import run_agent
from maintlog.backends import Replay
from maintlog.decision_schema import ARGS
from maintlog.extraction import (
    STATUS_GUIDANCE,
    has_unnegated_status_cue,
    validate_fields,
)
from maintlog.ingestion import load_csv, load_profile
from maintlog.scope import Scope

ROOT = Path(__file__).resolve().parents[1]


class StatusRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.records = load_csv(
            ROOT / "data/demo/company_export.csv",
            data_kind="synthetic",
            columns=load_profile(ROOT / "data/demo/company_profile.json"),
        )
        self.fields = {
            "component": {"field": "narrative_raw", "quote": "BRG-204"},
            "problem": {
                "field": "narrative_raw",
                "quote": "Vibration still high; no successful repair confirmed",
            },
            "action": {"field": "narrative_raw", "quote": "Replaced BRG-204"},
        }

    def extract(self, status):
        return {
            "tool": "extract",
            "args": {
                "record_id": "WO-02",
                "fields": self.fields,
                "action_status": status,
            },
        }

    def run_decisions(self, decisions):
        backend = Replay(decisions)
        contexts = []
        original = backend.decide

        def capture(system, context, timeout):
            self.assertIn(STATUS_GUIDANCE, system)
            contexts.append(json.loads(json.dumps(context)))
            return original(system, context, timeout)

        backend.decide = capture
        report = run_agent(
            self.records, "Review history", backend, scope=Scope(asset_id="PUMP-001")
        )
        return report, contexts

    def test_schema_explains_execution_separately_from_success(self):
        self.assertEqual(
            ARGS["extract"]["properties"]["action_status"]["description"],
            STATUS_GUIDANCE,
        )

    def test_performed_work_rejects_attempted_and_verified(self):
        for status in ("attempted", "verified"):
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(ValueError, "requires explicit"),
            ):
                validate_fields(self.records[1], self.fields, status)
        validate_fields(self.records[1], self.fields, "completed")
        validate_fields(self.records[1], self.fields, "unknown")

    def test_corrected_status_can_finish_without_relaxing_validation(self):
        rejected = self.extract("attempted")
        report, contexts = self.run_decisions(
            [
                {"tool": "search", "args": {"query": "vibration"}},
                {"tool": "aggregate", "args": {}},
                {"tool": "record", "args": {"record_id": "WO-02"}},
                rejected,
                self.extract("completed"),
                {"tool": "finish", "args": {"record_ids": ["WO-02"]}},
            ]
        )
        feedback = contexts[4]["observations"][-1]["result"]
        self.assertEqual(feedback["rejected_decision"], rejected)
        self.assertIn("tried or attempted", feedback["error"])
        self.assertIn("Do not repeat", feedback["retry_instruction"])
        self.assertEqual(report["status"], "ready_for_review")
        self.assertEqual(
            report["extraction_proposals"][0]["action_status_proposal"], "completed"
        )
        self.assertIn(
            "no successful repair confirmed",
            report["extraction_proposals"][0]["fields"]["problem"]["quote"],
        )

    def test_identical_invalid_retry_is_flagged_and_still_stops(self):
        report, _ = self.run_decisions(
            [
                {"tool": "record", "args": {"record_id": "WO-02"}},
                self.extract("attempted"),
                self.extract("attempted"),
            ]
        )
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["trace"][1]["repeated_invalid_decision"])
        self.assertTrue(report["trace"][2]["repeated_invalid_decision"])
        self.assertEqual(report["extraction_proposals"], [])

    def test_clause_local_status_negation(self):

        cases = [
            ("Tried to tighten VLV-82; work could not be completed", "attempted", True),
            (
                "Tried to tighten VLV-82; work could not be completed",
                "completed",
                False,
            ),
            ("Did not attempt to tighten VLV-82", "attempted", False),
            ("Never tried to tighten VLV-82", "attempted", False),
            ("Did not replace PMP-55", "completed", False),
            ("Replaced FAN-93; repair success not confirmed", "completed", True),
            ("Replaced FAN-93; repair success not confirmed", "verified", False),
            ("Replacement of FLT-64 verified by inspection", "verified", True),
        ]
        for text, status, expected in cases:
            with self.subTest(text=text, status=status):
                self.assertEqual(has_unnegated_status_cue(text, status), expected)

    def test_empty_finish_progress_requires_history_aggregate(self):
        report, contexts = self.run_decisions(
            [
                {"tool": "search", "args": {"query": "xyznotfound"}},
                {"tool": "aggregate", "args": {}},
                {"tool": "finish", "args": {"record_ids": []}},
            ]
        )
        self.assertFalse(contexts[1]["workflow_progress"]["empty_finish_eligible"])
        self.assertTrue(contexts[2]["workflow_progress"]["empty_finish_eligible"])
        self.assertEqual(report["status"], "no_matches")

    def test_progress_tracks_inspection_and_extraction(self):
        report, contexts = self.run_decisions(
            [
                {"tool": "search", "args": {"query": "vibration"}},
                {"tool": "record", "args": {"record_id": "WO-02"}},
                self.extract("completed"),
                {"tool": "abstain", "args": {"reason": "Regression fixture"}},
            ]
        )
        self.assertIn(
            "WO-02",
            contexts[1]["workflow_progress"]["pending_candidate_inspection"],
        )
        self.assertNotIn(
            "WO-02",
            contexts[2]["workflow_progress"]["pending_candidate_inspection"],
        )
        self.assertIn(
            "WO-02",
            contexts[2]["workflow_progress"]["pending_candidate_extraction"],
        )
        self.assertNotIn(
            "WO-02",
            contexts[3]["workflow_progress"]["pending_candidate_extraction"],
        )
        self.assertEqual(report["status"], "abstained")
