"""Explicit local-server backend and transparent replay fixtures; no auto-connect."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse


class BackendError(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BackendError("local model redirects are disabled")


class DecisionBackend(Protocol):
    label: str

    def decide(self, system: str, context: dict, timeout: float) -> dict: ...


@dataclass
class LocalServer:
    base_url: str = "http://127.0.0.1:8081/v1"
    model: str = "local-model"
    max_tokens: int = 512
    label: str = "local-llama-server"
    request_count: int = field(default=0, init=False)

    def __post_init__(self):
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in (
            "127.0.0.1",
            "localhost",
            "::1",
        ):
            raise BackendError("local backend requires a loopback HTTP URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise BackendError(
                "local URL must not contain credentials, query, or fragment"
            )
        if not 64 <= self.max_tokens <= 2048:
            raise BackendError("max_tokens must be between 64 and 2048")

    def decide(self, system: str, context: dict, timeout: float) -> dict:
        self.request_count += 1
        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
        }
        started = time.monotonic()
        try:
            # A separate request process lets Python terminate a stalled client
            # at a total deadline on Windows and Linux, including slow headers.
            result = subprocess.run(
                [sys.executable, "-m", "maintlog.http_worker"],
                input=json.dumps(
                    {"base_url": self.base_url, "body": body, "timeout": timeout}
                ),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                raise BackendError("local request process failed")
            decoded = json.loads(result.stdout)
            content = decoded["choices"][0]["message"]["content"]
            return {
                "decision": json.loads(content),
                "usage": decoded.get("usage", {}),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "model_called": True,
            }
        except subprocess.TimeoutExpired as exc:
            raise BackendError(
                "local request deadline exceeded; client terminated"
            ) from exc
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise BackendError(
                f"local model request failed ({type(exc).__name__})"
            ) from exc


class Replay:
    """Prewritten decisions exercise graph mechanics, never model intelligence."""

    label = "replay-fixture-no-model"
    request_count = 0

    def __init__(self, decisions: list[dict]):
        self.decisions = iter(decisions)

    @classmethod
    def from_file(cls, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise BackendError("replay fixture must be a JSON decision array")
        return cls(data)

    def decide(self, system: str, context: dict, timeout: float) -> dict:
        try:
            return {
                "decision": next(self.decisions),
                "usage": {},
                "elapsed_seconds": 0,
                "model_called": False,
            }
        except StopIteration as exc:
            raise BackendError("replay fixture exhausted") from exc
