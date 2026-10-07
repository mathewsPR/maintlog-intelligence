"""Regression boundaries for planning scope and tool text limits."""

import unittest

from maintlog.agent import _string
from maintlog.decision_schema import ARGS, TOOL_TEXT_LIMIT, validate_decision
from maintlog.extraction import has_unnegated_status_cue


class ValidationBoundaryTests(unittest.TestCase):
    def test_completed_work_with_separate_future_work(self):
        for text in (
            "Replaced bearing, will monitor",
            "Replaced bearing and will monitor",
            "Bolt found to be loose, tightened",
            "Changed out seal",
            "Swapped pump motor",
            "Will monitor; replaced bearing",
        ):
            with self.subTest(text=text):
                self.assertTrue(has_unnegated_status_cue(text, "completed"))

    def test_future_and_negated_work_do_not_establish_completion(self):
        for text in (
            "Will be replaced",
            "Scheduled to be replaced",
            "Bearing to be replaced",
            "Not replaced",
            "Never changed out seal",
            "Pump motor was not swapped",
            "Bearing was not replaced",
        ):
            with self.subTest(text=text):
                self.assertFalse(has_unnegated_status_cue(text, "completed"))

    def test_imperative_is_not_explicit_planning(self):
        self.assertFalse(has_unnegated_status_cue("replace engine oil", "planned"))

    def test_tool_text_schema_and_runtime_share_limit(self):
        for tool, key in (
            ("search", "query"),
            ("clarify", "question"),
            ("abstain", "reason"),
        ):
            with self.subTest(tool=tool):
                schema = ARGS[tool]["properties"][key]
                self.assertEqual(schema["maxLength"], TOOL_TEXT_LIMIT)
                value = "x" * TOOL_TEXT_LIMIT
                validate_decision({"tool": tool, "args": {key: value}})
                self.assertEqual(_string(value, key), value)
                for invalid in ("", value + "x"):
                    with self.assertRaises(ValueError):
                        validate_decision({"tool": tool, "args": {key: invalid}})
                    with self.assertRaises(ValueError):
                        _string(invalid, key)
