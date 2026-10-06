"""Lossless audit remains outside compact model working history."""

import json
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

    # Preserve one copy of each identical successful search result. The full
    # observations and trace remain unchanged outside this copied context.
    last_search = {}
    for index, item in enumerate(observations):
        result = item.get("result")
        if (
            item.get("tool") == "search"
            and isinstance(result, dict)
            and "hits" in result
            and "error" not in result
        ):
            signature = json.dumps(
                result,
                sort_keys=True,
                ensure_ascii=False,
            )
            last_search[signature] = index

    duplicate_searches = 0
    retained = []

    for index, item in enumerate(observations):
        result = item.get("result", {})
        if (
            item.get("tool") == "search"
            and isinstance(result, dict)
            and "hits" in result
            and "error" not in result
        ):
            signature = json.dumps(
                result,
                sort_keys=True,
                ensure_ascii=False,
            )
            if last_search[signature] != index:
                duplicate_searches += 1
                continue

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
                }
            elif "accepted_proposal" in result:
                item = {
                    "tool": item.get("tool", "extract"),
                    "result": {
                        key: result[key]
                        for key in ("record_id", "accepted_proposal")
                        if key in result
                    },
                }

        retained.append(item)

    compact["observations"] = retained
    compact["working_context_policy"] = "resolved_history_v3"
    compact["working_context_notice"] = (
        "Full sources and prior decisions remain in the audit. Accepted excerpts "
        "are unreviewed proposals, not established facts. Use record to reread "
        "source details when needed."
    )

    if duplicate_searches:
        compact["search_progress_notice"] = {
            "duplicate_results_compacted": duplicate_searches,
            "instruction": (
                "Repeated searches returned identical evidence. Repeating them "
                "does not address missing extraction evidence. Inspect pending "
                "retrieved records, refine the query when justified, or finish "
                "with supported records when task requirements are met. Null "
                "fields mean no excerpt was selected, not proof no work occurred."
            ),
        }

    return compact
