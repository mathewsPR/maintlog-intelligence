"""run_faa_history_batch.pyComplete FAA history workflows with versioned budgets and safe resume."""

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

import maintlog
from maintlog.agent import run_agent
from maintlog.backends import LocalServer
from maintlog.comparison import FixedWorkflow
from maintlog.domain import Evidence, Record
from maintlog.scope import Scope
from maintlog.tasks import TaskSpec
from maintlog.token_log import summarize_usage

VERSION = "faa-history-operational-v3-token-log"
ROOT = Path(__file__).resolve().parents[1]
CONFIGURATION = {
    "component_selection": True,
    "boundary_adapter": True,
    "focused_status_repair": True,
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def save_json(path, value, *, replace=False):
    """Finish writing before publishing a file; preserve existing run results."""
    if path.exists() and not replace:
        raise FileExistsError(f"Preserve existing file: {path}")

    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, default=str)
        stream.write("\n")

    if path.exists() and not replace:
        temporary.unlink()
        raise FileExistsError(f"Preserve existing file: {path}")

    os.replace(temporary, path)


def build_records(history, source_sha):
    asset_id = "FAA:" + json.dumps(history["make_serial"], separators=(",", ":"))
    records = []

    for item in history["records"]:
        records.append(
            Record(
                record_id=item["record_id"],
                event_date=datetime.strptime(
                    item["difficulty_date"].strip(), "%m/%d/%Y"
                ).date(),
                asset_id=asset_id,
                component="",
                issue_raw="",
                action_raw="",
                issue_normalized="",
                action_normalized="",
                narrative_raw=item["narrative_raw"],
                evidence=Evidence(
                    source_file="SDR-2024.csv",
                    source_sha256=source_sha,
                    csv_row=item["csv_row"],
                    data_kind="user-supplied",
                    columns={"narrative": "Discrepancy"},
                ),
            )
        )

    if not records:
        raise ValueError("Empty candidate history")
    if len({record.record_id for record in records}) != len(records):
        raise ValueError("Duplicate record IDs")

    return asset_id, sorted(
        records, key=lambda record: (record.event_date, record.record_id)
    )


def task_for(history):
    placeholders = {"", "UNKNOWN", "UNK", "N/A", "NA", "NONE"}
    names = Counter(
        item["source_fields"]["PartName"].strip()
        for item in history["records"]
        if item["source_fields"]["PartName"].strip().upper() not in placeholders
    )

    if names:
        query = sorted(names, key=lambda name: (-names[name], name))[0]
    else:
        query = " ".join(history["records"][0]["narrative_raw"].split()[:6])

    if not query:
        raise ValueError("Cannot create a topic from empty source text")

    query = query[:500]
    question = (
        f"Review this aircraft's reports concerning {query!r}. "
        "Identify relevant reported symptoms and corrective work in date order. "
        "Cite the supporting reports. Distinguish performed work from repair "
        "success, and similar symptoms from a confirmed common fault. "
        "Do not infer that an earlier repair failed. State uncertainty and "
        "limitations of the available reports."
    )
    return query, question


def summarize(report):
    history = report.get("history_review") or {}
    review = history.get("evidence_review") or {}
    errors = [
        {
            "step": step.get("step"),
            "error": step.get("tool_error", step.get("error")),
        }
        for step in report.get("trace", [])
        if "tool_error" in step or "error" in step
    ]

    return {
        "run_status": report.get("status"),
        "workflow_complete": report.get("completion", {}).get(
            "requirements_met", False
        ),
        "selected_record_ids": [
            row["record_id"] for row in report.get("records_for_review", [])
        ],
        "proposal_count": len(report.get("extraction_proposals", [])),
        "history_status": history.get("status"),
        "targeted_concern_count": len(review.get("concerns", [])),
        "model_calls": report.get("model_calls"),
        "elapsed_seconds": report.get("elapsed_seconds"),
        "errors": errors,
        "semantic_accuracy": None,
        "complete_task_success": None,
    }


def write_summary(output, rows, planned):
    summary = {
        "protocol": VERSION,
        "planned_runs": planned,
        "saved_runs": len(rows),
        "batch_complete": len(rows) == planned,
        "workflows": {},
        "semantic_accuracy": None,
        "complete_task_success": None,
        "interpretation": (
            "Unlabelled operational evaluation. Completion, absence of warnings, "
            "and valid source spans do not establish answer accuracy. "
            "The v2 step budget differs from the earlier 12-step batch."
        ),
        "runs": rows,
        "token_usage": summarize_usage(output / "token-usage.jsonl"),
    }

    for workflow in ("agent", "fixed"):
        selected = [row for row in rows if row["workflow"] == workflow]
        summary["workflows"][workflow] = {
            "runs": len(selected),
            "workflow_completed": sum(row["workflow_complete"] for row in selected),
            "status_counts": dict(Counter(row["run_status"] for row in selected)),
        }

    save_json(output / "summary.json", summary, replace=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidates",
        type=Path,
        default=ROOT / "data/benchmarks/faa_history/candidate_histories_v1.json",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "data/public/faa_sdr/SDR-2024.csv",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--model", default="qwen35-4b")
    parser.add_argument("--base-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if sys.version_info[:2] != (3, 11):
        parser.error("Python 3.11 required")
    if not 1 <= args.trials <= 10:
        parser.error("--trials must be between 1 and 10")
    if not 1 <= args.max_steps <= 20:
        parser.error("--max-steps must be between 1 and 20")
    if args.output.exists() and not args.resume:
        parser.error("Output exists; use --resume or a new directory")
    if args.resume and not args.output.is_dir():
        parser.error("--resume requires an existing batch directory")

    payload = json.loads(args.candidates.read_text(encoding="utf-8"))
    if sha(args.source) != payload["source_sha256"]:
        parser.error("FAA source snapshot hash mismatch")

    histories = payload["histories"]
    if not histories:
        parser.error("No candidate histories")
    ids = [history["candidate_id"] for history in histories]
    if len(set(ids)) != len(ids):
        parser.error("Duplicate candidate IDs")

    prepared = []
    for history in histories:
        asset_id, records = build_records(history, payload["source_sha256"])
        query, question = task_for(history)
        prepared.append((history["candidate_id"], asset_id, records, query, question))

    # Hash the package actually imported by this Python environment.
    package_root = Path(maintlog.__file__).resolve().parent
    identity = {
        "protocol": VERSION,
        "python": sys.version,
        "source_sha256": payload["source_sha256"],
        "candidate_sha256": sha(args.candidates),
        "runner_sha256": sha(Path(__file__)),
        "implementation_sha256": {
            path.relative_to(package_root).as_posix(): sha(path)
            for path in sorted(package_root.rglob("*.py"))
        },
        "model": args.model,
        "base_url": args.base_url,
        "configuration": CONFIGURATION,
        "budgets": {
            "max_steps": args.max_steps,
            "timeout_seconds": 120,
            "max_context_chars": 10000,
        },
        "trials": args.trials,
        "histories": len(histories),
    }
    batch_id = fingerprint(identity)
    planned = len(histories) * args.trials * 2

    if args.resume:
        manifest_path = args.output / "manifest.json"
        if not manifest_path.is_file():
            parser.error("Missing manifest; cannot safely resume")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("batch_id") != batch_id:
            parser.error(
                "Code, inputs, Python, or configuration changed. "
                "Use a new output directory."
            )

    rows = []
    pending = []

    for candidate_id, asset_id, records, query, question in prepared:
        for trial in range(1, args.trials + 1):
            workflows = ("agent", "fixed") if trial % 2 else ("fixed", "agent")
            for workflow in workflows:
                name = f"{candidate_id}-trial-{trial:02d}-{workflow}.json"
                path = args.output / name
                key = {
                    "candidate_id": candidate_id,
                    "trial": trial,
                    "workflow": workflow,
                }

                if path.exists():
                    saved = json.loads(path.read_text(encoding="utf-8"))
                    if (
                        saved.get("batch_id") != batch_id
                        or any(saved.get(k) != v for k, v in key.items())
                        or not isinstance(saved.get("summary"), dict)
                    ):
                        parser.error(f"Invalid saved result: {path}")
                    rows.append({**key, **saved["summary"]})
                else:
                    pending.append((path, key, asset_id, records, query, question))

    if pending:
        with urlopen(args.base_url.rstrip("/") + "/models", timeout=10) as response:
            models = json.load(response)

        available = {item["id"] for item in models.get("data", [])}
        if args.model not in available:
            parser.error(f"Model alias not advertised: {args.model}")

        if not args.resume:
            args.output.mkdir(parents=True)
            save_json(
                args.output / "manifest.json",
                {
                    "batch_id": batch_id,
                    "identity": identity,
                    "planned_runs": planned,
                    "server_models_response": models,
                    "limitations": (
                        "Server alias does not prove loaded model-file identity. "
                        "Questions are source-derived; relevance and semantic "
                        "correctness have no reviewed labels."
                    ),
                },
            )

    if not args.output.exists():
        parser.error("Batch directory was not created")

    write_summary(args.output, rows, planned)
    print(
        f"Saved: {len(rows)}/{planned}; pending: {len(pending)}",
        flush=True,
    )

    try:
        for path, key, asset_id, records, query, question in pending:
            provider = LocalServer(
                base_url=args.base_url,
                model=args.model,
                token_log_path=str((args.output / "token-usage.jsonl").resolve()),
                run_id=path.stem,
                **CONFIGURATION,
            )
            chooser = (
                provider
                if key["workflow"] == "agent"
                else FixedWorkflow(provider, query, "history")
            )
            result = {
                "batch_id": batch_id,
                **key,
                "question": question,
                "query": query,
                "input_record_ids": [record.record_id for record in records],
            }

            try:
                report = run_agent(
                    records,
                    question,
                    chooser,
                    scope=Scope(asset_id=asset_id),
                    task=TaskSpec(mode="history", initial_query=query),
                    max_steps=args.max_steps,
                    timeout_seconds=120,
                    max_context_chars=10000,
                )
                result["report"] = report
                result["summary"] = summarize(report)
            except Exception as exc:
                result["summary"] = {
                    "run_status": "runner_error",
                    "workflow_complete": False,
                    "exception": f"{type(exc).__name__}: {exc}",
                    "semantic_accuracy": None,
                    "complete_task_success": None,
                }

            result["token_usage"] = summarize_usage(
                args.output / "token-usage.jsonl", path.stem
            )
            save_json(path, result)
            rows.append({**key, **result["summary"]})
            write_summary(args.output, rows, planned)
            print(
                f"{len(rows)}/{planned} {path.name}: {result['summary']['run_status']}",
                flush=True,
            )

    except KeyboardInterrupt:
        write_summary(args.output, rows, planned)
        print(
            "\nInterrupted. Saved runs are preserved. "
            "Resume with the same command plus --resume.",
            flush=True,
        )
        return 130

    summary = write_summary(args.output, rows, planned)
    print(json.dumps(summary["workflows"], indent=2))
    print(f"Saved: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
