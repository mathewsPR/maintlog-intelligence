"""Only aggregate explicitly repeated normalized wording on the same asset."""

from collections import defaultdict
from dataclasses import asdict
from datetime import date

from .domain import Record
from .scope import Scope


def recurring_brief(
    records: list[Record],
    *,
    start: date | None = None,
    end: date | None = None,
    asset_id: str | None = None,
) -> dict:
    selected = Scope(asset_id, start, end).select(records)
    groups: dict[tuple[str, str, str], list[Record]] = defaultdict(list)
    for record in selected:
        if not record.component or not record.issue_normalized.strip():
            continue
        key = (
            record.asset_id,
            record.component,
            " ".join(record.issue_normalized.casefold().split()),
        )
        groups[key].append(record)
    recurring = []
    for (asset_id, component, issue), group in sorted(groups.items()):
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda r: (r.event_date, r.record_id))
        recurring.append(
            {
                "asset_id": asset_id,
                "component": component,
                "normalized_issue_key": issue,
                "record_count": len(ordered),
                "first_date": ordered[0].event_date.isoformat(),
                "last_date": ordered[-1].event_date.isoformat(),
                "evidence": [
                    {
                        "record_id": r.record_id,
                        "event_date": r.event_date.isoformat(),
                        "issue_raw": r.issue_raw,
                        "action_raw": r.action_raw,
                        "source": asdict(r.evidence),
                    }
                    for r in ordered
                ],
            }
        )
    return {
        "method": "same_asset_component_and_normalized_issue_wording",
        "data_kinds": sorted({r.evidence.data_kind for r in records}),
        "input_record_count": len(records),
        "selected_record_count": len(selected),
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "asset_id": asset_id,
        "unstructured_record_count": sum(not r.issue_raw.strip() for r in selected),
        "recurring_groups": recurring,
        "interpretation": (
            "Repeated wording is a candidate for engineer review. Counts describe "
            "records, not distinct failures; repairs, root causes, and future failures "
            "are not inferred. Synthetic data demonstrates behavior only."
        ),
    }
