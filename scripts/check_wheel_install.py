"""Check the base wheel and installed CLI in a fresh Python 3.11 environment."""

import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

FIELDS = ("record_id", "event_date", "asset_id", "component", "issue", "action")
ROWS = (
    (
        "SMOKE-001",
        "2026-01-01",
        "PUMP-001",
        "bearing",
        "bearing vibration",
        "inspect bearing",
    ),
    (
        "SMOKE-002",
        "2026-01-02",
        "PUMP-001",
        "bearing",
        "bearing vibration",
        "replace bearing",
    ),
    (
        "SMOKE-003",
        "2026-01-03",
        "PUMP-002",
        "bearing",
        "bearing vibration",
        "inspect bearing",
    ),
    ("SMOKE-004", "2026-01-04", "PUMP-001", "seal", "seal leak", "replace seal"),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def run(command: list[str], cwd: Path) -> None:
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(name, None)
    subprocess.run(command, cwd=cwd, env=environment, check=True, timeout=120)


def check_result(path: Path, source: Path, asset_id: str) -> None:
    result = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(result, dict), "Search output must be a JSON object")
    require(result.get("query") == "bearing vibration", "Query was not preserved")
    require(
        isinstance(result.get("scope"), dict)
        and result["scope"].get("asset_id") == asset_id,
        "Requested asset scope was not preserved",
    )
    require(
        result.get("normalization_policy") == "identity",
        "Requested normalization policy was not preserved",
    )
    expected_count = 3 if asset_id == "PUMP-001" else 0
    require(
        result.get("selected_record_count") == expected_count,
        "Wrong number of records in the requested scope",
    )
    hits = result.get("hits")
    require(isinstance(hits, list), "Search output must contain a hits list")
    expected_ids = {"SMOKE-001", "SMOKE-002"} if expected_count else set()
    found_ids = []
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    expected_rows = {row[0]: (number, row) for number, row in enumerate(ROWS, 2)}
    for hit in hits:
        require(isinstance(hit, dict), "Malformed search hit")
        record = hit.get("record")
        require(isinstance(record, dict), "Search hit must contain a record")
        record_id = record.get("record_id")
        require(record_id in expected_ids, "Unexpected or out-of-scope search hit")
        found_ids.append(record_id)
        require(record.get("asset_id") == asset_id, "Asset restriction was violated")
        score = hit.get("score")
        require(
            type(score) in (int, float) and math.isfinite(score) and score > 0,
            "Search hit must have a positive finite score",
        )
        row_number, row = expected_rows[record_id]
        require(record.get("issue_raw") == row[4], "Source issue was altered")
        require(record.get("action_raw") == row[5], "Source action was altered")
        evidence = record.get("evidence")
        require(isinstance(evidence, dict), "Source evidence is missing")
        require(evidence.get("data_kind") == "synthetic", "Wrong data provenance")
        require(evidence.get("source_sha256") == source_hash, "Wrong source hash")
        require(evidence.get("csv_row") == row_number, "Wrong source row")
    require(set(found_ids) == expected_ids, "Expected matching records are missing")
    require(len(found_ids) == len(set(found_ids)), "Duplicate search hits")


def main() -> int:
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Python 3.11 required")
    project = Path(__file__).resolve().parents[1]
    wheels = list((project / "dist").glob("maintlog_intelligence-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(
            "Build into a clean dist directory; expected exactly one wheel"
        )

    with tempfile.TemporaryDirectory(prefix="maintlog-wheel-") as directory:
        root = Path(directory)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        binaries = environment / ("Scripts" if sys.platform == "win32" else "bin")
        executable = binaries / ("python.exe" if sys.platform == "win32" else "python")
        console = binaries / ("maintlog.exe" if sys.platform == "win32" else "maintlog")
        run(
            [
                str(executable),
                "-I",
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(wheels[0].resolve()),
            ],
            root,
        )
        run(
            [
                str(executable),
                "-I",
                "-c",
                "import pathlib,sys,maintlog; "
                "p=pathlib.Path(maintlog.__file__).resolve(); "
                "prefix=pathlib.Path(sys.prefix).resolve(); "
                "sys.exit(0 if prefix in p.parents else "
                "'Imported outside fresh environment')",
            ],
            root,
        )
        run([str(executable), "-I", "-m", "pip", "check"], root)
        run([str(executable), "-I", "-m", "maintlog.cli", "--help"], root)
        run([str(console), "--help"], root)
        source = root / "synthetic_records.csv"
        with source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(FIELDS)
            writer.writerows(ROWS)
        for asset_id in ("PUMP-001", "PUMP-UNKNOWN"):
            output = root / f"{asset_id}.json"
            run(
                [
                    str(console),
                    "search",
                    str(source),
                    "--data-kind",
                    "synthetic",
                    "--query",
                    "bearing vibration",
                    "--normalization",
                    "identity",
                    "--top-k",
                    "10",
                    "--asset-id",
                    asset_id,
                    "--output",
                    str(output),
                ],
                root,
            )
            check_result(output, source, asset_id)
    print(
        "Base wheel, installed CLI, search results, scope, and evidence checks passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
