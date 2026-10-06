"""Source-computed occurrence choices for ambiguous extraction quotes."""

from .decision_schema import obj, validate_decision
from .evidence_policy import source_record
from .extraction import ORIGINS, resolve_span


def occurrence_contract(source: dict, feedback: dict):
    """Lock valid fields and let the model select exact repeated occurrences."""
    decision = feedback.get("rejected_decision")
    try:
        validate_decision(decision)
    except (ValueError, TypeError, KeyError):
        return None
    if decision["tool"] != "extract":
        return None
    args = decision["args"]
    if args["record_id"] != source.get("record_id"):
        return None

    record = source_record(source)
    fields, shown = {}, {}
    ambiguous = False
    for name, supplied in args["fields"].items():
        try:
            resolved = resolve_span(record, supplied, name)
        except ValueError:
            if not isinstance(supplied, dict) or set(supplied) != {"field", "quote"}:
                return None
            field, quote = supplied["field"], supplied["quote"]
            if (
                field not in ORIGINS[name]
                or not isinstance(quote, str)
                or not quote.strip()
            ):
                return None
            text = source.get(field, "")
            if not isinstance(text, str):
                return None
            choices = []
            cursor = 0
            while True:
                start = text.find(quote, cursor)
                if start < 0:
                    break
                choice = {"field": field, "start": start, "end": start + len(quote)}
                try:
                    resolve_span(record, choice, name)
                except ValueError:
                    # Never repair a quote that omits negation or violates field rules.
                    return None
                choices.append(choice)
                if len(choices) > 8:
                    return None
                cursor = start + 1
            if len(choices) < 2:
                return None
            ambiguous = True
        else:
            if resolved is None:
                fields[name] = {"type": "null"}
                continue
            choices = [{key: resolved[key] for key in ("field", "start", "end")}]

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
                surrounding_text=source[choice["field"]][
                    max(0, choice["start"] - 60) : choice["end"] + 60
                ],
            )
            for choice in choices
        ]

    if not ambiguous:
        return None
    return obj(
        {
            "tool": {"type": "string", "enum": ["extract"]},
            "args": obj(
                {
                    "record_id": {"type": "string", "enum": [source["record_id"]]},
                    "fields": obj(fields),
                    "action_status": {
                        "type": "string",
                        "enum": [args["action_status"]],
                    },
                }
            ),
        }
    ), shown
