"""Regressions for source cues, stage restrictions, and resolved history."""

import importlib.util
import json
import unittest
from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from maintlog.agent import run_agent
from maintlog.backends import BackendError, LocalServer, Replay
from maintlog.domain import Evidence, Record
from maintlog.extraction import has_unnegated_status_cue, resolve_span, validate_fields
from maintlog.tasks import TaskSpec
from maintlog.working_context import compact_context


def record(rid="R1", extra=""):
    return Record(
        rid,
        date(2024, 1, 1),
        "A1",
        "",
        "",
        "",
        "",
        "",
        Evidence("test.csv", "0" * 64, 2, "synthetic", {}),
        "Connector loose. RESECURED CONNECTOR." + extra,
    )


def extract(rid="R1", status="completed"):
    return {
        "tool": "extract",
        "args": {
            "record_id": rid,
            "fields": {
                "component": {"field": "narrative_raw", "quote": "CONNECTOR"},
                "problem": {"field": "narrative_raw", "quote": "Connector loose"},
                "action": {"field": "narrative_raw", "quote": "RESECURED CONNECTOR"},
            },
            "action_status": status,
        },
    }


class ReliabilityTests(unittest.TestCase):
    def test_explicit_work_and_negation(self):
        for text, expected in (
            ("RESECURED CONNECTOR", True),
            ("PERFORMED TEST", True),
            ("Connector was not resecured", False),
            ("Test was not performed", False),
            ("Never performed a test", False),
            ("Without having resecured the connector", False),
        ):
            with self.subTest(text=text):
                self.assertEqual(has_unnegated_status_cue(text, "completed"), expected)
        validate_fields(record(), extract()["args"]["fields"], "completed")

    def test_work_does_not_establish_verification_or_attempt(self):
        for status in ("verified", "attempted"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                validate_fields(record(), extract()["args"]["fields"], status)

    def test_future_work_cannot_establish_completion(self):
        source = record(extra=" Test will be performed tomorrow")
        fields = {
            "component": None,
            "problem": None,
            "action": {
                "field": "narrative_raw",
                "quote": "Test will be performed tomorrow",
            },
        }
        with self.assertRaises(ValueError):
            validate_fields(source, fields, "completed")

    def test_found_is_not_a_component_name(self):
        source = record(extra=" FOUND SENSOR LOOSE")
        with self.assertRaisesRegex(ValueError, "action phrase"):
            resolve_span(
                source, {"field": "narrative_raw", "quote": "FOUND SENSOR"}, "component"
            )

    def context(self):
        return {
            "observations": [
                {
                    "tool": "record",
                    "result": {"record_id": "R1", "narrative_raw": "long source"},
                },
                {
                    "tool": "extract",
                    "result": {
                        "error": "bad status",
                        "rejected_decision": extract(status="verified"),
                    },
                },
                {
                    "tool": "extract",
                    "result": {
                        "record_id": "R1",
                        "accepted_proposal": extract()["args"],
                    },
                },
                {
                    "tool": "record",
                    "result": {"record_id": "R2", "narrative_raw": "unresolved"},
                },
            ]
        }

    def test_compaction_preserves_audit_and_accepted_evidence(self):
        source = self.context()
        before = deepcopy(source)
        compact = compact_context(source)
        self.assertEqual(source, before)
        self.assertEqual(len(compact["observations"]), 3)
        self.assertNotIn("narrative_raw", compact["observations"][0]["result"])
        self.assertEqual(compact["observations"][1], source["observations"][2])
        self.assertEqual(compact["observations"][-1], source["observations"][-1])

    def test_unresolved_evidence_is_not_removed(self):
        source = self.context()
        source["observations"].pop(2)
        self.assertEqual(
            compact_context(source)["observations"], source["observations"]
        )

    def response(self, decision):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"choices": [{"message": {"content": json.dumps(decision)}}]}
            ),
        )

    def test_stage_schema_excludes_extract_and_is_checked_locally(self):
        context = {"allowed_tools": ["record", "finish"]}
        with patch(
            "maintlog.backends.subprocess.run",
            return_value=self.response({"tool": "record", "args": {"record_id": "R1"}}),
        ) as request:
            LocalServer().decide("Select", context, 10)
        body = json.loads(request.call_args.kwargs["input"])["body"]
        names = [
            branch["properties"]["tool"]["enum"][0]
            for branch in body["response_format"]["schema"]["anyOf"]
        ]
        self.assertEqual(names, ["record", "finish"])
        with patch(
            "maintlog.backends.subprocess.run", return_value=self.response(extract())
        ):
            with self.assertRaisesRegex(BackendError, "stage schema"):
                LocalServer().decide("Select", context, 10)

    def test_focused_extraction_rejects_wrong_record(self):
        with patch(
            "maintlog.backends.subprocess.run",
            return_value=self.response(extract("R2")),
        ):
            with self.assertRaises(BackendError):
                LocalServer(component_selection=False).decide(
                    "Extract",
                    {
                        "extraction_record": {
                            "record_id": "R1",
                            "narrative_raw": record().narrative_raw,
                        }
                    },
                    10,
                )


@unittest.skipUnless(importlib.util.find_spec("langgraph"), "LangGraph required")
class GraphReliabilityTests(unittest.TestCase):
    def test_history_finishes_without_losing_full_trace(self):
        extra = " Background information." * 85
        decisions = [
            {"tool": "search", "args": {"query": "Connector"}},
            {"tool": "record", "args": {"record_id": "R1"}},
            extract("R1", "verified"),
            extract("R1"),
            {"tool": "record", "args": {"record_id": "R2"}},
            extract("R2"),
            {"tool": "aggregate", "args": {}},
            {"tool": "finish", "args": {"record_ids": ["R1", "R2"]}},
        ]
        report = run_agent(
            [record("R1", extra), record("R2", extra)],
            "Review history",
            Replay(decisions),
            task=TaskSpec(mode="history", initial_query="Connector"),
            max_steps=12,
        )
        self.assertEqual(report["status"], "ready_for_review")
        self.assertTrue(report["completion"]["requirements_met"])
        self.assertTrue(
            any(item.get("working_context_compacted") for item in report["trace"])
        )
        self.assertEqual(
            report["trace"][1]["tool_result"]["narrative_raw"],
            record(extra=extra).narrative_raw,
        )

    def test_inspection_guard_remains(self):
        report = run_agent([record()], "Review", Replay([extract(), extract()]))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["extraction_proposals"], [])
        self.assertIn("before extracting", report["trace"][0]["tool_error"])


if __name__ == "__main__":
    unittest.main()
