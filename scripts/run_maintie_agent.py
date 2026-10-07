"""Run the real Maintlog agent on MaintIE narratives; Python 3.11.

Singleton history tasks exercise search, record, focused extraction, aggregate,
validation/recovery and finish. Synthetic IDs/date are adapter metadata, not
observed asset histories. MaintIE gold entities never enter agent context.
Entity comparisons are diagnostics, not full five-class NER or semantic scores.
"""

import argparse
import hashlib
import json
import platform
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def token_offsets(row):
    """Align original token strings without modifying source text."""
    offsets, cursor = [], 0
    for token in row["tokens"]:
        start = row["text"].find(token, cursor)
        if start < 0 or row["text"][cursor:start].strip():
            raise ValueError("Tokens do not align verbatim to original source")
        offsets.append((start, start + len(token)))
        cursor = start + len(token)
    if row["text"][cursor:].strip():
        raise ValueError("Unaligned trailing source text")
    return offsets


def diagnostics(report, source):
    try:
        offsets = token_offsets(source)
    except ValueError:
        offsets = None
    gold = {
        (offsets[e["start"]][0], offsets[e["end"] - 1][1], e["type"].split("/")[0])
        for e in source["entities"]
        if offsets is not None
    }
    # Deliberately broad associations, not official MaintIE task labels.
    compatible = {
        "component": {"PhysicalObject"},
        "problem": {"State", "Property"},
        "action": {"Activity", "Process"},
    }
    details = []
    for proposal in report.get("extraction_proposals", []):
        for name, span in proposal.get("fields", {}).items():
            if span is None:
                continue
            valid = (
                span.get("field") == "narrative_raw"
                and type(span.get("start")) is int
                and type(span.get("end")) is int
                and 0 <= span["start"] < span["end"] <= len(source["text"])
                and span.get("quote") == source["text"][span["start"] : span["end"]]
            )
            matched = sorted(
                kind
                for start, end, kind in gold
                if valid and (start, end) == (span["start"], span["end"])
            )
            details.append(
                {
                    "field": name,
                    "span": span,
                    "source_valid": valid,
                    "exact_gold_entity_classes": matched,
                    "compatible_class_exact_span": bool(
                        set(matched) & compatible.get(name, set())
                    ),
                }
            )
    trace = report.get("trace", [])
    errors = [
        i for i, step in enumerate(trace) if "error" in step or "tool_error" in step
    ]
    complete = report.get("completion", {}).get("requirements_met", False)
    return {
        "workflow_complete": complete,
        "expected_record_selected": [
            r["record_id"] for r in report.get("records_for_review", [])
        ]
        == ["TARGET"],
        "run_status": report.get("status"),
        "model_calls": report.get("model_calls"),
        "elapsed_seconds": report.get("elapsed_seconds"),
        "error_steps": len(errors),
        "completed_after_error": bool(errors) and complete,
        "nonnull_spans": len(details),
        "source_valid_spans": sum(d["source_valid"] for d in details),
        "entity_alignment_available": offsets is not None,
        "entity_alignment_error": None
        if offsets is not None
        else "Tokens do not align verbatim to original source",
        "exact_gold_entity_spans": sum(
            bool(d["exact_gold_entity_classes"]) for d in details
        )
        if offsets is not None
        else None,
        "compatible_class_exact_spans": sum(
            d["compatible_class_exact_span"] for d in details
        )
        if offsets is not None
        else None,
        "span_diagnostics": details,
        "semantic_success": None,
        "action_status_correctness": None,
        "chronology_correctness": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", type=Path, default=Path("data/public/maintie/gold_release.json")
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/benchmarks/maintie/split_manifest.json"),
    )
    parser.add_argument(
        "--split", choices=("test", "validation", "train", "all"), default="test"
    )
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--model", default="qwen35-4b")
    parser.add_argument("--base-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--model-file", type=Path, required=True)
    parser.add_argument("--server-file", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11):
        parser.error("Python 3.11 required")
    if (
        not 1 <= args.trials <= 10
        or not 1 <= args.max_steps <= 20
        or not 1 <= args.timeout <= 120
    ):
        parser.error("trials=1..10, max-steps=1..20, timeout=1..120 required")
    import maintlog
    from maintlog.agent import run_agent
    from maintlog.backends import LocalServer
    from maintlog.domain import Evidence, Record
    from maintlog.maintie_benchmark import validate_manifest
    from maintlog.scope import Scope
    from maintlog.tasks import TaskSpec

    raw = args.data.read_bytes()
    records, manifest = json.loads(raw), read(args.manifest)
    if sha(raw) != manifest["source_sha256"]:
        raise ValueError("Dataset hash mismatch")
    splits = validate_manifest(records, manifest)
    indices = (
        sorted(i for members in splits.values() for i in members)
        if args.split == "all"
        else splits[args.split]
    )
    unaligned_indices = []
    for index in indices:
        try:
            token_offsets(records[index])
        except ValueError:
            unaligned_indices.append(index)
    package_root = Path(maintlog.__file__).resolve().parent

    def file_hash(path):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    plan = {
        "schema_version": 1,
        "protocol": "maintie_real_agent_singleton_history_v1",
        "python": platform.python_version(),
        "source_sha256": sha(raw),
        "manifest_sha256": file_hash(args.manifest),
        "runner_sha256": file_hash(Path(__file__)),
        "implementation_sha256": {
            str(p.relative_to(package_root)): file_hash(p)
            for p in sorted(package_root.rglob("*.py"))
        },
        "model_file_sha256": file_hash(args.model_file),
        "server_file_sha256": file_hash(args.server_file),
        "model": args.model,
        "base_url": args.base_url,
        "split": args.split,
        "indices": indices,
        "trials": args.trials,
        "max_steps": args.max_steps,
        "timeout_seconds": args.timeout,
        "unaligned_record_indices": unaligned_indices,
        "backend": {
            "max_tokens": 512,
            "component_selection": True,
            "boundary_adapter": True,
            "focused_status_repair": True,
        },
        "limitations": [
            "Adapted singleton history tasks, not official MaintIE benchmark",
            "No real asset/date metadata or multi-event chronology",
            "Entity associations are diagnostics, not semantic accuracy",
            "No artificial fault injection; recovery is observed when errors occur",
            "File hashes do not prove the live server loaded those files",
            "Previously inspected/tuned test data is development data",
        ],
    }
    if args.preflight:
        print(
            json.dumps(
                {
                    "preflight": "passed",
                    "records": len(indices),
                    "agent_runs": len(indices) * args.trials,
                    "model_calls": 0,
                    "split": args.split,
                    "unaligned_records": len(unaligned_indices),
                },
                indent=2,
            )
        )
        return
    if args.resume:
        if read(args.run_dir / "plan.json") != plan:
            raise ValueError("Resume source/configuration changed")
    else:
        args.run_dir.mkdir(parents=True, exist_ok=False)
        write(args.run_dir / "plan.json", plan)
    totals = Counter()
    statuses = Counter()
    for trial in range(1, args.trials + 1):
        for index in indices:
            path = args.run_dir / f"record-{index:04d}-trial-{trial:02d}.json"
            if path.exists():
                row = read(path)
                if (row["index"], row["trial"]) != (index, trial):
                    raise ValueError("Checkpoint identity mismatch")
            else:
                source = records[index]
                record = Record(
                    "TARGET",
                    date(2000, 1, 1),
                    "MAINTIE-SINGLETON",
                    "",
                    "",
                    "",
                    "",
                    "",
                    Evidence(
                        args.data.name,
                        sha(raw),
                        index + 1,
                        "public",
                        {"narrative": "text"},
                    ),
                    narrative_raw=source["text"],
                )
                provider = LocalServer(
                    base_url=args.base_url,
                    model=args.model,
                    max_tokens=512,
                    component_selection=True,
                    boundary_adapter=True,
                    focused_status_repair=True,
                    token_log_path=str(args.run_dir / "tokens.jsonl"),
                    run_id=f"record-{index}-trial-{trial}",
                )
                started = time.monotonic()
                report, error = None, None
                # Contain case-level runtime failures; preserve denominator and continue.
                try:
                    report = run_agent(
                        [record],
                        "Review this maintenance narrative and its reported work. "
                        "Inspect the source, propose supported fields, compute the aggregate, "
                        "and select the record for review. Adapter IDs and date are artificial.",
                        provider,
                        scope=Scope(asset_id="MAINTIE-SINGLETON"),
                        task=TaskSpec("history", source["tokens"][0][:500]),
                        max_steps=args.max_steps,
                        timeout_seconds=args.timeout,
                    )
                except Exception as exc:
                    error = {"type": type(exc).__name__, "message": str(exc)}
                row = {
                    "index": index,
                    "trial": trial,
                    "source_text_sha256": sha(source["text"].encode()),
                    "error": error,
                    "report": report,
                    "wall_seconds": round(time.monotonic() - started, 3),
                    "metrics": diagnostics(report, source)
                    if report
                    else {"workflow_complete": False, "run_status": "runner_error"},
                }
                write(path, row)
            metrics = row["metrics"]
            statuses[metrics["run_status"]] += 1
            totals["runs"] += 1
            if metrics.get("entity_alignment_available"):
                totals["entity_diagnostic_runs"] += 1
                totals["entity_diagnostic_spans"] += metrics.get("nonnull_spans", 0)
            for key in (
                "workflow_complete",
                "expected_record_selected",
                "error_steps",
                "completed_after_error",
                "nonnull_spans",
                "source_valid_spans",
                "exact_gold_entity_spans",
                "compatible_class_exact_spans",
            ):
                totals[key] += metrics.get(key, 0) or 0
            print(
                f"trial={trial} record={index} status={metrics['run_status']} completed={metrics['workflow_complete']}",
                flush=True,
            )
            write(
                args.run_dir / "summary.json",
                {
                    "schema_version": 1,
                    "totals": dict(totals),
                    "statuses": dict(statuses),
                    "planned_runs": len(indices) * args.trials,
                    "finished": totals["runs"] == len(indices) * args.trials,
                    "interpretation": plan["limitations"],
                    "token_usage": "See tokens.jsonl; missing usage is unknown, not zero",
                },
            )
    print(f"Saved results: {args.run_dir}")


if __name__ == "__main__":
    main()
