"""Durable accounting handles unknown usage and corrupted logs."""

import tempfile
import unittest
from pathlib import Path

from maintlog.token_log import append_event, normalized_usage, summarize_usage


class TokenLogTests(unittest.TestCase):
    def test_known_usage_and_unfinished_request(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "usage.jsonl"
            append_event(
                path, {"event": "request_started", "request_id": "1", "run_id": "a"}
            )
            usage = normalized_usage(
                {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "prompt_tokens_details": {"cached_tokens": 80},
                }
            )
            append_event(
                path,
                {
                    "event": "request_finished",
                    "request_id": "1",
                    "run_id": "a",
                    "status": "response_received",
                    **usage,
                },
            )
            append_event(
                path, {"event": "request_started", "request_id": "2", "run_id": "b"}
            )
            summary = summarize_usage(path)
            self.assertEqual(summary["known_total_tokens"], 120)
            self.assertEqual(summary["known_input_tokens"], 100)
            self.assertEqual(summary["known_cached_input_tokens"], 80)
            self.assertEqual(summary["requests_without_usage"], 1)
            self.assertFalse(summary["token_totals_complete"])
            self.assertTrue(summarize_usage(path, "a")["token_totals_complete"])

    def test_missing_usage_is_null(self):
        usage = normalized_usage(None)
        self.assertIsNone(usage["input_tokens"])
        self.assertIsNone(usage["output_tokens"])
        self.assertFalse(usage["usage_available"])

    def test_corrupt_log_refuses_undercount(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "usage.jsonl"
            path.write_text('{"truncated":', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid token log"):
                summarize_usage(path)
