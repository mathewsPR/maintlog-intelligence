"""Durable request accounting for a sequential evaluation runner."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def append_event(path, event):
    if path is None:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp_utc": datetime.now(UTC).isoformat(), **event}
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def normalized_usage(usage):
    usage = usage if isinstance(usage, dict) else {}
    names = {
        "input_tokens": "prompt_tokens",
        "output_tokens": "completion_tokens",
        "total_tokens": "total_tokens",
    }
    result = {}
    for target, source in names.items():
        value = usage.get(source)
        result[target] = value if type(value) is int and value >= 0 else None
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    result["cached_input_tokens"] = (
        cached if type(cached) is int and cached >= 0 else None
    )
    result["usage_available"] = all(result[key] is not None for key in names)
    return result


def summarize_usage(path, run_id=None):
    starts, ends = {}, {}
    target = Path(path)
    if target.exists():
        with target.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, start=1):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid token log line {number}; preserve and inspect the log"
                    ) from exc
                if run_id is not None and event.get("run_id") != run_id:
                    continue
                request_id = event["request_id"]
                if event["event"] == "request_started":
                    if request_id in starts:
                        raise ValueError("Duplicate request start")
                    starts[request_id] = event
                elif event["event"] == "request_finished":
                    if request_id in ends:
                        raise ValueError("Duplicate request finish")
                    ends[request_id] = event
    if not set(ends) <= set(starts):
        raise ValueError("Token log contains a finish without a start")
    missing = sum(not ends.get(key, {}).get("usage_available", False) for key in starts)
    result = {
        "requests_started": len(starts),
        "responses_received": sum(
            e["status"] == "response_received" for e in ends.values()
        ),
        "transport_failures": sum(
            e["status"] == "request_failed" for e in ends.values()
        ),
        "requests_without_finish": len(set(starts) - set(ends)),
        "requests_without_usage": missing,
        "token_totals_complete": missing == 0,
        "interpretation": "Known usage includes responses rejected later by decision validation. Missing usage is unknown, never zero. Cached input is a subset of input, not additional tokens.",
    }
    for key in ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens"):
        reported = [e[key] for e in ends.values() if e.get(key) is not None]
        result["known_" + key] = sum(reported)
    return result
