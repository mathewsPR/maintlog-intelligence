"""Behavioral tests for the M0 data/evidence contract; Python 3.11 only."""

import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

from maintlog.brief import recurring_brief
from maintlog.cli import main
from maintlog.ingestion import FIELDS, DataError, load_csv
from maintlog.normalization import normalize
from maintlog.retrieval import search

if sys.version_info[:2] != (3, 11):
    raise RuntimeError("Run project tests with Python 3.11 only")

DEMO = Path(__file__).resolve().parents[1] / "data/demo/pump_records.csv"


class NormalizationTests(unittest.TestCase):
    def test_dictionary_expansion(self):
        self.assertEqual(normalize("BRG vib high"), "bearing vibration high")

    def test_identifiers_preserved(self):
        text = "BRG-204 TEMP_01 BRG204 BRG/204 PUMP-001"
        self.assertEqual(normalize(text), text)

    def test_unknown_terms_and_numbers_preserved(self):
        text = "NPSH 3.5 mm Müller XJ9"
        self.assertEqual(normalize(text), text)

    def test_negation_preserved(self):
        self.assertEqual(normalize("no brg vib"), "no bearing vibration")

    def test_idempotent(self):
        text = normalize("chk brg and repl BRG-204")
        self.assertEqual(normalize(text), text)


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "records.csv"

    def write_rows(self, rows):
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(FIELDS)
            writer.writerows(rows)

    def row(self, **changes):
        row = dict(zip(FIELDS, ["R-1", "2026-01-01", "P-1", "seal", "seal leak", ""]))
        row.update(changes)
        return [row[field] for field in FIELDS]

    def test_source_and_raw_text_preserved(self):
        self.write_rows([self.row(issue="  brg vib  ", action="repl BRG-204")])
        record = load_csv(self.path, data_kind="synthetic")[0]
        self.assertEqual(record.issue_raw, "  brg vib  ")
        self.assertEqual(record.action_raw, "repl BRG-204")
        self.assertEqual(record.evidence.csv_row, 2)
        self.assertEqual(record.evidence.source_file, "records.csv")
        self.assertEqual(len(record.evidence.source_sha256), 64)

    def test_duplicate_ids_rejected(self):
        self.write_rows([self.row(), self.row()])
        with self.assertRaisesRegex(DataError, "duplicate"):
            load_csv(self.path, data_kind="synthetic")

    def test_invalid_date_rejected(self):
        self.write_rows([self.row(event_date="2026-02-30")])
        with self.assertRaisesRegex(DataError, "event_date"):
            load_csv(self.path, data_kind="synthetic")

    def test_compact_date_rejected(self):
        self.write_rows([self.row(event_date="20260101")])
        with self.assertRaises(DataError):
            load_csv(self.path, data_kind="synthetic")

    def test_missing_asset_rejected(self):
        self.write_rows([self.row(asset_id="")])
        with self.assertRaisesRegex(DataError, "asset_id"):
            load_csv(self.path, data_kind="synthetic")

    def test_blank_issue_rejected(self):
        self.write_rows([self.row(issue=" ")])
        with self.assertRaisesRegex(DataError, "issue"):
            load_csv(self.path, data_kind="synthetic")

    def test_empty_action_is_unknown(self):
        self.write_rows([self.row()])
        self.assertEqual(load_csv(self.path, data_kind="synthetic")[0].action_raw, "")

    def test_wrong_columns_rejected(self):
        self.path.write_text("id,text\n1,test\n", encoding="utf-8")
        with self.assertRaisesRegex(DataError, "Expected columns"):
            load_csv(self.path, data_kind="synthetic")

    def test_extra_field_rejected(self):
        self.write_rows([self.row() + ["extra"]])
        with self.assertRaisesRegex(DataError, "fields"):
            load_csv(self.path, data_kind="synthetic")

    def test_empty_file_rejected(self):
        self.path.write_text("", encoding="utf-8")
        with self.assertRaises(DataError):
            load_csv(self.path, data_kind="synthetic")

    def test_header_only_rejected(self):
        self.write_rows([])
        with self.assertRaisesRegex(DataError, "no maintenance"):
            load_csv(self.path, data_kind="synthetic")

    def test_invalid_utf8_rejected(self):
        self.path.write_bytes(b"\xff\xfe")
        with self.assertRaisesRegex(DataError, "UTF-8"):
            load_csv(self.path, data_kind="synthetic")

    def test_bom_unicode_and_multiline(self):
        self.write_rows(
            [self.row(issue="Müller seal\nleak, noted"), self.row(record_id="R-2")]
        )
        self.path.write_bytes(b"\xef\xbb\xbf" + self.path.read_bytes())
        records = load_csv(self.path, data_kind="synthetic")
        self.assertEqual(records[0].issue_raw, "Müller seal\nleak, noted")
        self.assertEqual(records[1].evidence.csv_row, 3)

    def test_content_hash_changes_with_source(self):
        self.write_rows([self.row()])
        first = load_csv(self.path, data_kind="synthetic")[0].evidence.source_sha256
        self.write_rows([self.row(action="checked")])
        second = load_csv(self.path, data_kind="synthetic")[0].evidence.source_sha256
        self.assertNotEqual(first, second)

    def test_data_kind_required_and_validated(self):
        self.write_rows([self.row()])
        with self.assertRaises(DataError):
            load_csv(self.path, data_kind="verified-real")


class RetrievalAndBriefTests(unittest.TestCase):
    def setUp(self):
        self.records = load_csv(DEMO, data_kind="synthetic")

    def test_abbreviation_query_and_exact_asset_filter(self):
        hits = search(self.records, "brg vib", asset_id="PUMP-001")
        self.assertEqual(
            {hit.record.record_id for hit in hits}, {"DEMO-001", "DEMO-002", "DEMO-003"}
        )
        self.assertTrue(all(hit.score > 0 for hit in hits))

    def test_no_overlap_returns_no_hits(self):
        self.assertEqual(search(self.records, "xyzunknown"), [])

    def test_missing_asset_returns_no_hits(self):
        self.assertEqual(search(self.records, "seal", asset_id="PUMP-999"), [])

    def test_invalid_top_k_and_empty_query(self):
        for query, top_k in [("seal", 0), ("  ", 3)]:
            with self.subTest(query=query, top_k=top_k), self.assertRaises(ValueError):
                search(self.records, query, top_k=top_k)

    def test_limit_and_determinism(self):
        first = search(self.records, "seal", top_k=2)
        self.assertEqual(len(first), 2)
        self.assertEqual(first, search(list(reversed(self.records)), "seal", top_k=2))

    def test_grouping_keeps_assets_components_and_negation_separate(self):
        brief = recurring_brief(self.records)
        counts = {g["asset_id"]: g["record_count"] for g in brief["recurring_groups"]}
        self.assertEqual(counts, {"PUMP-001": 3, "PUMP-002": 2, "PUMP-003": 2})
        self.assertEqual(brief["data_kinds"], ["synthetic"])

    def test_date_range_is_inclusive(self):
        brief = recurring_brief(
            self.records, start=date(2026, 1, 3), end=date(2026, 1, 8)
        )
        self.assertEqual(brief["selected_record_count"], 3)
        self.assertEqual(brief["recurring_groups"][0]["record_count"], 2)

    def test_reversed_date_range_rejected(self):
        with self.assertRaises(ValueError):
            recurring_brief(self.records, start=date(2026, 2, 1), end=date(2026, 1, 1))

    def test_empty_window_not_confused_with_empty_import(self):
        brief = recurring_brief(self.records, start=date(2027, 1, 1))
        self.assertEqual(brief["selected_record_count"], 0)
        self.assertEqual(brief["recurring_groups"], [])

    def test_every_group_count_recomputed_from_evidence(self):
        for group in recurring_brief(self.records)["recurring_groups"]:
            self.assertEqual(group["record_count"], len(group["evidence"]))
            self.assertTrue(
                all(item["source"]["source_sha256"] for item in group["evidence"])
            )


class CliIntegrationTests(unittest.TestCase):
    def test_brief_json_output(self):
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["brief", str(DEMO), "--data-kind", "synthetic"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["input_record_count"], 12)

    def test_missing_query_is_reported(self):
        with redirect_stderr(io.StringIO()):
            status = main(["search", str(DEMO), "--data-kind", "synthetic"])
        self.assertEqual(status, 2)

    def test_input_cannot_be_overwritten(self):
        with redirect_stderr(io.StringIO()):
            status = main(
                ["brief", str(DEMO), "--data-kind", "synthetic", "--output", str(DEMO)]
            )
        self.assertEqual(status, 2)

    def test_report_file_written(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "artifacts/report.json"
            status = main(
                [
                    "brief",
                    str(DEMO),
                    "--data-kind",
                    "synthetic",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(status, 0)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["selected_record_count"],
                12,
            )


if __name__ == "__main__":
    unittest.main()
