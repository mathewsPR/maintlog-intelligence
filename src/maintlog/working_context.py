"""Lossless audit remains outside compact model working history."""

from copy import deepcopy


def compact_context(context: dict) -> dict:
    """Compact resolved history; retain unresolved records and latest result.

    Accepted excerpts remain visible. Full record observations remain in the
    agent state and audit trace. This is not a relevance or recall decision.
    """
    compact = deepcopy(context)
    observations = compact.get("observations", [])
    accepted = {
        item.get("result", {}).get("record_id")
        for item in observations
        if isinstance(item.get("result"), dict)
        and "accepted_proposal" in item["result"]
    }
    retained = []
    for index, item in enumerate(observations):
        latest = index == len(observations) - 1
        result = item.get("result", {})
        if not latest and isinstance(result, dict):
            rejected_id = (
                result.get("rejected_decision", {}).get("args", {}).get("record_id")
            )
            if "error" in result and rejected_id in accepted:
                continue
            if item.get("tool") == "record" and result.get("record_id") in accepted:
                item = {
                    "tool": "record",
                    "result": {
                        key: result[key]
                        for key in ("record_id", "asset_id", "event_date")
                        if key in result
                    },
                    "note": "Full source is retained in the audit trace; accepted excerpts follow.",
                }
        retained.append(item)
    compact["observations"] = retained
    compact["working_context_policy"] = "resolved_history_v1"
    return compact
