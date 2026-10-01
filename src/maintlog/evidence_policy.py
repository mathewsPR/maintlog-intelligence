"""evidence policy.py  Audited source-span boundary policy and constrained status repair."""

import re
from copy import deepcopy
from types import SimpleNamespace

from .decision_schema import ARGS, obj
from .extraction import CUES, has_unnegated_status_cue, resolve_span

BOUNDARY_POLICY = "terminal_period_v1"

# Conservative exceptions, not a complete abbreviation dictionary.
ABBREVIATIONS = {
    "approx",
    "assy",
    "ave",
    "dept",
    "dr",
    "eg",
    "etc",
    "fig",
    "hr",
    "hrs",
    "ie",
    "inc",
    "max",
    "min",
    "misc",
    "mr",
    "mrs",
    "ms",
    "no",
    "nos",
    "qty",
    "ref",
    "rev",
    "sec",
    "st",
    "temp",
    "vs",
}


def source_record(source: dict):
    """Provide the source attributes required by the shared span validator."""
    return SimpleNamespace(
        component=source.get("component", ""),
        issue_raw=source.get("issue_raw", ""),
        action_raw=source.get("action_raw", ""),
        narrative_raw=source.get("narrative_raw", ""),
        evidence=SimpleNamespace(columns={}),
    )


def adapt_boundaries(decision: dict, source: dict) -> tuple[dict, dict]:
    """Adjust only eligible terminal periods, retaining source offsets."""
    adjusted = deepcopy(decision)
    audit = {
        "policy": BOUNDARY_POLICY,
        "original_decision": deepcopy(decision),
        "changes": [],
    }
    record = source_record(source)

    for name in ("problem", "action"):
        supplied = adjusted["args"]["fields"][name]
        try:
            span = resolve_span(record, supplied, name)
        except (ValueError, TypeError, KeyError):
            # Leave invalid evidence for normal validation and feedback.
            continue

        if span is None:
            continue

        quote = span["quote"]
        match = re.search(r"([A-Za-z][A-Za-z0-9_-]*)\.$", quote)
        if not match:
            continue

        word = match.group(1)
        token_start = match.start(1)

        if (
            len(word) < 3
            or word.casefold() in ABBREVIATIONS
            or (word.isalpha() and word.isupper())
            or (token_start > 0 and quote[token_start - 1] == ".")
        ):
            continue

        text = source.get(span["field"], "")
        end = span["end"]
        if end < len(text) and not text[end].isspace():
            continue

        replacement = {
            "field": span["field"],
            "start": span["start"],
            "end": end - 1,
        }
        verified = resolve_span(record, replacement, name)
        adjusted["args"]["fields"][name] = replacement
        audit["changes"].append(
            {
                "field_name": name,
                "before": span,
                "after": verified,
            }
        )

    return adjusted, audit


def status_repair_contract(
    feedback: dict,
    source: dict,
    *,
    candidates: dict | None = None,
):
    """Build a repair contract only from independently validated evidence."""
    repair = feedback.get("status_repair")
    if not isinstance(repair, dict):
        return None

    rejected = feedback.get("rejected_decision", {})
    if rejected.get("tool") != "extract":
        return None

    args = rejected.get("args", {})
    if args.get("record_id") != source.get("record_id"):
        return None

    fields = args.get("fields")
    if not isinstance(fields, dict) or set(fields) != {
        "component",
        "problem",
        "action",
    }:
        return None

    record = source_record(source)
    try:
        resolved = {
            name: resolve_span(record, span, name) for name, span in fields.items()
        }
    except (ValueError, TypeError, KeyError):
        return None

    validated = repair.get("validated_fields")
    if not isinstance(validated, dict) or set(validated) != set(resolved):
        return None

    for name, span in resolved.items():
        expected = validated[name]
        if span is None:
            if expected is not None:
                return None
        elif not isinstance(expected, dict) or any(
            span[key] != expected.get(key) for key in ("field", "start", "end", "quote")
        ):
            return None

    action = resolved["action"]
    statuses = ["unknown"]
    if action is not None:
        text = action["quote"]
        for status in ("planned", "attempted", "completed", "verified"):
            if has_unnegated_status_cue(text, status):
                if status == "completed" and CUES["planned"].search(text):
                    continue
                statuses.append(status)

    schema = deepcopy(ARGS["extract"])
    schema["properties"]["record_id"] = {
        "type": "string",
        "enum": [source["record_id"]],
    }

    # Literal spans preserve the evidence while the model repairs status.
    locked = {}
    for name, span in fields.items():
        if span is None:
            locked[name] = {"type": "null"}
        else:
            locked[name] = obj(
                {
                    key: {
                        "type": "integer" if type(value) is int else "string",
                        "enum": [value],
                    }
                    for key, value in span.items()
                }
            )

        # A validated null is permitted evidence absence, not proof that
    # the source contains no component. Candidate selection remains optional.
    if fields["component"] is None and candidates:
        locked["component"] = {
            "anyOf": [
                {"type": "null"},
                {"type": "string", "enum": list(candidates)},
            ]
        }

    schema["properties"]["fields"] = obj(locked)
    schema["properties"]["action_status"] = {
        "type": "string",
        "enum": statuses,
    }

    return (
        obj(
            {
                "tool": {"type": "string", "enum": ["extract"]},
                "args": schema,
            }
        ),
        deepcopy(fields),
        statuses,
    )


def validate_status_repair(
    decision: dict,
    locked_fields: dict,
    allowed_statuses: list[str],
    candidates: dict,
) -> None:
    """Reject changed evidence, allowing candidate recovery of a null component."""
    if not isinstance(decision, dict) or decision.get("tool") != "extract":
        raise ValueError("status repair must return an extract decision")

    args = decision.get("args")
    if not isinstance(args, dict):
        raise ValueError("status repair returned invalid arguments")

    fields = args.get("fields")
    if not isinstance(fields, dict) or set(fields) != set(locked_fields):
        raise ValueError("status repair changed locked evidence")

    if args.get("action_status") not in allowed_statuses:
        raise ValueError("status repair returned unsupported status")

    for name in ("problem", "action"):
        if fields[name] != locked_fields[name]:
            raise ValueError("status repair changed locked evidence")

    choice = fields["component"]
    if locked_fields["component"] is None and candidates:
        if choice is not None and (
            not isinstance(choice, str) or choice not in candidates
        ):
            raise ValueError("component must select a supplied candidate or null")
    elif choice != locked_fields["component"]:
        raise ValueError("status repair changed locked component")
