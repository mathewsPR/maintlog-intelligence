"""Bound repeated reads without selecting relevance on the model's behalf."""

import json
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from maintlog.agent import run_agent
from maintlog.backends import BackendError, LocalServer, Replay
from maintlog.decision_schema import ARGS
from maintlog.domain import Evidence, Record
from maintlog.extraction import validate_fields
from maintlog.tasks import TaskSpec


def source():
    return Record(
        record_id="R1",
        event_date=date(2024, 1, 1),
        asset_id="A1",
        component="",
        issue_raw="",
        action_raw="",
        issue_normalized="",
        action_normalized="",
        narrative_raw="BOOT HAS CRACK",
        evidence=Evidence("test.csv", "0" * 64, 2, "synthetic", {}),
    )


def read():
    return {"tool": "record", "args": {"record_id": "R1"}}


def decisions():
    return [
        {"tool": "search", "args": {"query": "BOOT"}},
        {"tool": "aggregate", "args": {}},
        read(),
        {
            "tool": "extract",
            "args": {
                "record_id": "R1",
                "fields": {
                    "component": None,
                    "problem": {"field": "narrative_raw", "quote": "BOOT HAS CRACK"},
                    "action": None,
                },
                "action_status": "unknown",
            },
        },
        read(),
    ]


class ProgressGuardTests(unittest.TestCase):
    def test_exhausted_candidate_does_not_offer_unretrieved_scoped_records(self):
        other = replace(source(), record_id="R2", narrative_raw="HYDRAULIC VALVE LEAK")
        backend = Replay(
            decisions() + [{"tool": "finish", "args": {"record_ids": ["R1"]}}]
        )
        contexts = []
        original = backend.decide

        def capture(system, context, timeout):
            contexts.append(deepcopy(context))
            return original(system, context, timeout)

        backend.decide = capture
        report = run_agent(
            [source(), other],
            "Review BOOT",
            backend,
            task=TaskSpec(mode="history", initial_query="BOOT"),
        )
        self.assertEqual(report["status"], "ready_for_review")
        self.assertEqual(contexts[1]["record_available_ids"], ["R1"])
        self.assertNotIn("record", contexts[-1]["allowed_tools"])
        self.assertNotIn("record_available_ids", contexts[-1])

    def test_refined_search_can_unlock_another_scoped_record(self):
        other = replace(source(), record_id="R2", narrative_raw="HYDRAULIC VALVE LEAK")
        backend = Replay(
            decisions()
            + [
                {"tool": "search", "args": {"query": "VALVE"}},
                {"tool": "record", "args": {"record_id": "R2"}},
                {
                    "tool": "extract",
                    "args": {
                        "record_id": "R2",
                        "fields": {
                            "component": None,
                            "problem": {
                                "field": "narrative_raw",
                                "quote": "HYDRAULIC VALVE LEAK",
                            },
                            "action": None,
                        },
                        "action_status": "unknown",
                    },
                },
                {"tool": "finish", "args": {"record_ids": ["R2"]}},
            ]
        )
        contexts = []
        original = backend.decide

        def capture(system, context, timeout):
            contexts.append(deepcopy(context))
            return original(system, context, timeout)

        backend.decide = capture
        report = run_agent(
            [source(), other],
            "Review BOOT and VALVE",
            backend,
            max_steps=12,
            task=TaskSpec(mode="history", initial_query="BOOT"),
        )
        self.assertEqual(report["status"], "ready_for_review")
        self.assertEqual(contexts[6]["record_available_ids"], ["R2"])
        self.assertEqual([r["record_id"] for r in report["records_for_review"]], ["R2"])

    def test_replay_cannot_bypass_retrieval_selection_policy(self):
        other = replace(source(), record_id="R2", narrative_raw="HYDRAULIC VALVE LEAK")
        invalid = {"tool": "record", "args": {"record_id": "R2"}}
        report = run_agent(
            [source(), other],
            "Review BOOT",
            Replay(
                [
                    {"tool": "search", "args": {"query": "BOOT"}},
                    invalid,
                    invalid,
                ]
            ),
            task=TaskSpec(mode="history", initial_query="BOOT"),
        )
        self.assertEqual(report["status"], "failed")
        self.assertIn("refine search first", report["trace"][-1]["tool_error"])
        self.assertEqual(report["extraction_proposals"], [])

    def test_one_reread_then_model_selects_finish(self):
        backend = Replay(
            decisions() + [{"tool": "finish", "args": {"record_ids": ["R1"]}}]
        )
        contexts = []
        original = backend.decide

        def capture(system, context, timeout):
            contexts.append(deepcopy(context))
            return original(system, context, timeout)

        backend.decide = capture
        report = run_agent(
            [source()],
            "Review BOOT",
            backend,
            task=TaskSpec(mode="history", initial_query="BOOT"),
        )
        self.assertEqual(report["status"], "ready_for_review")
        self.assertNotIn("record", contexts[-1]["allowed_tools"])
        self.assertEqual(
            contexts[-1]["record_read_policy"]["blocked_record_ids"], ["R1"]
        )
        self.assertEqual(report["extraction_proposals"][0]["fields"]["action"], None)
        self.assertEqual(report["limits"]["max_reads_per_record"], 2)

    def test_backend_cannot_bypass_read_limit(self):
        report = run_agent(
            [source()],
            "Review BOOT",
            Replay(decisions() + [read(), read()]),
            task=TaskSpec(mode="history", initial_query="BOOT"),
        )
        self.assertEqual(report["status"], "failed")
        reads = [
            x
            for x in report["trace"]
            if x["decision"]["tool"] == "record" and "tool_error" not in x
        ]
        self.assertEqual(len(reads), 2)
        self.assertIn("record read limit", report["trace"][-1]["tool_error"])

    def test_transport_schema_restricts_available_ids(self):
        original_args = deepcopy(ARGS)
        response = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"tool": "record", "args": {"record_id": "R2"}}
                                )
                            }
                        }
                    ]
                }
            ),
        )
        with patch(
            "maintlog.backends.subprocess.run", return_value=response
        ) as request:
            LocalServer().decide(
                "Choose",
                {"allowed_tools": ["record", "finish"], "record_available_ids": ["R2"]},
                10,
            )
        body = json.loads(request.call_args.kwargs["input"])["body"]
        schema = body["response_format"]["schema"]["anyOf"][0]
        self.assertEqual(
            schema["properties"]["args"]["properties"]["record_id"]["enum"], ["R2"]
        )
        self.assertEqual(ARGS, original_args)
        response.stdout = response.stdout.replace("R2", "R1")
        with (
            patch("maintlog.backends.subprocess.run", return_value=response),
            self.assertRaises(BackendError),
        ):
            LocalServer().decide(
                "Choose",
                {"allowed_tools": ["record"], "record_available_ids": ["R2"]},
                10,
            )

    def test_new_completed_verbs_preserve_negative_and_future_constraints(self):
        for verb in (
            "ACCOMPLISHED",
            "RESEATED",
            "REPOSITIONED",
            "SERVICED",
            "CLEANED",
            "REINSTALLED",
            "SECURED",
            "ADJUSTED",
            "TIGHTENED",
            "REPACKED",
        ):
            for text, accepted in (
                (f"{verb} CONNECTOR", True),
                (f"CONNECTOR WAS NOT {verb}", False),
                (f"CONNECTOR WILL BE {verb}", False),
            ):
                with self.subTest(text=text):
                    rec = replace(source(), narrative_raw=text)
                    fields = {
                        "component": None,
                        "problem": None,
                        "action": {"field": "narrative_raw", "quote": text},
                    }
                    if accepted:
                        validate_fields(rec, fields, "completed")
                        for status in ("attempted", "verified"):
                            with self.assertRaises(ValueError):
                                validate_fields(rec, fields, status)
                    else:
                        with self.assertRaises(ValueError):
                            validate_fields(rec, fields, "completed")


if __name__ == "__main__":
    unittest.main()
