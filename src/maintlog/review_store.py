"""Validated field reviews and source-bound reuse; source records are never edited."""

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

from .brief import recurring_brief
from .domain import Evidence, Record
from .extraction import FIELD_NAMES, STATUSES, resolve_span, validate_fields
from .normalization import normalize_nouns
from .scope import Scope


def report_records(report: dict) -> dict[str, Record]:
    rows = {r["record_id"]: r for r in report["records_for_review"]}
    for step in report["trace"]:
        row = step.get("tool_result", {})
        if step.get("decision", {}).get("tool") == "record" and "record_id" in row:
            rows.setdefault(row["record_id"], row)
    records = {}
    for rid, row in rows.items():
        copy = dict(row)
        copy["event_date"] = date.fromisoformat(str(copy["event_date"]))
        copy["evidence"] = Evidence(**copy["evidence"])
        records[rid] = Record(**copy)
    return records


def validate_field_review(report: dict, row: dict) -> dict | None:
    if "fields" not in row and "action_status" not in row:
        return None  # Old record-level acceptance never silently approves fields.
    record = report_records(report)[row["record_id"]]
    base = next(
        (
            p
            for p in report["extraction_proposals"]
            if p["record_id"] == row["record_id"]
        ),
        None,
    )
    fields = row.get("fields", {})
    if not isinstance(fields, dict) or not set(fields) <= FIELD_NAMES:
        raise ValueError("invalid field review names")
    resolved = {}
    for name, review in fields.items():
        if not isinstance(review, dict) or review.get("decision") not in {
            "accepted",
            "rejected",
            "corrected",
        }:
            raise ValueError("invalid field review decision")
        choice = review["decision"]
        expected = {"decision", "span"} if choice == "corrected" else {"decision"}
        if set(review) != expected:
            raise ValueError("invalid field review keys")
        if choice == "accepted":
            if base is None:
                raise ValueError("no extraction proposal to accept; use corrected")
            span = base["fields"][name]
        elif choice == "rejected":
            span = None
        else:
            span = review["span"]
        resolved[name] = {"decision": choice, "span": resolve_span(record, span, name)}
    status_review = row.get("action_status")
    status = None
    if status_review is not None:
        if not isinstance(status_review, dict) or set(status_review) != {
            "decision",
            "value",
        }:
            raise ValueError("invalid action-status review keys")
        choice, value = status_review["decision"], status_review["value"]
        if choice not in {"accepted", "rejected", "corrected"} or value not in STATUSES:
            raise ValueError("invalid action-status review")
        if choice == "accepted" and (
            base is None or value != base["action_status_proposal"]
        ):
            raise ValueError("accepted status must match the proposal")
        if choice == "rejected" and value != "unknown":
            raise ValueError("rejected status must be unknown")
        status = dict(status_review)
    complete = (
        set(resolved) == FIELD_NAMES
        and status is not None
        and row["decision"] == "accepted"
    )
    if complete:
        validate_fields(
            record,
            {name: review["span"] for name, review in resolved.items()},
            status["value"],
            human_review=True,
        )
    return {
        "fields": resolved,
        "action_status": status,
        "complete": complete,
        "semantic_validation": "human_review_not_automatic_proof",
    }


def reviewed_brief(
    records: list[Record],
    database: Path,
    run_sha256: str,
    *,
    scope: Scope = Scope(),
    vocabulary: dict | None = None,
) -> dict:
    from .vocabulary import predict

    def normalizer(text):
        return (
            predict(text, vocabulary)
            if vocabulary is not None
            else normalize_nouns(text)
        )

    selected = scope.select(records)
    if not database.is_file():
        raise ValueError("review database does not exist")
    from .review import canonical, run_hash

    # Read-only open: a missing/mistyped database must not create an empty file.
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as conn:
        run = conn.execute(
            "SELECT report_json FROM runs WHERE sha256=?", (run_sha256,)
        ).fetchone()
        if run is None:
            raise ValueError("unknown review run")
        report = json.loads(run[0])
        if run_hash(report) != run_sha256:
            raise ValueError("stored run hash mismatch")
        try:
            events = conn.execute(
                """SELECT r.event_id,r.record_id,r.reviewer,r.decision,r.reviewed_at,f.review_json
                FROM review_events r LEFT JOIN field_review_events f ON f.event_id=r.event_id
                WHERE r.run_sha256=? AND r.event_id IN (
                  SELECT MAX(event_id) FROM review_events WHERE run_sha256=? GROUP BY record_id)
                ORDER BY r.record_id""",
                (run_sha256, run_sha256),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise ValueError(
                "database has no field-review history; import explicit field reviews"
            ) from exc
    snapshots = report_records(report)
    live = {r.record_id: r for r in records}
    # Check every snapshot, including records excluded by a new filter. A changed
    # CSV or mapping invalidates reuse instead of silently mixing source versions.
    for rid, snapshot in snapshots.items():
        if rid not in live or canonical(asdict(live[rid])) != canonical(
            asdict(snapshot)
        ):
            raise ValueError("source CSV or profile differs from the reviewed run")
    selected_ids = {r.record_id for r in selected}
    projected = []
    provenance = {}
    for event_id, rid, reviewer, decision, reviewed_at, review_json in events:
        if rid not in selected_ids or decision != "accepted" or review_json is None:
            continue
        review = json.loads(review_json)
        if not review["complete"]:
            continue
        fields = {name: item["span"] for name, item in review["fields"].items()}
        status = review["action_status"]["value"]
        fields = validate_fields(live[rid], fields, status, human_review=True)
        component, issue, action = (
            fields[name]["quote"] if fields[name] else ""
            for name in ("component", "problem", "action")
        )
        projected.append(
            replace(
                live[rid],
                component=component,
                issue_raw=issue,
                action_raw=action,
                issue_normalized=normalizer(issue),
                action_normalized=normalizer(action),
            )
        )
        provenance[rid] = {
            "event_id": event_id,
            "run_sha256": run_sha256,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "fields": fields,
            "action_status": status,
            "original_record": asdict(live[rid]),
        }
    result = recurring_brief(projected)
    for group in result["recurring_groups"]:
        for evidence in group["evidence"]:
            evidence["field_review"] = provenance[evidence["record_id"]]
    result.update(
        {
            "method": "human_reviewed_spans_same_asset_component_issue_wording",
            "input_record_count": len(records),
            "selected_record_count": len(selected),
            "eligible_reviewed_record_count": len(projected),
            "unreviewed_or_rejected_record_count": len(selected) - len(projected),
            "review_run_sha256": run_sha256,
            "scope": asdict(scope),
            "reviewed_records": [
                {"record_id": r.record_id, "field_review": provenance[r.record_id]}
                for r in projected
            ],
            "interpretation": "Only latest complete accepted field reviews are reused. Counts describe records, not failures. Human classifications remain review judgments; original CSV bytes are unchanged.",
        }
    )
    return result
