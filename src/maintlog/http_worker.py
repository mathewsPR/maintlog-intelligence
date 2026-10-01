"""Private request worker: parent process owns cancellation and the total deadline."""

import json
import sys
import urllib.request

from .backends import LocalServer, _NoRedirect


def main():
    try:
        payload = json.load(sys.stdin)
        LocalServer(payload["base_url"])  # Validate again in this process.
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
        print(json.dumps(decoded))
        return 0
    except Exception:
        # Do not print maintenance narratives or transport bodies on failure.
        print('{"error":"request_failed"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
