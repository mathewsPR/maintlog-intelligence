"""Python 3.11 equipment-history review. Models are explicitly selected."""

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .brief import recurring_brief
from .ingestion import DATA_KINDS, DataError, load_csv, load_profile
from .retrieval import search
from .scope import Scope


def main(argv: list[str] | None = None) -> int:
    if sys.version_info[:2] != (3, 11):
        print("maintlog requires Python 3.11 only.", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("import", "search", "brief", "agent", "reviewed-brief")
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--data-kind", required=True, choices=DATA_KINDS)
    parser.add_argument("--query")
    parser.add_argument(
        "--normalization",
        choices=("dictionary_v0", "noun_alias_v1", "identity"),
        default="noun_alias_v1",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--asset-id")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--vocabulary", type=Path)
    parser.add_argument("--question")
    parser.add_argument("--backend", choices=("local", "replay"))
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--model", default="local-model")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--html", type=Path)
    parser.add_argument(
        "--task", choices=("history", "search", "inspect", "extract"), default="history"
    )
    parser.add_argument("--initial-query")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--review-run")
    parser.add_argument("--review-report", type=Path)
    args = parser.parse_args(argv)
    try:
        protected = {
            p.resolve()
            for p in (
                args.csv,
                args.profile,
                args.replay,
                args.database,
                args.vocabulary,
            )
            if p
        }
        for output in (args.output, args.html):
            if output and output.resolve() in protected:
                raise DataError("output must not overwrite an input file")
        if args.output and args.html and args.output.resolve() == args.html.resolve():
            raise DataError("JSON and HTML output paths must differ")
        if args.html and args.command != "agent":
            raise DataError("--html requires agent")
        # Reject unrelated flags rather than silently ignoring them.
        agent_flags = {
            "--question",
            "--backend",
            "--replay",
            "--base-url",
            "--model",
            "--max-steps",
            "--timeout",
            "--max-tokens",
            "--task",
            "--initial-query",
        }
        supplied = {
            a.split("=", 1)[0]
            for a in (argv if argv is not None else sys.argv[1:])
            if a.startswith("--")
        }
        if args.command != "agent" and supplied & agent_flags:
            raise DataError("model flags require agent")
        if args.command != "search" and supplied & {
            "--query",
            "--top-k",
            "--normalization",
        }:
            raise DataError("--query and --top-k require search")
        if args.command != "reviewed-brief" and supplied & {
            "--database",
            "--review-run",
            "--review-report",
        }:
            raise DataError("review flags require reviewed-brief")
        if args.vocabulary and "--normalization" in supplied:
            raise DataError("--vocabulary and --normalization are mutually exclusive")
        from .vocabulary import load_vocabulary

        vocabulary = load_vocabulary(args.vocabulary) if args.vocabulary else None
        records = load_csv(
            args.csv,
            data_kind=args.data_kind,
            columns=load_profile(args.profile) if args.profile else None,
            vocabulary=vocabulary,
        )
        scope = Scope(args.asset_id, args.start, args.end)
        selected = scope.select(records)
        if args.command == "import":
            result = {
                "record_count": len(selected),
                "input_record_count": len(records),
                "data_kind": args.data_kind,
                "scope": asdict(scope),
                "records": [asdict(record) for record in selected],
            }
        elif args.command == "search":
            if not args.query:
                raise DataError("search requires --query")
            result = {
                "query": args.query,
                "scope": asdict(scope),
                "selected_record_count": len(selected),
                "method": "bm25_raw_fields_with_explicit_alias_policy",
                "normalization_policy": "train_lexicon_v1"
                if vocabulary
                else args.normalization,
                "hits": [
                    asdict(hit)
                    for hit in search(
                        selected,
                        args.query,
                        top_k=args.top_k,
                        normalization_policy=args.normalization,
                        vocabulary=vocabulary,
                    )
                ],
            }
        elif args.command == "brief":
            result = recurring_brief(
                records, start=args.start, end=args.end, asset_id=args.asset_id
            )
        elif args.command == "reviewed-brief":
            from .review_store import reviewed_brief

            if not args.database or bool(args.review_run) == bool(args.review_report):
                raise DataError(
                    "reviewed-brief requires --database and exactly one of --review-run or --review-report"
                )
            if args.review_report:
                from .review import run_hash

                args.review_run = run_hash(
                    json.loads(args.review_report.read_text(encoding="utf-8"))
                )
            result = reviewed_brief(
                records,
                args.database,
                args.review_run,
                scope=scope,
                vocabulary=vocabulary,
            )
        else:
            from .agent import run_agent
            from .backends import LocalServer, Replay
            from .tasks import TaskSpec

            if not args.question or not args.backend:
                raise DataError(
                    "agent requires --question and explicit --backend local or replay"
                )
            if (args.backend == "replay") != bool(args.replay):
                raise DataError("--replay is required only for backend replay")
            if args.backend == "replay" and supplied & {
                "--base-url",
                "--model",
                "--max-tokens",
            }:
                raise DataError(
                    "--base-url, --model, --max-tokens require backend local"
                )
            backend = (
                Replay.from_file(args.replay)
                if args.backend == "replay"
                else LocalServer(args.base_url, args.model, args.max_tokens)
            )
            result = run_agent(
                records,
                args.question,
                backend,
                scope=scope,
                max_steps=args.max_steps,
                timeout_seconds=args.timeout,
                task=TaskSpec(args.task, args.initial_query),
                vocabulary=vocabulary,
            )
            if args.html:
                from .review import render_html

                args.html.parent.mkdir(parents=True, exist_ok=True)
                args.html.write_text(render_html(result), encoding="utf-8")
        rendered = json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n"
        if args.output:
            if args.output.resolve() == args.csv.resolve():
                raise DataError("output must not overwrite the input CSV")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except ImportError:
        print(
            'Error: agent requires installation with python -m pip install -e ".[agent]"',
            file=sys.stderr,
        )
        return 2
    except (DataError, OSError, ValueError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.command == "agent" and result["status"] not in {
        "ready_for_review",
        "needs_clarification",
        "no_matches",
        "no_records",
    }:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
