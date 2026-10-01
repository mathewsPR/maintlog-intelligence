"""Regressions from live tool-contract failures; no model quality claims."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from maintlog.backends import BackendError, LocalServer
from maintlog.decision_schema import DECISION_SCHEMA, validate_decision
from maintlog.extraction import resolve_span
from maintlog.ingestion import load_csv, load_profile

ROOT = Path(__file__).resolve().parents[1]


class DecisionSchemaTests(unittest.TestCase):
    def extract(self, span):
        return {
            "tool": "extract",
            "args": {
                "record_id": "WO-02",
                "fields": {"component": span, "problem": None, "action": None},
                "action_status": "unknown",
            },
        }

    def test_unique_quote_and_repeated_quote_offsets_supported(self):
        for span in (
            {"field": "narrative_raw", "quote": "BRG-204"},
            {"field": "narrative_raw", "start": 9, "end": 16},
            None,
        ):
            self.assertEqual(validate_decision(self.extract(span)), self.extract(span))

    def test_rejects_output_metadata_and_mixed_span_modes(self):
        for extra in (
            {"source_column": "Technician Notes"},
            {"start": 9, "end": 17},
            {"span": "narrative_raw"},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_decision(
                    self.extract(
                        {"field": "narrative_raw", "quote": "BRG-204", **extra}
                    )
                )

    def test_rejects_missing_status_and_aggregate_arguments(self):
        value = self.extract(None)
        del value["args"]["action_status"]
        for decision in (
            value,
            {"tool": "aggregate", "args": {"query": "bearing"}},
            {"tool": "shell", "args": {}},
            {"tool": "search", "args": {"query": "bearing", "top_k": True}},
        ):
            with self.subTest(decision=decision), self.assertRaises(ValueError):
                validate_decision(decision)

    def test_backend_sends_schema_and_rejects_server_violation(self):
        response = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"tool": "aggregate", "args": {"query": "bad"}}
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
            with self.assertRaises(BackendError):
                LocalServer().decide("instructions", {}, 5)
        payload = json.loads(request.call_args.kwargs["input"])
        self.assertEqual(
            payload["body"]["response_format"],
            {"type": "json_object", "schema": DECISION_SCHEMA},
        )

    def test_live_offset_error_and_metadata_error_explain_recovery(self):
        record = load_csv(
            ROOT / "data/demo/company_export.csv",
            data_kind="synthetic",
            columns=load_profile(ROOT / "data/demo/company_profile.json"),
        )[1]
        with self.assertRaisesRegex(ValueError, "remove offsets"):
            resolve_span(
                record,
                {"field": "narrative_raw", "quote": "BRG-204", "start": 9, "end": 17},
                "component",
            )
        with self.assertRaisesRegex(ValueError, "do not send source_column"):
            resolve_span(
                record,
                {
                    "field": "narrative_raw",
                    "quote": "BRG-204",
                    "source_column": "Technician Notes",
                },
                "component",
            )

    def test_completed_work_keeps_unsuccessful_outcome_in_source(self):
        from maintlog.extraction import validate_fields

        record = load_csv(
            ROOT / "data/demo/company_export.csv",
            data_kind="synthetic",
            columns=load_profile(ROOT / "data/demo/company_profile.json"),
        )[1]
        fields = {
            "component": {"field": "narrative_raw", "quote": "BRG-204"},
            "problem": {
                "field": "narrative_raw",
                "quote": "Vibration still high; no successful repair confirmed",
            },
            "action": {"field": "narrative_raw", "quote": "Replaced BRG-204"},
        }
        resolved = validate_fields(record, fields, "completed")
        self.assertIn("no successful repair confirmed", resolved["problem"]["quote"])
        self.assertEqual(resolved["action"]["quote"], "Replaced BRG-204")

    def test_model_observations_exclude_computed_span_metadata(self):
        from maintlog.agent import run_agent
        from maintlog.backends import Replay
        from maintlog.scope import Scope

        records = load_csv(
            ROOT / "data/demo/company_export.csv",
            data_kind="synthetic",
            columns=load_profile(ROOT / "data/demo/company_profile.json"),
        )
        decisions = [
            {"tool": "record", "args": {"record_id": "WO-01"}},
            {
                "tool": "extract",
                "args": {
                    "record_id": "WO-01",
                    "fields": {
                        "component": {"field": "narrative_raw", "quote": "BRG-204"},
                        "problem": None,
                        "action": None,
                    },
                    "action_status": "unknown",
                },
            },
            {"tool": "abstain", "args": {"reason": "Regression fixture"}},
        ]
        backend = Replay(decisions)
        contexts = []
        original = backend.decide

        def capture(system, context, timeout):
            contexts.append(json.loads(json.dumps(context)))
            return original(system, context, timeout)

        backend.decide = capture
        report = run_agent(records, "Review", backend, scope=Scope(asset_id="PUMP-001"))
        observation = contexts[2]["observations"][-1]
        self.assertNotIn("source_column", json.dumps(observation))
        self.assertNotIn('"start"', json.dumps(observation))
        self.assertIn(
            "source_column", report["extraction_proposals"][0]["fields"]["component"]
        )
