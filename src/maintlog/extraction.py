"""Shared source-span validation and conservative classification constraints."""

import re

from .domain import Record

FIELD_NAMES = {"component", "problem", "action"}
STATUSES = {"unknown", "planned", "attempted", "completed", "verified"}
ORIGINS = {
    "component": {"component", "issue_raw", "narrative_raw"},
    "problem": {"issue_raw", "narrative_raw"},
    "action": {"action_raw", "narrative_raw"},
}
# These rules reject a few clear contradictions, not all semantic errors.
ACTION_PREFIX = re.compile(
    r"^(?:(?:plan(?:ned)?\s+to\s+)?(?:repl|replace|replaced|lubricated|checked|repaired|installed|removed))\b",
    re.I,
)
CUES = {
    "planned": re.compile(r"\b(?:plan(?:ned)?|scheduled|will|to be)\b", re.I),
    "attempted": re.compile(r"\b(?:attempt(?:ed)?|tried)\b", re.I),
    "completed": re.compile(
        r"\b(?:completed|replaced|repaired|installed|removed|checked|inspected|lubricated)\b",
        re.I,
    ),
    "verified": re.compile(r"\b(?:verified|confirmed|passed|validated)\b", re.I),
}
NEGATED_STATUS = re.compile(
    r"\b(?:not|never|unconfirmed|unverified)\b|\bno\s+(?:successful\s+)?(?:repair|verification|confirmation)\b",
    re.I,
)


def resolve_span(record: Record, span: dict | None, name: str) -> dict | None:
    if span is None:
        return None
    if not isinstance(span, dict):
        raise ValueError("invalid source span")
    # Stored spans may carry computed quote/column metadata. Never trust it.
    keys = set(span)
    offset_mode = {"field", "start", "end"} <= keys
    allowed = (
        {"field", "start", "end", "quote", "source_column"}
        if offset_mode
        else {"field", "quote"}
    )
    if not keys <= allowed or (not offset_mode and keys != allowed):
        raise ValueError("invalid source span keys")
    field = span["field"]
    if not isinstance(field, str) or field not in ORIGINS[name]:
        raise ValueError(f"{name} cannot use this source field")
    source = getattr(record, field)
    if offset_mode:
        start, end = span["start"], span["end"]
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(source)
        ):
            raise ValueError("invalid span offsets")
        quote = source[start:end]
        if "quote" in span and span["quote"] != quote:
            raise ValueError("stored quote disagrees with source offsets")
    else:
        quote = span["quote"]
        if not isinstance(quote, str) or not quote.strip() or len(quote) > 6000:
            raise ValueError("invalid quote")
        start = source.find(quote)
        if start < 0 or source.find(quote, start + 1) >= 0:
            raise ValueError(
                "quote must occur exactly once; use offsets for repeated text"
            )
        end = start + len(quote)
    if name in {"problem", "action"} and re.search(
        r"\b(?:no|not|without)\s+(?:\w+\s+){0,2}$",
        source[max(0, start - 30) : start],
        re.I,
    ):
        raise ValueError("source span omits nearby negation; include it in the excerpt")
    if not quote.strip():
        raise ValueError("empty source span")
    if name == "component" and ACTION_PREFIX.search(quote.strip()):
        raise ValueError(
            "component starts with an action phrase; select the object only"
        )
    return {
        "field": field,
        "start": start,
        "end": end,
        "quote": quote,
        "source_column": record.evidence.columns.get(field.removesuffix("_raw")),
    }


def validate_fields(
    record: Record, fields: dict, status: str, *, human_review: bool = False
) -> dict:
    if not isinstance(fields, dict) or set(fields) != FIELD_NAMES:
        raise ValueError("fields must contain component, problem and action")
    if not isinstance(status, str) or status not in STATUSES:
        raise ValueError("invalid action status")
    resolved = {name: resolve_span(record, span, name) for name, span in fields.items()}
    if resolved["action"] is None and status != "unknown":
        raise ValueError("unsupported action must have unknown status")
    if status != "unknown" and not human_review:
        text = resolved["action"]["quote"]
        if NEGATED_STATUS.search(text) or not CUES[status].search(text):
            raise ValueError(
                "action status lacks unnegated explicit support; choose unknown"
            )
        if status == "completed" and CUES["planned"].search(text):
            raise ValueError("planned wording cannot establish completion")
    return resolved
