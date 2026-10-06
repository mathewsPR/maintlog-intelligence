"""Dated source excerpts for completed history reviews; no inferred diagnosis."""

from .domain import Record
from .evidence_review import review_evidence
from .extraction import validate_fields

LIMITATIONS = (
    "These are selected reports, not proof of complete maintenance history. "
    "Similar symptoms alone do not establish a common cause or that an earlier "
    "repair failed. Completed work does not establish successful repair. "
    "Narrative recurrence and causal relationships have not been automatically "
    "verified. Component, relevance and status proposals remain unreviewed."
)


def build_history_review(records: list[Record], proposals: list[dict]) -> dict:
    """Render selected evidence in date order without an additional model call.

    Validate source spans again before rendering. Full narratives remain visible
    so that checks and qualifications are available even when action excerpts
    are narrow. This output does not judge its own semantic correctness.
    """
    if len({record.record_id for record in records}) != len(records):
        raise ValueError("duplicate history record IDs")

    by_id = {}
    selected = {record.record_id for record in records}

    for proposal in proposals:
        record_id = proposal["record_id"]
        if record_id not in selected:
            continue
        if record_id in by_id:
            raise ValueError("duplicate history proposals")
        by_id[record_id] = proposal

    entries = []
    lines = ["Maintenance history — unreviewed source evidence", ""]

    for record in sorted(records, key=lambda item: (item.event_date, item.record_id)):
        proposal = by_id.get(record.record_id)

        if proposal is None and record.narrative_raw:
            raise ValueError("missing narrative extraction for history record")

        fields = {"component": None, "problem": None, "action": None}
        status = "unknown"

        if proposal is not None:
            status = proposal["action_status_proposal"]
            fields = validate_fields(record, proposal["fields"], status)

        citation = {
            "record_id": record.record_id,
            "source_file": record.evidence.source_file,
            "source_sha256": record.evidence.source_sha256,
            "csv_row": record.evidence.csv_row,
        }

        entry = {
            "record_id": record.record_id,
            "date": record.event_date.isoformat(),
            "asset_id": record.asset_id,
            "fields": fields,
            "action_status_proposal": status,
            "citation": citation,
            "source_text": {
                "component": record.component,
                "issue_raw": record.issue_raw,
                "action_raw": record.action_raw,
                "narrative_raw": record.narrative_raw,
            },
        }
        entries.append(entry)

        lines.append(f"{entry['date']} | record {record.record_id}")
        lines.append(
            f"Source: {citation['source_file']}, CSV row {citation['csv_row']}, "
            f"SHA256 {citation['source_sha256']}"
        )

        for name in ("component", "problem", "action"):
            span = fields[name]
            if span is None:
                lines.append(f"{name}: no extracted proposal")
            else:
                lines.append(
                    f"{name}: {span['quote']} "
                    f"[record={record.record_id}; field={span['field']}; "
                    f"offsets={span['start']}:{span['end']}]"
                )

        lines.append(f"Action status proposal: {status}")

        for field, text in entry["source_text"].items():
            if text:
                lines.append(f"Full source ({field}, verbatim): {text}")

        lines.append("")

    checked = [
        {"record_id": entry["record_id"], "fields": entry["fields"]}
        for entry in entries
    ]
    evidence_review = review_evidence(records, checked)

    if evidence_review["concerns"]:
        lines.insert(
            1,
            "Evidence review required: unresolved extraction concerns.",
        )
        lines.append("Extraction concerns:")
        for concern in evidence_review["concerns"]:
            lines.append(
                f"{concern['record_id']} / {concern['field']}: {concern['message']}"
            )

    lines.append(LIMITATIONS)

    return {
        "status": (
            "needs_evidence_review"
            if evidence_review["concerns"]
            else "available_for_review"
        ),
        "evidence_review": evidence_review,
        "method": "dated_source_excerpts_v1",
        "entries": entries,
        "text": "\n".join(lines),
        "limitations": LIMITATIONS,
        "semantic_task_success": None,
    }
