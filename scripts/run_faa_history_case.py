"""run_faa_history_case.py  Compare the main agent and fixed workflow on one real development case."""

import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from maintlog.agent import run_agent
from maintlog.backends import LocalServer
from maintlog.comparison import FixedWorkflow, score_case
from maintlog.domain import Evidence, Record
from maintlog.extraction import validate_fields
from maintlog.scope import Scope
from maintlog.tasks import TaskSpec

SOURCE = Path("data/public/faa_sdr/SDR-2024.csv")
OUTPUT = Path("artifacts/faa-history-development-08")
SOURCE_SHA = "80a2d209092d8aab8a3fd96cddf226418105c62f13a5457ce261b8c780df808e"

INPUT_IDS = {
    "29GA2024021400001",
    "29GA2024031200001",
    "29GA2024041800001",
}
RELEVANT_IDS = [
    "29GA2024021400001",
    "29GA2024041800001",
]
ASSET_ID = 'FAA:["AEROSP","1092"]'
QUERY = "left main landing gear"
QUESTION = (
    "Review left-main landing-gear indication reports for this aircraft. "
    "Identify the reported symptoms and corrective work in date order, "
    "and explain what the records establish about recurrence. "
    "Distinguish similar symptoms from the same confirmed fault. "
    "Do not infer that an earlier repair failed or that the reports "
    "have a common cause."
)

CONFIGURATION = {
    "component_selection": True,
    "boundary_adapter": True,
    "focused_status_repair": True,
}

REFERENCE_QUOTES = {
    "29GA2024021400001": {
        "component": "11GB PROXIMITY SWITCH",
        "problem": "LEFT MAIN UNLK LIGHT ON OVERHEAD PANEL",
        "action": "REMOVED AND REPLACED 11GB PROX SWITCH",
    },
    "29GA2024041800001": {
        "component": "FWD. LH DOWN LOCK SENSOR ELECTRICAL CONNECTOR",
        "problem": (
            "LT MAIN LANDING GEAR UNSAFE INDICATION ON SECONDARY PANEL "
            "DURING FINAL APPROACH"
        ),
        "action": (
            "FOUND FWD. LH DOWN LOCK SENSOR ELECTRICAL CONNECTOR LOOSE AND RESECURED"
        ),
    },
}


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, default=str)
        stream.write("\n")


def load_records():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("FAA snapshot hash mismatch")

    records = []
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        for row_number, row in enumerate(csv.DictReader(stream), start=2):
            record_id = row["OperatorControlNumber"].strip()
            if record_id not in INPUT_IDS:
                continue

            identity = (
                row["AircraftMake"].strip().upper(),
                row["AircraftSerialNumber"].strip().upper(),
                row["RegistryNNumber"].strip().upper(),
            )
            if identity != ("AEROSP", "1092", "708SV"):
                raise ValueError("Development-case identity changed")

            records.append(
                Record(
                    record_id=record_id,
                    event_date=datetime.strptime(
                        row["DifficultyDate"].strip(), "%m/%d/%Y"
                    ).date(),
                    asset_id=ASSET_ID,
                    component="",
                    issue_raw="",
                    action_raw="",
                    issue_normalized="",
                    action_normalized="",
                    narrative_raw=row["Discrepancy"],
                    evidence=Evidence(
                        source_file=SOURCE.name,
                        source_sha256=SOURCE_SHA,
                        csv_row=row_number,
                        data_kind="user-supplied",
                        columns={"narrative": "Discrepancy"},
                    ),
                )
            )

    if (
        len(records) != len(INPUT_IDS)
        or {record.record_id for record in records} != INPUT_IDS
    ):
        raise ValueError("Missing or duplicate development-case records")

    return sorted(records, key=lambda record: (record.event_date, record.record_id))


def main():
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Python 3.11 required")
    if OUTPUT.exists():
        raise SystemExit(f"Preserve existing output: {OUTPUT}")

    records = load_records()
    by_id = {record.record_id: record for record in records}

    # These references are supplied only to scoring, never to either backend.
    expected_fields = {}
    for record_id, quotes in REFERENCE_QUOTES.items():
        fields = {
            name: {"field": "narrative_raw", "quote": quote}
            for name, quote in quotes.items()
        }
        expected_fields[record_id] = {
            "fields": validate_fields(
                by_id[record_id],
                fields,
                "completed",
                human_review=True,
            ),
            "action_status": "completed",
        }

    case = {
        "id": "faa-left-main-indication-development-v1",
        "question": QUESTION,
        "query": QUERY,
        "task": "history",
        "scope": {"asset_id": ASSET_ID},
        "relevant_record_ids": RELEVANT_IDS,
        "expected_fields": expected_fields,
        "label_provenance": (
            "Development references reviewed from three exposed narratives "
            "in this conversation. Single-reviewer, strict excerpt boundaries; "
            "not an independent holdout or a representative benchmark."
        ),
        "written_answer_requirements": [
            "Describe the February and April reports in date order.",
            "Describe their reported corrective work and checks.",
            "Exclude the unrelated March engine report.",
            "State that similar symptoms do not establish a common cause.",
            "Do not claim the February repair failed.",
            "Link each finding to its supporting evidence.",
        ],
    }

    OUTPUT.mkdir(parents=True, exist_ok=False)
    write_new(
        OUTPUT / "case.json",
        {
            "source_sha256": SOURCE_SHA,
            "configuration": CONFIGURATION,
            "case": case,
            "input_records": records_as_dicts(records),
        },
    )

    summaries = {}
    for workflow in ("agent", "fixed"):
        provider = LocalServer(
            base_url="http://127.0.0.1:8081/v1",
            model="qwen35-4b",
            **CONFIGURATION,
        )
        chooser = (
            provider
            if workflow == "agent"
            else FixedWorkflow(provider, QUERY, "history")
        )

        report = run_agent(
            records,
            QUESTION,
            chooser,
            scope=Scope(asset_id=ASSET_ID),
            task=TaskSpec(mode="history", initial_query=QUERY),
            max_steps=12,
            timeout_seconds=120,
            max_context_chars=10000,
        )

        metrics = score_case(report, case)
        result = {
            "workflow": workflow,
            "metrics": metrics,
            "written_answer_assessment": {
                "status": "not_scored",
                "history_review_present": report.get("history_review") is not None,
                "reason": (
                    "The report can contain a source-backed history review. "
                    "The strict scorer measures selected records, extraction spans, "
                    "execution statuses and workflow completion. It does not assess "
                    "the requested explanation or establish semantic correctness."
                ),
            },
            "report": report,
        }
        write_new(OUTPUT / f"{workflow}.json", result)

        summaries[workflow] = {
            "status": report["status"],
            "workflow_complete": metrics["workflow_complete"],
            "final_record_ids": [
                row["record_id"] for row in report["records_for_review"]
            ],
            "record_precision": metrics["record_precision"],
            "record_recall": metrics["record_recall"],
            "field_tp": metrics["field_tp"],
            "field_fp": metrics["field_fp"],
            "field_fn": metrics["field_fn"],
            "status_correct": metrics["status_correct"],
            "status_total": metrics["status_total"],
            "labeled_task_success": metrics["labeled_task_success"],
            "model_calls": metrics["model_calls"],
            "elapsed_seconds": metrics["elapsed_seconds"],
            "errors": [
                {
                    "step": step["step"],
                    "error": step.get("tool_error", step.get("error")),
                }
                for step in report["trace"]
                if "tool_error" in step or "error" in step
            ],
        }
        print(
            json.dumps({workflow: summaries[workflow]}, indent=2),
            flush=True,
        )

    write_new(OUTPUT / "summary.json", summaries)
    print(f"Saved: {OUTPUT}")
    return 0


def records_as_dicts(records):
    from dataclasses import asdict

    return [asdict(record) for record in records]


if __name__ == "__main__":
    raise SystemExit(main())
