"""Model input contract, separate from persisted evidence spans."""

from .extraction import STATUS_GUIDANCE


def obj(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


TEXT = {"type": "string"}
SPAN = {
    "anyOf": [
        {"type": "null"},
        obj(
            {
                "field": {
                    "type": "string",
                    "enum": ["component", "narrative_raw", "issue_raw", "action_raw"],
                },
                "quote": TEXT,
            }
        ),
        obj(
            {
                "field": {
                    "type": "string",
                    "enum": ["component", "narrative_raw", "issue_raw", "action_raw"],
                },
                "start": {"type": "integer", "minimum": 0},
                "end": {"type": "integer", "minimum": 1},
            }
        ),
    ]
}
ARGS = {
    "assets": obj({"offset": {"type": "integer", "minimum": 0}}, []),
    "search": obj(
        {"query": TEXT, "top_k": {"type": "integer", "minimum": 1, "maximum": 5}},
        ["query"],
    ),
    "record": obj({"record_id": TEXT}),
    "extract": obj(
        {
            "record_id": TEXT,
            "fields": obj({name: SPAN for name in ("component", "problem", "action")}),
            "action_status": {
                "type": "string",
                "enum": ["unknown", "planned", "attempted", "completed", "verified"],
                "description": STATUS_GUIDANCE,
            },
        }
    ),
    "aggregate": obj({}),
    "clarify": obj({"question": TEXT}),
    "abstain": obj({"reason": TEXT}),
    "finish": obj({"record_ids": {"type": "array", "items": TEXT, "maxItems": 50}}),
}
DECISION_SCHEMA = {
    "anyOf": [
        obj({"tool": {"type": "string", "enum": [name]}, "args": schema})
        for name, schema in ARGS.items()
    ]
}


def _valid(value, schema):
    if "anyOf" in schema:
        return any(_valid(value, branch) for branch in schema["anyOf"])
    kind = schema["type"]
    types = {
        "null": value is None,
        "object": isinstance(value, dict),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "array": isinstance(value, list),
    }
    if not types[kind] or ("enum" in schema and value not in schema["enum"]):
        return False
    if kind == "object":
        return set(schema["required"]) <= set(value) <= set(
            schema["properties"]
        ) and all(_valid(v, schema["properties"][k]) for k, v in value.items())
    if kind == "integer":
        return schema.get("minimum", value) <= value <= schema.get("maximum", value)
    if kind == "array":
        return len(value) <= schema.get("maxItems", len(value)) and all(
            _valid(v, schema["items"]) for v in value
        )
    return True


def validate_decision(value):
    """Fail closed even if the server ignores its requested grammar."""
    if not _valid(value, DECISION_SCHEMA):
        raise ValueError("model decision violates the tool input schema")
    return value
