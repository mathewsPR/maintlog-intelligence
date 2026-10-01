"""component_selection.py  Source-backed component selection; no evaluation labels are consulted."""

import re
from copy import deepcopy

from .decision_schema import obj
from .extraction import ORIGINS

# Conservative identifier shape: letters and digits with a separator.
# A matching token is a candidate, not proof that it is a component.
IDENTIFIER = re.compile(
    r"(?<![\w-])"
    r"(?=[A-Za-z0-9_-]*[A-Za-z])"
    r"(?=[A-Za-z0-9_-]*[0-9])"
    r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+"
    r"(?![\w-])"
)


def component_candidates(record: dict) -> dict[str, dict]:
    """Return deterministic IDs mapped to exact source spans."""
    candidates = []
    structured = record.get("component", "")

    if isinstance(structured, str) and structured.strip():
        start = len(structured) - len(structured.lstrip())
        end = len(structured.rstrip())
        candidates.append(
            {
                "field": "component",
                "start": start,
                "end": end,
                "quote": structured[start:end],
            }
        )

    for field in sorted(ORIGINS["component"] - {"component"}):
        source = record.get(field, "")
        if not isinstance(source, str):
            raise ValueError(f"{field} must be a string")

        for match in IDENTIFIER.finditer(source):
            candidates.append(
                {
                    "field": field,
                    "start": match.start(),
                    "end": match.end(),
                    "quote": match.group(),
                }
            )

    # Stable order and no duplicated source locations.
    unique = {}
    for span in candidates:
        key = (span["field"], span["start"], span["end"])
        unique[key] = span

    return {f"c{index}": span for index, span in enumerate(unique.values(), start=1)}


def selection_schema(record_id: str, extract_args: dict, candidates: dict) -> dict:
    """Copy the extraction contract and constrain only component selection."""
    args = deepcopy(extract_args)
    args["properties"]["record_id"] = {
        "type": "string",
        "enum": [record_id],
    }
    args["properties"]["fields"]["properties"]["component"] = {
        "anyOf": [
            {"type": "null"},
            {"type": "string", "enum": list(candidates)},
        ]
    }

    # In this experimental mode, the model copies problem/action quotes.
    # The application resolves their offsets through validate_fields.
    for name in ("problem", "action"):
        args["properties"]["fields"]["properties"][name] = {
            "anyOf": [
                {"type": "null"},
                obj(
                    {
                        "field": {
                            "type": "string",
                            "enum": sorted(ORIGINS[name]),
                        },
                        "quote": {
                            "type": "string",
                            "minLength": 1,
                        },
                    }
                ),
            ]
        }

    return obj(
        {
            "tool": {"type": "string", "enum": ["extract"]},
            "args": args,
        }
    )


def resolve_component_choice(decision: dict, candidates: dict) -> dict:
    """Translate a selected ID into the existing input-span contract."""
    translated = deepcopy(decision)

    if translated.get("tool") != "extract":
        raise ValueError("component selector must return extract")

    fields = translated["args"]["fields"]
    choice = fields["component"]

    if choice is None:
        return translated

    if not isinstance(choice, str) or choice not in candidates:
        raise ValueError("component must select a supplied candidate ID or null")

    span = candidates[choice]
    fields["component"] = {
        "field": span["field"],
        "start": span["start"],
        "end": span["end"],
    }
    return translated
