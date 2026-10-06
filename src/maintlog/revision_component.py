"""revision_component.py Source-derived component boundary correction for an omitted subpart."""

from .evidence_review import SUBPART


def component_revision_candidate(source: dict, revision: dict) -> dict | None:
    """Extend only the original source span by the flagged adjacent subpart.

    No gold labels, inferred names, normalization, or condition words are used.
    Other warnings remain unresolved by this narrow boundary correction.
    """
    if not any(
        item.get("field") == "component"
        and item.get("code") == "possible_omitted_subpart"
        for item in revision.get("concerns", [])
    ):
        return None

    previous = revision.get("previous_proposal", {})
    span = previous.get("fields", {}).get("component")

    if not isinstance(span, dict):
        return None

    if previous.get("record_id") != source.get("record_id"):
        raise ValueError("component revision source record mismatch")

    field, start, end = span["field"], span["start"], span["end"]
    text = source[field]

    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(text)
        or text[start:end] != span["quote"]
    ):
        raise ValueError("component revision span disagrees with source")

    match = SUBPART.match(text[end:])
    if match is None:
        raise ValueError("flagged subpart continuation is absent")

    return {
        "field": field,
        "start": start,
        "end": end + match.end(),
    }
