"""Regression checks for the synthetic replay CI gate, without a model."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_replay_report.py"
SPEC = importlib.util.spec_from_file_location("maintlog_replay_gate", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load replay gate")
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class ReplayGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.cases = root / "cases.json"
        self.report = root / "report.json"
        self.cases.write_text(
            json.dumps({"source": {"data_kind": "synthetic"}, "cases": [{"id": "a"}]}),
            encoding="utf-8",
        )
        self.payload = {
            "schema_version": 1,
            "backend": "replay",
            "evidence_kind": "synthetic_replay_mechanics",
            "data_kind": "synthetic",
            "cases_sha256": hashlib.sha256(self.cases.read_bytes()).hexdigest(),
            "trials": 1,
            "results": [
                {
                    "trial": 1,
                    "case_id": "a",
                    "workflow": workflow,
                    "metrics": {
                        "workflow_complete": True,
                        "exact_record_set": True,
                        "labeled_task_success": workflow != "deterministic",
                    },
                }
                for workflow in ("deterministic", "fixed", "agent")
            ],
        }

    def run_gate(self) -> int:
        self.report.write_text(json.dumps(self.payload), encoding="utf-8")
        argv = [str(SCRIPT), str(self.report), str(self.cases), "--trials", "1"]
        with patch("sys.argv", argv):
            return GATE.main()

    def test_passes_with_expected_baseline_extraction_limitation(self) -> None:
        self.assertEqual(self.run_gate(), 0)

    def test_rejects_missing_workflow_result(self) -> None:
        self.payload["results"].pop()
        with self.assertRaisesRegex(SystemExit, "missing"):
            self.run_gate()

    def test_rejects_duplicate_result(self) -> None:
        self.payload["results"].append(self.payload["results"][0])
        with self.assertRaisesRegex(SystemExit, "repeated"):
            self.run_gate()

    def test_rejects_agent_task_failure_after_operational_completion(self) -> None:
        self.payload["results"][2]["metrics"]["labeled_task_success"] = False
        with self.assertRaisesRegex(SystemExit, "regression"):
            self.run_gate()

    def test_rejects_changed_case_hash(self) -> None:
        self.payload["cases_sha256"] = "0" * 64
        with self.assertRaisesRegex(SystemExit, "configuration"):
            self.run_gate()
