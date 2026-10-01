"""Immutable records preserve source fields separately from normalized text."""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Evidence:
    source_file: str
    source_sha256: str
    csv_row: int
    data_kind: str
    columns: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Record:
    record_id: str
    event_date: date
    asset_id: str
    component: str
    issue_raw: str
    action_raw: str
    issue_normalized: str
    action_normalized: str
    evidence: Evidence
    narrative_raw: str = ""
    normalization_policy: str = "dictionary_v0"


@dataclass(frozen=True)
class SearchHit:
    record: Record
    score: float
