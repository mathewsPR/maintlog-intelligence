"""Real graph execution with replay decisions; no model-quality claims."""

import importlib.util
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from maintlog.agent import run_agent
from maintlog.backends import BackendError, LocalServer, Replay
from maintlog.cli import main
from maintlog.ingestion import DataError, load_csv, load_profile
from maintlog.review import render_html, run_hash, save_decisions
from maintlog.scope import Scope
from maintlog.tasks import TaskSpec

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data/demo/pump_records.csv"
EXPORT = ROOT / "data/demo/company_export.csv"
PROFILE = ROOT / "data/demo/company_profile.json"
HAS_GRAPH = importlib.util.find_spec("langgraph") is not None


def decision(tool, **args):
    return {"tool": tool, "args": args}


class ProfileAndFilterTests(unittest.TestCase):
    def test_company_narrative_preserved_with_unknown_fields(self):
        records = load_csv(EXPORT, data_kind="synthetic", columns=load_profile(PROFILE))
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].component, "")
        self.assertEqual(records[0].issue_raw, "")
        self.assertEqual(records[0].action_raw, "")
        self.assertIn("BRG-204", records[0].narrative_raw)
        self.assertEqual(records[0].evidence.columns["narrative"], "Technician Notes")

    def test_bad_profiles_rejected(self):
        mappings = [
            {"columns": {"record_id": "id"}},
            {
                "columns": {
                    "record_id": "id",
                    "event_date": "date",
                    "asset_id": "asset",
                    "narrative": "text",
                    "issue": "text2",
                }
            },
            {
                "columns": {
                    "record_id": "id",
                    "event_date": "date",
                    "asset_id": "asset",
                    "narrative": "text",
                    "action": "action",
                }
            },
            {
                "columns": {
                    "record_id": "id",
                    "event_date": "id",
                    "asset_id": "asset",
                    "narrative": "text",
                }
            },
            {
                "columns": {
                    "record_id": "id",
                    "event_date": "date",
                    "asset_id": "asset",
                    "narrative": "text",
                    "invent": "x",
                }
            },
            {
                "columns": {
                    "record_id": "id",
                    "event_date": "date",
                    "asset_id": "asset",
                    "narrative": 42,
                }
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"
            for mapping in mappings:
                with self.subTest(mapping=mapping):
                    path.write_text(json.dumps(mapping))
                    with self.assertRaises(DataError):
                        load_profile(path)

    def test_mapped_column_missing_and_duplicate_headers_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.csv"
            for content in [
                "Work Order,Date,Equipment\n1,2026-01-01,P1\n",
                "Work Order,Date,Equipment,Technician Notes,Date\n1,2026-01-01,P1,seal leak,2026-01-01\n",
            ]:
                path.write_text(content)
                with self.assertRaises(DataError):
                    load_csv(path, data_kind="synthetic", columns=load_profile(PROFILE))

    def call(self, command, *flags):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main([command, str(DEMO), "--data-kind", "synthetic", *flags])
        return code, json.loads(out.getvalue()) if out.getvalue() else None

    def test_search_honors_inclusive_dates(self):
        code, result = self.call(
            "search",
            "--query",
            "bearing vibration",
            "--asset-id",
            "PUMP-001",
            "--start",
            "2026-01-08",
            "--end",
            "2026-01-08",
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            [h["record"]["record_id"] for h in result["hits"]], ["DEMO-002"]
        )

    def test_brief_honors_asset(self):
        code, result = self.call("brief", "--asset-id", "PUMP-002")
        self.assertEqual(code, 0)
        self.assertEqual(result["selected_record_count"], 2)
        self.assertEqual(len(result["recurring_groups"]), 1)
        self.assertEqual(result["recurring_groups"][0]["asset_id"], "PUMP-002")

    def test_import_honors_scope(self):
        code, result = self.call(
            "import", "--asset-id", "PUMP-001", "--end", "2026-01-08"
        )
        self.assertEqual(code, 0)
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["input_record_count"], 12)

    def test_unsupported_flags_rejected(self):
        for command, flags in [
            ("brief", ["--query", "seal"]),
            ("search", ["--query", "seal", "--backend", "local"]),
            ("import", ["--html", "x.html"]),
        ]:
            with self.subTest(command=command):
                self.assertEqual(self.call(command, *flags)[0], 2)

    def test_reversed_dates_rejected_in_all_commands(self):
        for command in ["import", "search", "brief"]:
            flags = ["--start", "2026-02-01", "--end", "2026-01-01"]
            if command == "search":
                flags += ["--query", "seal"]
            self.assertEqual(self.call(command, *flags)[0], 2)


@unittest.skipUnless(HAS_GRAPH, "install .[agent] to test the actual graph")
class AgentTests(unittest.TestCase):
    def setUp(self):
        self.records = load_csv(DEMO, data_kind="synthetic")

    def run_fixture(self, decisions, **kwargs):
        kwargs.setdefault("task", TaskSpec("inspect"))
        return run_agent(self.records, "Review history", Replay(decisions), **kwargs)

    def test_aggregate_counts_full_scope_not_top_k(self):
        result = self.run_fixture(
            [
                decision("search", query="bearing vibration", top_k=1),
                decision("aggregate"),
                decision("record", record_id="DEMO-002"),
                decision("finish", record_ids=["DEMO-002"]),
            ],
            scope=Scope("PUMP-001"),
        )
        self.assertEqual(result["status"], "ready_for_review")
        self.assertEqual(result["selected_record_count"], 3)
        self.assertEqual(result["aggregate"]["recurring_groups"][0]["record_count"], 3)
        self.assertEqual(len(result["records_for_review"]), 1)
        self.assertEqual(result["backend"], "replay-fixture-no-model")

    def test_outside_scope_records_cannot_be_read_or_cited(self):
        result = self.run_fixture(
            [
                decision("record", record_id="DEMO-004"),
                decision("finish", record_ids=["DEMO-004"]),
            ],
            scope=Scope("PUMP-001"),
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["records_for_review"], [])
        self.assertEqual(result["selected_record_count"], 3)

    def test_missing_citation_is_rejected_then_recovery_allowed(self):
        result = self.run_fixture(
            [
                decision("finish", record_ids=["FAKE"]),
                decision("search", query="seal"),
                decision("record", record_id="DEMO-004"),
                decision("finish", record_ids=["DEMO-004"]),
            ]
        )
        self.assertEqual(result["status"], "ready_for_review")
        self.assertIn("tool_error", result["trace"][0])

    def test_budget_halts_tool_loop(self):
        result = self.run_fixture([decision("assets")] * 5, max_steps=2)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["steps"], 2)

    def test_context_limit_before_model_call(self):
        result = self.run_fixture([], max_context_chars=10)
        self.assertEqual(result["status"], "context_limit")
        self.assertEqual(result["steps"], 0)

    def test_invalid_decision_retries_are_bounded(self):
        result = self.run_fixture([{"tool": "finish", "args": {}, "invent": "x"}] * 3)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["steps"], 2)

    def test_unknown_tool_cannot_run_commands(self):
        result = self.run_fixture(
            [
                decision("shell", command="remove records"),
                decision("search", query="xyzunknown"),
                decision("finish", record_ids=[]),
            ]
        )
        self.assertEqual(result["status"], "no_matches")
        self.assertIn("unknown tool", result["trace"][0]["tool_error"])

    def test_clarification_pauses(self):
        result = self.run_fixture(
            [decision("clarify", question="Which exact asset ID?")]
        )
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["steps"], 1)

    def test_unsupported_action_status_rejected(self):
        result = self.run_fixture(
            [
                decision("record", record_id="DEMO-007"),
                decision(
                    "extract",
                    record_id="DEMO-007",
                    fields={"component": None, "problem": None, "action": None},
                    action_status="completed",
                ),
                decision("finish", record_ids=["DEMO-007"]),
            ]
        )
        self.assertEqual(result["extraction_proposals"], [])
        self.assertIn("unknown status", result["trace"][1]["tool_error"])

    def test_out_of_range_and_boolean_offsets_rejected(self):
        for start, end in [(0, 9999), (True, 3), (4, 1), (-1, 3)]:
            result = self.run_fixture(
                [
                    decision("record", record_id="DEMO-001"),
                    decision(
                        "extract",
                        record_id="DEMO-001",
                        fields={
                            "component": None,
                            "problem": {
                                "field": "issue_raw",
                                "start": start,
                                "end": end,
                            },
                            "action": None,
                        },
                        action_status="unknown",
                    ),
                    decision("finish", record_ids=["DEMO-001"]),
                ]
            )
            self.assertEqual(result["extraction_proposals"], [])

    def test_extract_requires_inspection(self):
        result = self.run_fixture(
            [
                decision(
                    "extract",
                    record_id="DEMO-001",
                    fields={"component": None, "problem": None, "action": None},
                    action_status="unknown",
                ),
                decision("finish", record_ids=[]),
            ]
        )
        self.assertIn("inspect", result["trace"][0]["tool_error"])

    def test_single_narrative_flow_and_unclassified_aggregate(self):
        records = load_csv(EXPORT, data_kind="synthetic", columns=load_profile(PROFILE))
        result = run_agent(
            records,
            "Review bearing vibration",
            Replay.from_file(ROOT / "data/demo/replay_narrative.json"),
            scope=Scope("PUMP-001"),
        )
        self.assertEqual(result["status"], "ready_for_review")
        proposal = result["extraction_proposals"][0]
        self.assertEqual(proposal["fields"]["component"]["quote"], "brg")
        self.assertEqual(
            proposal["fields"]["action"]["quote"], "Plan to replace BRG-204 next week."
        )
        self.assertEqual(proposal["review_status"], "unreviewed")
        self.assertEqual(result["aggregate"]["unstructured_record_count"], 2)
        self.assertEqual(result["aggregate"]["recurring_groups"], [])

    def test_unique_quotes_resolve_to_exact_offsets(self):
        result = self.run_fixture(
            [
                decision("record", record_id="DEMO-003"),
                decision(
                    "extract",
                    record_id="DEMO-003",
                    fields={
                        "component": None,
                        "problem": None,
                        "action": {"field": "action_raw", "quote": "BRG-204"},
                    },
                    action_status="unknown",
                ),
                decision("finish", record_ids=["DEMO-003"]),
            ]
        )
        span = result["extraction_proposals"][0]["fields"]["action"]
        self.assertEqual(span["quote"], "BRG-204")
        self.assertEqual(span["start"], 5)
        self.assertEqual(span["end"], 12)

    def test_repeated_or_absent_quotes_rejected(self):
        self.records[0] = replace(self.records[0], issue_raw="seal seal")
        for quote in ["seal", "made-up diagnosis"]:
            result = self.run_fixture(
                [
                    decision("record", record_id="DEMO-001"),
                    decision(
                        "extract",
                        record_id="DEMO-001",
                        fields={
                            "component": None,
                            "problem": {"field": "issue_raw", "quote": quote},
                            "action": None,
                        },
                        action_status="unknown",
                    ),
                    decision("finish", record_ids=["DEMO-001"]),
                ]
            )
            self.assertEqual(result["extraction_proposals"], [])
            self.assertIn("exactly once", result["trace"][1]["tool_error"])

    def test_late_model_reply_is_not_executed(self):
        clock = [0.0]

        class LateBackend:
            label = "late-test-fixture"

            def decide(self, system, context, timeout):
                clock[0] = 2.0
                return {"decision": decision("finish", record_ids=[])}

        with patch("maintlog.agent.time.monotonic", side_effect=lambda: clock[0]):
            result = run_agent(
                self.records, "Review history", LateBackend(), timeout_seconds=1
            )
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertNotIn("tool_result", result["trace"][0])

    def test_empty_scope_is_explicit(self):
        result = self.run_fixture(
            [decision("aggregate"), decision("finish", record_ids=[])],
            scope=Scope("MISSING"),
        )
        self.assertEqual(result["selected_record_count"], 0)
        self.assertEqual(result["status"], "no_records")
        self.assertEqual(result["steps"], 0)

    def test_tool_can_refine_search_dynamically(self):
        result = self.run_fixture(
            [
                decision("search", query="xyznotfound"),
                decision("search", query="seal leak"),
                decision("record", record_id="DEMO-004"),
                decision("finish", record_ids=["DEMO-004"]),
            ]
        )
        self.assertEqual(result["trace"][0]["tool_result"]["hits"], [])
        self.assertTrue(result["trace"][1]["tool_result"]["hits"])

    def test_replay_failure_has_nonzero_cli_exit_and_report(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "failed.json"
            code = main(
                [
                    "agent",
                    str(DEMO),
                    "--data-kind",
                    "synthetic",
                    "--question",
                    "Review history",
                    "--backend",
                    "replay",
                    "--replay",
                    str(ROOT / "data/demo/replay_structured.json"),
                    "--max-steps",
                    "1",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(code, 3)
            self.assertEqual(
                json.loads(output.read_text())["status"], "budget_exhausted"
            )

    def test_html_escapes_untrusted_source_and_question(self):
        source = '</script><img src=x onerror="alert(1)">'
        self.records[0] = replace(self.records[0], issue_raw=source)
        result = self.run_fixture(
            [
                decision("record", record_id="DEMO-001"),
                decision("finish", record_ids=["DEMO-001"]),
            ]
        )
        result["question"] = source
        page = render_html(result)
        self.assertNotIn(source, page)
        self.assertIn("&lt;/script&gt;", page)

    def test_review_hash_binds_to_exact_run_and_events_append(self):
        result = self.run_fixture(
            [
                decision("record", record_id="DEMO-001"),
                decision("finish", record_ids=["DEMO-001"]),
            ]
        )
        decisions = {
            "run_sha256": run_hash(result),
            "reviewer": "Engineer",
            "decisions": [
                {
                    "record_id": "DEMO-001",
                    "decision": "accepted",
                    "note": "Source checked",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "review.sqlite3"
            self.assertEqual(save_decisions(result, decisions, database), 1)
            decisions["decisions"][0]["decision"] = "rejected"
            save_decisions(result, decisions, database)
            with closing(sqlite3.connect(database)) as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 1
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM review_events").fetchone()[0], 2
                )
            changed = {**result, "question": "Another question"}
            with self.assertRaisesRegex(ValueError, "exact run"):
                save_decisions(changed, decisions, database)
            decisions["decisions"][0]["record_id"] = "FAKE"
            with self.assertRaises(ValueError):
                save_decisions(result, decisions, database)


class LocalTransportTests(unittest.TestCase):
    def test_nonlocal_and_credential_urls_rejected(self):
        for url in [
            "https://remote.example/v1",
            "http://remote.example/v1",
            "http://user:secret@localhost/v1",
            "http://127.0.0.1/v1?token=secret",
        ]:
            with self.assertRaises(BackendError):
                LocalServer(url)

    def test_http_adapter_json_usage_and_redirect_rejection(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            redirect = False

            def do_POST(self):
                received.append(
                    json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                )
                if self.redirect:
                    self.send_response(307)
                    self.send_header("Location", "http://remote.invalid/")
                    self.end_headers()
                    return
                body = json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        decision("finish", record_ids=[])
                                    )
                                }
                            }
                        ],
                        "usage": {"completion_tokens": 12},
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            backend = LocalServer(
                f"http://127.0.0.1:{server.server_port}/v1", model="fixture"
            )
            response = backend.decide("rules", {"question": "history"}, 2)
            self.assertEqual(response["decision"]["tool"], "finish")
            self.assertEqual(response["usage"]["completion_tokens"], 12)
            self.assertEqual(received[0]["max_tokens"], 512)
            self.assertEqual(received[0]["messages"][0]["role"], "system")
            Handler.redirect = True
            with self.assertRaises(BackendError):
                backend.decide("rules", {}, 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
