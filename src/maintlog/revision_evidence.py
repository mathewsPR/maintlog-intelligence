"""Bounded source excerpt alternatives for two targeted evidence concerns."""

import re

from .evidence_review import CORRECTIVE
from .extraction import CUES, has_unnegated_status_cue

# Conservative exceptions; this is not a complete sentence parser.
ABBREVIATIONS = {"fwd", "aft", "ref", "no", "nos", "approx", "assy", "fig", "dr"}
BOUNDARY = re.compile(r"[.;!?](?=\s|$)")
REPORTING = re.compile(r"\b(?:had|reported|observed|experienced)\s+", re.I)


def excerpt_options(source: dict, revision: dict) -> dict:
    """Offer original spans and source alternatives without choosing for the model."""
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
                    # Offer both versions; do not automatically remove context.
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
    """Lock unchanged evidence while offering original and source alternatives."""
    from .decision_schema import obj
    from .revision_component import component_revision_candidate

    options = excerpt_options(source, revision)
    if not options:
        return None

    previous = revision["previous_proposal"]
    fields = {}
    shown = {}
    component = component_revision_candidate(source, revision)

    for name, span in previous["fields"].items():
        if span is None:
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
            dict(
                choice,
                quote=source[choice["field"]][choice["start"] : choice["end"]],
            )
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
