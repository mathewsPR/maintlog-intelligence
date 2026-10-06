"""Private request worker: parent process owns cancellation and the total deadline."""

import json
import sys
import time
import urllib.request
import uuid

from .backends import LocalServer, _NoRedirect
from .token_log import append_event, normalized_usage


def main():
    log_path = None
    metadata = None
    started = time.monotonic()
    finished = False
    try:
        payload = json.load(sys.stdin)
        LocalServer(payload["base_url"])  # Validate again in this process.
        log_path = payload.get("token_log_path")
        metadata = {
            "request_id": uuid.uuid4().hex,
            "run_id": payload.get("run_id"),
            "request_number": payload.get("request_number"),
            "provider": "llama.cpp",
            "model": payload["body"]["model"],
            "stage": payload.get("stage"),
            "record_id": payload.get("record_id"),
        }
        append_event(log_path, {**metadata, "event": "request_started"})
        request = urllib.request.Request(
            payload["base_url"].rstrip("/") + "/chat/completions",
            data=json.dumps(payload["body"]).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )
        with opener.open(request, timeout=payload["timeout"]) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("response too large")
        decoded = json.loads(raw)
        append_event(
            log_path,
            {
                **metadata,
                "event": "request_finished",
                "status": "response_received",
                "elapsed_seconds": round(time.monotonic() - started, 3),
                **normalized_usage(decoded.get("usage")),
            },
        )
        finished = True
        print(json.dumps(decoded))
        return 0
    except Exception as exc:
        if metadata is not None and not finished:
            try:
                append_event(
                    log_path,
                    {
                        **metadata,
                        "event": "request_finished",
                        "status": "request_failed",
                        "error_type": type(exc).__name__,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        **normalized_usage(None),
                    },
                )
            except OSError:
                pass
        # Do not print maintenance narratives or transport bodies on failure.
        print('{"error":"request_failed"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
