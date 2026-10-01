"""test_revisions    Regression tests for review completion, corrections and comparison oracles."""

import csv
import importlib.util
import json
import sqlite3
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from maintlog.agent import run_agent
from maintlog.backends import BackendError, LocalServer, Replay
from maintlog.cli import main as cli
from maintlog.comparison import FixedWorkflow, compare, score_case
from maintlog.evaluation import NormDocument, Unit
from maintlog.extraction import validate_fields
from maintlog.ingestion import load_csv
from maintlog.normalization import normalize_nouns
from maintlog.review import run_hash, save_decisions
from maintlog.review_store import reviewed_brief
from maintlog.tasks import TaskSpec
from maintlog.vocabulary import fit_lexicon, predict

ROOT = Path(__file__).resolve().parents[1]
HAS_GRAPH = importlib.util.find_spec("langgraph") is not None


def d(tool, **args):
    return {"tool": tool, "args": args}


@unittest.skipUnless(HAS_GRAPH, "install .[agent]")
class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.records = load_csv(
            ROOT / "data/demo/pump_records.csv", data_kind="synthetic"
        )

    def run_fixture(self, decisions, mode="history", **kwargs):
        return run_agent(
            self.records,
            "Review history",
            Replay(decisions),
            task=TaskSpec(mode),
            **kwargs,
        )

    def test_old_empty_finish_is_rejected(self):
        r = self.run_fixture([d("finish", record_ids=[])])
        self.assertNotEqual(r["status"], "ready_for_review")
        self.assertFalse(r["completion"]["requirements_met"])
        self.assertIn("perform a search", r["trace"][0]["tool_error"])

    def test_search_hits_must_be_inspected(self):
        r = self.run_fixture(
            [
                d("search", query="seal"),
                d("aggregate"),
                d("finish", record_ids=["DEMO-004"]),
            ]
        )
        self.assertNotEqual(r["status"], "ready_for_review")
        self.assertIn("inspect DEMO-004", r["trace"][-2]["tool_error"])

    def test_history_requires_aggregate(self):
        r = self.run_fixture(
            [
                d("search", query="seal"),
                d("record", record_id="DEMO-004"),
                d("finish", record_ids=["DEMO-004"]),
            ]
        )
        self.assertFalse(r["completion"]["requirements_met"])
        self.assertIn("full-scope aggregate", r["trace"][-2]["tool_error"])

    def test_empty_after_nonempty_search_cannot_claim_no_matches(self):
        r = self.run_fixture(
            [d("search", query="seal"), d("aggregate"), d("finish", record_ids=[])]
        )
        self.assertNotEqual(r["status"], "no_matches")

    def test_no_match_is_separate_from_ready_review(self):
        r = self.run_fixture(
            [
                d("search", query="xyznotfound"),
                d("aggregate"),
                d("finish", record_ids=[]),
            ]
        )
        self.assertEqual(r["status"], "no_matches")
        self.assertTrue(r["completion"]["requirements_met"])
        self.assertIsNone(r["completion"]["semantic_task_success"])

    def test_abstention_does_not_claim_completion(self):
        r = self.run_fixture([d("abstain", reason="Cannot resolve equipment identity")])
        self.assertEqual(r["status"], "abstained")
        self.assertFalse(r["completion"]["requirements_met"])

    def test_wrong_component_from_action_column_is_rejected(self):
        row = next(r for r in self.records if r.record_id == "DEMO-005")
        with self.assertRaisesRegex(ValueError, "source field"):
            validate_fields(
                row,
                {
                    "component": {"field": "action_raw", "quote": "repl seal"},
                    "problem": None,
                    "action": None,
                },
                "unknown",
            )

    def test_unsupported_verified_status_is_rejected(self):
        row = next(r for r in self.records if r.record_id == "DEMO-003")
        with self.assertRaisesRegex(ValueError, "explicit support"):
            validate_fields(
                row,
                {
                    "component": None,
                    "problem": None,
                    "action": {"field": "action_raw", "quote": "repl BRG-204"},
                },
                "verified",
            )

    def test_negative_problem_excerpt_cannot_drop_no(self):
        row = next(r for r in self.records if r.record_id == "DEMO-012")
        with self.assertRaisesRegex(ValueError, "negation"):
            validate_fields(
                row,
                {
                    "component": None,
                    "problem": {"field": "issue_raw", "quote": "seal leak"},
                    "action": None,
                },
                "unknown",
            )
        fields = validate_fields(
            row,
            {
                "component": None,
                "problem": {"field": "issue_raw", "quote": "no seal leak observed"},
                "action": None,
            },
            "unknown",
        )
        self.assertEqual(fields["problem"]["quote"], "no seal leak observed")

    def test_replay_has_zero_actual_model_calls(self):
        r = self.run_fixture(
            [d("record", record_id="DEMO-003"), d("finish", record_ids=["DEMO-003"])],
            mode="inspect",
        )
        self.assertEqual(r["model_calls"], 0)
        self.assertEqual(r["status"], "ready_for_review")


@unittest.skipUnless(HAS_GRAPH, "install .[agent]")
class ReviewReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source.csv"
        with self.path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "date", "asset", "notes"])
            writer.writerows(
                [
                    ["A", "2026-01-01", "P1", "seal leak. Plan to replace seal."],
                    ["B", "2026-01-02", "P1", "seal leak. Replaced seal."],
                ]
            )
        self.columns = {
            "record_id": "id",
            "event_date": "date",
            "asset_id": "asset",
            "narrative": "notes",
        }
        self.records = load_csv(self.path, data_kind="synthetic", columns=self.columns)
        script = []
        for record, status in zip(self.records, ["planned", "completed"]):
            script += [
                d("record", record_id=record.record_id),
                d(
                    "extract",
                    record_id=record.record_id,
                    fields={
                        "component": {"field": "narrative_raw", "start": 0, "end": 4},
                        "problem": {"field": "narrative_raw", "quote": "leak"},
                        "action": {
                            "field": "narrative_raw",
                            "quote": record.narrative_raw[11:],
                        },
                    },
                    action_status=status,
                ),
            ]
        script += [d("finish", record_ids=["A", "B"])]
        self.report = run_agent(
            self.records,
            "Extract reported fields",
            Replay(script),
            task=TaskSpec("extract"),
        )
        self.assertEqual(self.report["status"], "ready_for_review")
        self.db = Path(self.temp.name) / "reviews.sqlite3"
        self.decisions = {
            "run_sha256": run_hash(self.report),
            "reviewer": "Engineer",
            "decisions": [
                {
                    "record_id": rid,
                    "decision": "accepted",
                    "note": "Corrected problem quote",
                    "fields": {
                        "component": {"decision": "accepted"},
                        "problem": {
                            "decision": "corrected",
                            "span": {"field": "narrative_raw", "start": 0, "end": 9},
                        },
                        "action": {"decision": "accepted"},
                    },
                    "action_status": {"decision": "accepted", "value": status},
                }
                for rid, status in [("A", "planned"), ("B", "completed")]
            ],
        }

    def test_review_connections_close_before_return(self):
        connect = sqlite3.connect
        connections = []

        def tracked_connect(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connections.append(connection)
            return connection

        with patch("sqlite3.connect", side_effect=tracked_connect):
            save_decisions(self.report, self.decisions, self.db)
            reviewed_brief(self.records, self.db, run_hash(self.report))
        self.assertEqual(len(connections), 2)
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_corrected_fields_feed_source_linked_brief(self):
        original = self.path.read_bytes()
        save_decisions(self.report, self.decisions, self.db)
        r = reviewed_brief(self.records, self.db, run_hash(self.report))
        self.assertEqual(r["eligible_reviewed_record_count"], 2)
        self.assertEqual(r["recurring_groups"][0]["record_count"], 2)
        self.assertEqual(r["recurring_groups"][0]["normalized_issue_key"], "seal leak")
        review = r["recurring_groups"][0]["evidence"][0]["field_review"]
        self.assertEqual(review["reviewer"], "Engineer")
        self.assertEqual(review["fields"]["problem"]["quote"], "seal leak")
        self.assertEqual(self.path.read_bytes(), original)

    def test_reviewed_brief_cli_accepts_original_report_reference(self):
        save_decisions(self.report, self.decisions, self.db)
        report_path = Path(self.temp.name) / "run.json"
        report_path.write_text(json.dumps(self.report, default=str))
        profile = Path(self.temp.name) / "profile.json"
        profile.write_text(json.dumps({"columns": self.columns}))
        output = Path(self.temp.name) / "brief.json"
        code = cli(
            [
                "reviewed-brief",
                str(self.path),
                "--data-kind",
                "synthetic",
                "--profile",
                str(profile),
                "--database",
                str(self.db),
                "--review-report",
                str(report_path),
                "--output",
                str(output),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(output.read_text())["eligible_reviewed_record_count"], 2
        )

    def test_record_acceptance_alone_never_promotes_fields(self):
        rows = [
            {k: v for k, v in row.items() if k in {"record_id", "decision", "note"}}
            for row in self.decisions["decisions"]
        ]
        save_decisions(self.report, {**self.decisions, "decisions": rows}, self.db)
        r = reviewed_brief(self.records, self.db, run_hash(self.report))
        self.assertEqual(r["eligible_reviewed_record_count"], 0)
        self.assertEqual(r["unreviewed_or_rejected_record_count"], 2)

    def test_latest_rejection_invalidates_old_acceptance(self):
        save_decisions(self.report, self.decisions, self.db)
        save_decisions(
            self.report,
            {
                **self.decisions,
                "decisions": [
                    {"record_id": "A", "decision": "rejected", "note": "Withdrawn"}
                ],
            },
            self.db,
        )
        r = reviewed_brief(self.records, self.db, run_hash(self.report))
        self.assertEqual(r["eligible_reviewed_record_count"], 1)
        self.assertEqual(r["recurring_groups"], [])

    def test_partial_field_review_cannot_be_reused(self):
        self.decisions["decisions"][0]["fields"].pop("action")
        save_decisions(self.report, self.decisions, self.db)
        r = reviewed_brief(self.records, self.db, run_hash(self.report))
        self.assertEqual(r["eligible_reviewed_record_count"], 1)

    def test_changed_source_rejects_reuse(self):
        save_decisions(self.report, self.decisions, self.db)
        self.path.write_text(
            self.path.read_text().replace("Plan to replace", "Will replace")
        )
        changed = load_csv(self.path, data_kind="synthetic", columns=self.columns)
        with self.assertRaisesRegex(ValueError, "differs"):
            reviewed_brief(changed, self.db, run_hash(self.report))

    def test_invalid_correction_fails_before_database_write(self):
        self.decisions["decisions"][0]["fields"]["problem"]["span"] = {
            "field": "narrative_raw",
            "quote": "invented root cause",
        }
        with self.assertRaises(ValueError):
            save_decisions(self.report, self.decisions, self.db)
        self.assertFalse(self.db.exists())

    def test_component_action_phrase_rejected_in_narrative(self):
        self.decisions["decisions"][0]["fields"]["component"] = {
            "decision": "corrected",
            "span": {"field": "narrative_raw", "quote": "Plan to replace seal."},
        }
        # Source support alone is insufficient: an explicit performed-action
        # prefix is rejected, while general semantics still need human review.
        fields = {
            "component": {"field": "narrative_raw", "quote": "Replaced seal."},
            "problem": None,
            "action": None,
        }
        with self.assertRaisesRegex(ValueError, "action phrase"):
            validate_fields(self.records[1], fields, "unknown")

    def test_planned_quote_cannot_establish_completed_status(self):
        with self.assertRaisesRegex(ValueError, "support|planned"):
            validate_fields(
                self.records[0],
                {
                    "component": None,
                    "problem": None,
                    "action": {
                        "field": "narrative_raw",
                        "quote": "Plan to replace seal.",
                    },
                },
                "completed",
            )

    def test_unsupported_action_unknown_after_human_review(self):
        self.decisions["decisions"][0]["fields"]["action"] = {"decision": "rejected"}
        with self.assertRaisesRegex(ValueError, "unknown status"):
            save_decisions(self.report, self.decisions, self.db)


@unittest.skipUnless(HAS_GRAPH, "install .[agent]")
class ComparisonTests(unittest.TestCase):
    def test_all_three_workflows_share_source_scope_and_oracle(self):
        result = compare(
            ROOT / "data/demo/comparison_cases.json", backend="replay", trials=2
        )
        self.assertEqual(len(result["results"]), 18)
        self.assertEqual(result["evidence_kind"], "synthetic_replay_mechanics")
        for row in result["results"]:
            with self.subTest(
                case_id=row["case_id"],
                workflow=row["workflow"],
            ):
                self.assertEqual(
                    row["metrics"]["record_recall"],
                    1,
                    msg=json.dumps(row, indent=2, default=str),
                )
        bearing = [r for r in result["results"] if r["case_id"] == "bearing-actions"]
        self.assertTrue(
            all(
                r["metrics"]["labeled_task_success"]
                for r in bearing
                if r["workflow"] != "deterministic"
            )
        )
        self.assertTrue(
            all(
                not r["metrics"]["labeled_task_success"]
                for r in bearing
                if r["workflow"] == "deterministic"
            )
        )

    def test_oracle_rejects_completed_but_wrong_result(self):
        report = {
            "records_for_review": [],
            "extraction_proposals": [],
            "status": "ready_for_review",
            "trace": [],
            "elapsed_seconds": 0,
            "completion": {"requirements_met": True},
        }
        score = score_case(report, {"relevant_record_ids": ["MISSING"]})
        self.assertFalse(score["labeled_task_success"])
        self.assertTrue(score["workflow_complete"])

    def test_oracle_rejects_wrong_aggregate_count(self):
        report = {
            "records_for_review": [],
            "extraction_proposals": [],
            "status": "no_matches",
            "trace": [],
            "elapsed_seconds": 0,
            "aggregate": {"selected_record_count": 4, "recurring_groups": []},
        }
        case = {
            "relevant_record_ids": [],
            "expected_aggregate_groups": [],
            "expected_selected_count": 3,
        }
        score = score_case(report, case)
        self.assertFalse(score["aggregate_correct"])
        self.assertFalse(score["labeled_task_success"])

    def test_fixed_model_context_has_no_oracle_labels(self):
        captured = []

        class Spy:
            label = "spy-fixture"

            def decide(self, system, context, timeout):
                captured.append(context)
                return {
                    "decision": d(
                        "extract",
                        record_id="R",
                        fields={"component": None, "problem": None, "action": None},
                        action_status="unknown",
                    ),
                    "model_called": False,
                }

        chooser = FixedWorkflow(Spy(), "bearing", "history")
        context = {
            "question": "Review history",
            "task_requirements": TaskSpec().requirements(),
            "observations": [],
        }
        chooser.decide("", context, 1)
        context["observations"] = [
            {"tool": "search", "result": {"hits": [{"record_id": "R"}]}}
        ]
        chooser.decide("", context, 1)
        context["observations"].append(
            {
                "tool": "record",
                "result": {"record_id": "R", "narrative_raw": "bearing high"},
            }
        )
        chooser.decide("", context, 1)
        self.assertEqual(set(captured[0]), {"question", "task_requirements", "record"})


class RequestDeadlineTests(unittest.TestCase):
    def test_stalled_http_request_is_terminated(self):
        class Slow(BaseHTTPRequestHandler):
            def do_POST(self):
                time.sleep(0.3)
                try:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"{}")
                except (OSError, BrokenPipeError):
                    pass

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Slow)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            backend = LocalServer(f"http://127.0.0.1:{server.server_port}/v1")
            started = time.monotonic()
            with self.assertRaisesRegex(BackendError, "deadline"):
                backend.decide("rules", {}, 0.12)
            self.assertLess(time.monotonic() - started, 0.75)
            self.assertEqual(backend.request_count, 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class VocabularyTests(unittest.TestCase):
    def test_default_aliases_preserve_action_tense_and_identifiers(self):
        self.assertEqual(
            normalize_nouns("brg vib repl chk lub BRG-204"),
            "bearing vibration repl chk lub BRG-204",
        )

    def test_training_conflicts_and_masked_identifiers_are_excluded(self):
        docs = [
            NormDocument((Unit("Mech", "mechanical", 1), Unit("BRG-204", "<id>", 2)))
        ] * 5
        docs += [NormDocument((Unit("X", "one", 1),))] * 5 + [
            NormDocument((Unit("X", "two", 1),))
        ] * 5
        lexicon = fit_lexicon(docs)
        self.assertIn("mech", lexicon["entries"])
        self.assertNotIn("x", lexicon["entries"])
        self.assertEqual(
            predict("Mech BRG-204 unknown", lexicon), "mechanical BRG-204 unknown"
        )


if __name__ == "__main__":
    unittest.main()
