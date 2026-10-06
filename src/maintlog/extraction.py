"""Shared source-span validation and conservative classification constraints."""

import re

from .domain import Record

FIELD_NAMES = {"component", "problem", "action"}
STATUSES = {"unknown", "planned", "attempted", "completed", "verified"}

STATUS_GUIDANCE = (
    "action_status describes execution of the selected action, not repair success. "
    "unknown: insufficient explicit evidence. planned: intended or scheduled work. "
    "attempted: explicitly tried or attempted work, without stated completion. "
    "completed: explicitly performed work, even if the problem persists. "
    "verified: explicit verification of the selected action; never infer verification "
    "from work being completed or from an unrelated confirmation."
)

STATUS_SUPPORT = {
    "planned": "explicit planning or scheduling wording",
    "attempted": "explicit tried or attempted wording",
    "completed": "explicit performed or completed work wording",
    "verified": "explicit verification wording for the selected action",
}

ORIGINS = {
    "component": {"component", "issue_raw", "narrative_raw"},
    "problem": {"issue_raw", "narrative_raw"},
    "action": {"action_raw", "narrative_raw"},
}

# These rules reject a few clear contradictions, not all semantic errors.
ACTION_PREFIX = re.compile(
    r"^(?:(?:plan(?:ned)?\s+to\s+)?"
    r"(?:repl|replace|replaced|lubricated|checked|repaired|installed|"
    r"removed|found|resecured|performed))\b",
    re.I,
)

CUES = {
    "planned": re.compile(
        r"\b(?:plan(?:ned)?|scheduled|will|to be)\b",
        re.I,
    ),
    "attempted": re.compile(
        r"\b(?:attempt(?:ed)?|tried)\b",
        re.I,
    ),
    "completed": re.compile(
        r"\b(?:completed|replaced|repaired|installed|removed|checked|inspected|"
        r"lubricated|resecured|performed|drilled)\b",
        re.I,
    ),
    "verified": re.compile(
        r"\b(?:verified|confirmed|passed|validated)\b",
        re.I,
    ),
}


def has_unnegated_status_cue(text: str, status: str) -> bool:
    """Conservative clause-local check, not full semantic verification."""
    for clause in re.split(r"[.;!?\n]", text):
        for cue in CUES[status].finditer(clause):
            prefix = clause[: cue.start()]
            suffix = clause[cue.end() :]

            negated_before = re.search(
                r"\b(?:no|not|never|without|cannot|can't|couldn't|"
                r"didn't|wasn't|weren't|hasn't|haven't|hadn't)"
                r"\s+(?:\w+\s+){0,3}$",
                prefix,
                re.I,
            )
            negated_after = re.match(
                r"\s+(?:(?:was|were|is|are|has|have|had)\s+)?"
                r"(?:not|never)\b",
                suffix,
                re.I,
            )

            if not negated_before and not negated_after:
                return True

    return False


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
        raise ValueError(
            f"{name}: invalid source span keys; received={sorted(keys)}. "
            'For a unique quote use only {"field": "source field", "quote": "exact text"}; '
            "do not send source_column. For repeated text use field/start/end."
        )

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
            raise ValueError(
                f"{name}: invalid span offsets; "
                f"require 0 <= start < end <= {len(source)}. "
                "Use field/quote for unique text."
            )

        quote = source[start:end]
        if "quote" in span and span["quote"] != quote:
            raise ValueError(
                f"{name}: stored quote disagrees with source offsets; "
                "remove offsets and use field/quote for unique text."
            )
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
    record: Record,
    fields: dict,
    status: str,
    *,
    human_review: bool = False,
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

        if not has_unnegated_status_cue(text, status):
            raise ValueError(
                f"action_status={status!r} lacks unnegated explicit support in "
                f"the selected action quote {text!r}; "
                f"requires {STATUS_SUPPORT[status]}. "
                "Correct the status using explicit execution evidence, "
                "or choose unknown. "
                "A persistent problem or unconfirmed repair outcome does not "
                "change performed work into attempted work. "
                "Do not repeat the rejected proposal."
            )

        if status == "completed" and CUES["planned"].search(text):
            raise ValueError("planned wording cannot establish completion")

    return resolved
