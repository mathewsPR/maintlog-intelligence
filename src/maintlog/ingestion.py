"""Strict single-format CSV ingestion with reproducible source references."""

import csv
import hashlib
import io
import json
from datetime import date
from pathlib import Path

from .domain import Evidence, Record
from .normalization import normalize_nouns

FIELDS = ["record_id", "event_date", "asset_id", "component", "issue", "action"]
DATA_KINDS = ("synthetic", "user-supplied")


class DataError(ValueError):
    """An input violates the declared data contract."""


def load_profile(path: Path) -> dict[str, str]:
    """Map canonical fields to source headers; never guess company semantics."""
    profile = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict) or set(profile) != {"columns"}:
        raise DataError("profile must contain only a columns object")
    columns = profile["columns"]
    allowed = set(FIELDS) | {"narrative"}
    if not isinstance(columns, dict) or not set(columns) <= allowed:
        raise DataError("profile contains unsupported canonical fields")
    if not {"record_id", "event_date", "asset_id"} <= set(columns):
        raise DataError("profile requires record_id, event_date, asset_id mappings")
    if ("narrative" in columns) == ("issue" in columns):
        raise DataError("map exactly one of narrative or issue")
    if "narrative" in columns and "action" in columns:
        raise DataError("narrative mode cannot also map action")
    if any(not isinstance(v, str) or not v.strip() for v in columns.values()):
        raise DataError("source header names must be nonempty strings")
    if len(set(columns.values())) != len(columns):
        raise DataError("source columns cannot be mapped twice")
    return columns


def load_csv(
    path: Path,
    *,
    data_kind: str,
    columns: dict[str, str] | None = None,
    vocabulary: dict | None = None,
) -> list[Record]:
    if data_kind not in DATA_KINDS:
        raise DataError(f"data_kind must be one of {DATA_KINDS}")
    if vocabulary is not None:
        from .vocabulary import predict, vocabulary_hash

        def normalizer(text):
            return predict(text, vocabulary)

        policy = "train_lexicon_v1:" + vocabulary_hash(vocabulary)
    else:
        normalizer = normalize_nouns
        policy = "noun_alias_v1"
    blob = path.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    try:
        decoded = blob.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataError("CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
    records: list[Record] = []
    seen: set[str] = set()
    try:
        if columns is None and reader.fieldnames != FIELDS:
            raise DataError(f"Expected columns in this order: {','.join(FIELDS)}")
        mapping = columns if columns is not None else {f: f for f in FIELDS}
        if reader.fieldnames is None or len(set(reader.fieldnames)) != len(
            reader.fieldnames
        ):
            raise DataError("CSV requires unique source headers")
        if not set(mapping.values()) <= set(reader.fieldnames):
            raise DataError("CSV is missing mapped source columns")
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise DataError(f"CSV row {row_number}: wrong number of fields")
            row = {f: row.get(mapping.get(f), "") for f in FIELDS + ["narrative"]}
            # Preserve narrative text verbatim; identifiers are validated, not cleaned.
            for field in ("record_id", "asset_id") + (
                ("component",) if "component" in mapping else ()
            ):
                value = row[field]
                if not value.strip() or value != value.strip():
                    raise DataError(f"CSV row {row_number}: invalid {field}")
            text_field = "narrative" if "narrative" in mapping else "issue"
            if not row[text_field].strip():
                raise DataError(f"CSV row {row_number}: missing {text_field}")
            if row["record_id"] in seen:
                raise DataError(f"CSV row {row_number}: duplicate record_id")
            try:
                event_date = date.fromisoformat(row["event_date"])
                if event_date.isoformat() != row["event_date"]:
                    raise ValueError("date must use YYYY-MM-DD")
            except ValueError as exc:
                raise DataError(f"CSV row {row_number}: invalid event_date") from exc
            seen.add(row["record_id"])
            records.append(
                Record(
                    record_id=row["record_id"],
                    event_date=event_date,
                    asset_id=row["asset_id"],
                    component=row["component"],
                    issue_raw=row["issue"],
                    action_raw=row["action"],
                    issue_normalized=normalizer(row["issue"]),
                    action_normalized=normalizer(row["action"]),
                    evidence=Evidence(
                        path.name, digest, row_number, data_kind, dict(mapping)
                    ),
                    narrative_raw=row["narrative"],
                    normalization_policy=policy,
                )
            )
    except csv.Error as exc:
        raise DataError(f"Malformed CSV near physical line {reader.line_num}") from exc
    if not records:
        raise DataError("CSV contains no maintenance records")
    return records
