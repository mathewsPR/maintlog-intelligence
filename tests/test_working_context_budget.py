"""Compact model history without modifying accepted evidence or audit state."""

import json
import unittest
from copy import deepcopy

from maintlog.working_context import compact_context


class WorkingContextBudgetTests(unittest.TestCase):
    def context(self):
        return {
            "workflow_progress": {"pending_candidate_inspection": ["R2"]},
            "observations": [
                {
                    "tool": "record",
                    "result": {
                        "record_id": "R1",
                        "asset_id": "A1",
                        "narrative_raw": "x" * 2000,
                    },
                },
                {
                    "tool": "extract",
                    "result": {
                        "record_id": "R1",
                        "accepted_proposal": {
                            "fields": {
                                "component": None,
                                "problem": None,
                                "action": {
                                    "field": "narrative_raw",
                                    "quote": "RESECURED CONNECTOR",
                                },
                            },
                            "action_status": "completed",
                        },
                        "review_status": "unreviewed",
                        "note": "Stored evidence metadata is added by the application.",
                    },
                },
                {
                    "tool": "record",
                    "result": {
                        "record_id": "R2",
                        "narrative_raw": "Unresolved source",
                    },
                },
            ],
        }

    def test_reduces_context_preserves_quotes_and_progress(self):
        context = self.context()
        original = deepcopy(context)
        result = compact_context(context)
        self.assertEqual(context, original)
        self.assertLess(len(json.dumps(result)), len(json.dumps(context)))
        self.assertEqual(result["workflow_progress"], context["workflow_progress"])
        self.assertEqual(
            result["observations"][1]["result"]["accepted_proposal"],
            context["observations"][1]["result"]["accepted_proposal"],
        )
        self.assertNotIn("note", result["observations"][1]["result"])
        self.assertEqual(result["observations"][-1], context["observations"][-1])

    def test_unresolved_and_latest_feedback_remain_exact(self):
        context = self.context()
        context["observations"].append(
            {
                "tool": "extract",
                "result": {
                    "error": "invalid quote",
                    "rejected_decision": {
                        "tool": "extract",
                        "args": {"record_id": "R2"},
                    },
                },
            }
        )
        result = compact_context(context)
        self.assertEqual(result["observations"][-2:], context["observations"][-2:])

    def test_latest_accepted_response_is_preserved(self):
        context = self.context()
        context["observations"].pop()
        result = compact_context(context)
        self.assertEqual(result["observations"][-1], context["observations"][-1])
        self.assertIn("unreviewed", result["working_context_notice"])


if __name__ == "__main__":
    unittest.main()
