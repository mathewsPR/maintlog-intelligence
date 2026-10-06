"""Bounded source excerpt alternatives and missing-action reconsideration."""

import re

from .evidence_review import CORRECTIVE
from .extraction import CUES, has_unnegated_status_cue

ABBREVIATIONS = {"fwd", "aft", "ref", "no", "nos", "approx", "assy", "fig", "dr"}
BOUNDARY = re.compile(r"[.;!?](?=\s|$)")
REPORTING = re.compile(r"\b(?:had|reported|observed|experienced)\s+", re.I)


def excerpt_options(source: dict, revision: dict) -> dict:
    """Return original spans plus alternatives; never select for the model."""
    previous = revision["previous_proposal"]
    if previous["record_id"] != source["record_id"]:
        raise ValueError("evidence revision source record mismatch")

    options = {}
    codes = {(item["field"], item["code"]) for item in revision["concerns"]}

    for name, code in (
        ("problem", "possible_diagnosis_in_symptom_field"),
        ("action", "action_contains_administrative_heading"),
    ):
        if (name, code) not in codes:
            continue

        original = previous["fields"][name]
        if original is None:
            continue

        field = original["field"]
        text = source[field]
        start, end = original["start"], original["end"]
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(text)
            or text[start:end] != original["quote"]
        ):
            raise ValueError("evidence revision span disagrees with source")

        heading = CORRECTIVE.search(text)
        if heading is None:
            continue

        choices = [{"field": field, "start": start, "end": end}]
        lower, upper = (
            (0, heading.start()) if name == "problem" else (heading.end(), len(text))
        )

        cursor = lower
        segments = []
        for match in BOUNDARY.finditer(text, lower, upper):
            position = match.start()
            if text[position] == ".":
                word = re.search(r"([A-Za-z]+)$", text[cursor:position])
                if word and word.group(1).casefold() in ABBREVIATIONS:
                    continue
            segments.append((cursor, position))
            cursor = match.end()
        segments.append((cursor, upper))

        for left, right in segments[:4]:
            while left < right and text[left].isspace():
                left += 1
            while right > left and text[right - 1].isspace():
                right -= 1
            if left == right:
                continue

            variants = [(left, right)]
            if name == "problem":
                reporting = REPORTING.search(text, left, right)
                if reporting is not None and reporting.end() < right:
                    variants.append((reporting.end(), right))

            for begin, finish in variants:
                quote = text[begin:finish]
                status = previous["action_status_proposal"]
                if name == "action" and status != "unknown":
                    if not has_unnegated_status_cue(quote, status):
                        continue
                    if status == "completed" and CUES["planned"].search(quote):
                        continue

                option = {"field": field, "start": begin, "end": finish}
                if option not in choices and len(choices) < 6:
                    choices.append(option)

        if len(choices) > 1:
            options[name] = choices

    return options


def excerpt_contract(source: dict, revision: dict):
    """Lock unchanged evidence while offering source-backed alternatives."""
    from .decision_schema import obj
    from .revision_component import component_revision_candidate

    options = excerpt_options(source, revision)
    if not options:
        return omitted_action_contract(source, revision)

    previous = revision["previous_proposal"]
    fields = {}
    shown = {}
    omission = omitted_action_contract(source, revision)
    component = component_revision_candidate(source, revision)

    for name, span in previous["fields"].items():
        if span is None:
            if name == "action" and omission is not None:
                fields[name] = omission[0]["properties"]["args"]["properties"][
                    "fields"
                ]["properties"]["action"]
                shown[name] = omission[1]["action"]
            else:
                fields[name] = {"type": "null"}
            continue

        choices = options.get(
            name, [{key: span[key] for key in ("field", "start", "end")}]
        )
        if name == "component" and component is not None:
            choices = [*choices, component]

        fields[name] = {
            "anyOf": [
                obj(
                    {
                        key: {
                            "type": "string" if key == "field" else "integer",
                            "enum": [value],
                        }
                        for key, value in choice.items()
                    }
                )
                for choice in choices
            ]
        }
        shown[name] = [
            dict(choice, quote=source[choice["field"]][choice["start"] : choice["end"]])
            for choice in choices
        ]

    schema = obj(
        {
            "tool": {"type": "string", "enum": ["extract"]},
            "args": obj(
                {
                    "record_id": {"type": "string", "enum": [source["record_id"]]},
                    "fields": obj(fields),
                    "action_status": {
                        "type": "string",
                        "enum": [previous["action_status_proposal"]],
                    },
                }
            ),
        }
    )
    return schema, shown


def omitted_action_contract(source: dict, revision: dict):
    """Permit missing-action reconsideration; preserve status and other evidence."""
    from .decision_schema import obj
    from .evidence_policy import source_record
    from .extraction import ORIGINS, resolve_span
    from .revision_component import component_revision_candidate

    previous = revision["previous_proposal"]
    if previous["record_id"] != source["record_id"]:
        raise ValueError("evidence revision source record mismatch")

    if previous["fields"]["action"] is not None or not any(
        concern.get("field") == "action"
        and concern.get("code") == "possible_omitted_work"
        for concern in revision.get("concerns", [])
    ):
        return None

    if previous["action_status_proposal"] != "unknown":
        raise ValueError("null action revision requires unknown status")

    record = source_record(source)
    component = component_revision_candidate(source, revision)
    fields = {}

    for name, span in previous["fields"].items():
        resolved = resolve_span(record, span, name)

        if name == "action":
            fields[name] = {
                "anyOf": [
                    {"type": "null"},
                    obj(
                        {
                            "field": {"type": "string", "enum": sorted(ORIGINS[name])},
                            "quote": {"type": "string", "minLength": 1},
                        }
                    ),
                    obj(
                        {
                            "field": {"type": "string", "enum": sorted(ORIGINS[name])},
                            "start": {"type": "integer", "minimum": 0},
                            "end": {"type": "integer", "minimum": 1},
                        }
                    ),
                ]
            }
        elif resolved is None:
            fields[name] = {"type": "null"}
        else:
            choices = [{key: resolved[key] for key in ("field", "start", "end")}]
            if name == "component" and component is not None:
                choices.append(component)

            fields[name] = {
                "anyOf": [
                    obj(
                        {
                            key: {
                                "type": "string" if key == "field" else "integer",
                                "enum": [value],
                            }
                            for key, value in choice.items()
                        }
                    )
                    for choice in choices
                ]
            }

    schema = obj(
        {
            "tool": {"type": "string", "enum": ["extract"]},
            "args": obj(
                {
                    "record_id": {"type": "string", "enum": [source["record_id"]]},
                    "fields": obj(fields),
                    "action_status": {"type": "string", "enum": ["unknown"]},
                }
            ),
        }
    )
    return schema, {
        "action": (
            "Select exact source evidence or retain null. Preserve unknown "
            "status and unflagged fields. Any flagged component correction "
            "must use its supplied source-backed boundary choice."
        )
    }
