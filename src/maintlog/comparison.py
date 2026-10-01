"""comparison.py   Paired workflow comparisons with labels kept outside model context."""

import argparse
import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .agent import SYSTEM, run_agent
from .backends import LocalServer, Replay
from .brief import recurring_brief
from .extraction import validate_fields
from .ingestion import load_csv, load_profile
from .retrieval import search
from .scope import Scope
from .tasks import TaskSpec


class FixedWorkflow:
    """Fixed lexical search → inspect/extract candidates → aggregate → finish."""

    def __init__(self, backend, query: str, mode: str):
        self.backend, self.query, self.mode = backend, query, mode
        self.label = "fixed-workflow/" + backend.label
        self.actions = None
        self.pending_focused_record = None

    @property
    def request_count(self):
        return getattr(self.backend, "request_count", 0)

    def decide(self, system, context, timeout):
        extraction_record = context.get("extraction_record")
        if isinstance(extraction_record, dict):
            record_id = extraction_record.get("record_id")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError("focused extraction requires a record_id")

            if self.pending_focused_record != record_id:
                if self.actions is None:
                    raise ValueError(
                        "fixed extraction requested before workflow initialization"
                    )

                # Consume the scheduled extraction once. Retries for this
                # record must not advance the remaining workflow actions.
                scheduled = next(self.actions, None)
                if scheduled != {
                    "tool": "_maybe_extract",
                    "args": {"record_id": record_id},
                }:
                    raise ValueError(
                        "focused extraction does not match fixed workflow schedule"
                    )

                self.pending_focused_record = record_id

            # Pass through the focused source and any validation feedback.
            response = self.backend.decide(system, context, timeout)
            value = response.get("decision", {})
            if (
                value.get("tool") != "extract"
                or value.get("args", {}).get("record_id") != record_id
            ):
                raise ValueError("fixed extractor returned wrong tool or record")
            return response

        self.pending_focused_record = None

        observations = context["observations"]
        if observations and "error" in observations[-1]["result"]:
            decision = {
                "tool": "abstain",
                "args": {"reason": "Fixed workflow validation failed; inspect trace."},
            }
        elif self.actions is None:
            if not observations:
                return {
                    "decision": {
                        "tool": "search",
                        "args": {"query": self.query, "top_k": 5},
                    },
                    "model_called": False,
                }
            hits = observations[-1]["result"]["hits"]
            ids = [h["record_id"] for h in hits]
            actions = []
            for rid in ids:
                actions.append({"tool": "record", "args": {"record_id": rid}})
                actions.append({"tool": "_maybe_extract", "args": {"record_id": rid}})
            if self.mode == "history":
                actions.append({"tool": "aggregate", "args": {}})
            actions.append({"tool": "finish", "args": {"record_ids": ids}})
            self.actions = iter(actions)
            return self.decide(system, context, timeout)
        else:
            decision = next(self.actions)
            while decision["tool"] == "_maybe_extract":
                row = observations[-1]["result"]
                needs = self.mode == "extract" or (
                    self.mode == "history" and row.get("narrative_raw")
                )
                if needs:
                    # Same model and validation engine. Only extraction is a
                    # model call; search/tool order is fixed by this baseline.
                    prompt = (
                        SYSTEM
                        + "\nFor this fixed workflow return ONLY extract for "
                        + row["record_id"]
                        + ". Unknown fields may be null."
                    )
                    response = self.backend.decide(
                        prompt,
                        {
                            "question": context["question"],
                            "task_requirements": context["task_requirements"],
                            "record": row,
                        },
                        timeout,
                    )
                    value = response.get("decision", {})
                    if (
                        value.get("tool") != "extract"
                        or value.get("args", {}).get("record_id") != row["record_id"]
                    ):
                        raise ValueError(
                            "fixed extractor returned wrong tool or record"
                        )
                    return response
                decision = next(self.actions)
        return {
            "decision": decision,
            "model_called": False,
            "usage": {},
            "elapsed_seconds": 0,
        }


def score_case(report: dict, case: dict) -> dict:
    expected = set(case["relevant_record_ids"])
    retrieved = [r["record_id"] for r in report["records_for_review"]]
    actual = set(retrieved)
    overlap = len(actual & expected)
    fields_expected = case.get("expected_fields", {})
    proposals = {p["record_id"]: p for p in report["extraction_proposals"]}
    tp = fp = fn = correct_unknown = status_correct = status_total = 0
    for rid, reference in fields_expected.items():
        predicted = proposals.get(rid, {}).get("fields", {})
        for name, gold in reference["fields"].items():
            pred = predicted.get(name)

            def key(span):
                return (span["field"], span["start"], span["end"]) if span else None

            if gold is None:
                correct_unknown += pred is None
                fp += pred is not None
            elif key(pred) == key(gold):
                tp += 1
            else:
                fn += 1
                fp += pred is not None
        if "action_status" in reference:
            status_total += 1
            status_correct += (
                proposals.get(rid, {}).get("action_status_proposal")
                == reference["action_status"]
            )
    field_total = sum(
        sum(span is not None for span in reference["fields"].values())
        for reference in fields_expected.values()
    )
    matches = actual == expected
    terminal = report["status"] in {"ready_for_review", "no_matches", "no_records"}
    aggregate_correct = None
    if "expected_aggregate_groups" in case:
        aggregate = report.get("aggregate")

        def group_key(group):
            return (
                group["asset_id"],
                group["component"],
                group["normalized_issue_key"],
                group["record_count"],
            )

        aggregate_correct = aggregate is not None and sorted(
            group_key(g) for g in aggregate["recurring_groups"]
        ) == sorted(group_key(g) for g in case["expected_aggregate_groups"])
        if aggregate_correct and "expected_selected_count" in case:
            aggregate_correct = (
                aggregate["selected_record_count"] == case["expected_selected_count"]
            )

    return {
        "record_precision": overlap / len(actual)
        if actual
        else (1.0 if not expected else 0.0),
        "record_recall": overlap / len(expected)
        if expected
        else (1.0 if not actual else 0.0),
        "exact_record_set": matches,
        "aggregate_correct": aggregate_correct,
        "field_tp": tp,
        "field_fp": fp,
        "field_fn": fn,
        "required_field_spans": field_total,
        "field_precision": tp / (tp + fp) if tp + fp else None,
        "field_recall": tp / (tp + fn) if tp + fn else None,
        "correct_unknown_fields": correct_unknown,
        "status_correct": status_correct,
        "status_total": status_total,
        "labeled_task_success": terminal
        and matches
        and fn == 0
        and fp == 0
        and status_correct == status_total
        and aggregate_correct is not False,
        "workflow_complete": report.get("completion", {}).get(
            "requirements_met", False
        ),
        "run_status": report["status"],
        "model_calls": report.get("model_calls", 0),
        "invalid_decisions": sum(
            "tool_error" in s or "error" in s for s in report["trace"]
        ),
        "elapsed_seconds": report["elapsed_seconds"],
        "reported_completion_tokens": sum(
            s.get("usage", {}).get("completion_tokens", 0) for s in report["trace"]
        ),
        "token_usage_available": any(s.get("usage") for s in report["trace"]),
    }


def deterministic(records, case, scope):
    started = time.monotonic()
    selected = scope.select(records)
    hits = search(
        selected, case["query"], top_k=5, normalization_policy="noun_alias_v1"
    )
    return {
        "status": "ready_for_review"
        if hits
        else "no_matches"
        if selected
        else "no_records",
        "records_for_review": [asdict(h.record) for h in hits],
        "extraction_proposals": [],
        "aggregate": recurring_brief(selected) if case["task"] == "history" else None,
        "trace": [],
        "model_calls": 0,
        "elapsed_seconds": time.monotonic() - started,
        "completion": {"requirements_met": True},
        "backend": "deterministic-no-model",
    }


def load_cases(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    source = payload["source"]
    csv = path.parent / source["csv"]
    if hashlib.sha256(csv.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("comparison source hash mismatch")
    columns = None
    if source.get("profile"):
        profile = path.parent / source["profile"]
        if hashlib.sha256(profile.read_bytes()).hexdigest() != source["profile_sha256"]:
            raise ValueError("comparison profile hash mismatch")
        columns = load_profile(profile)
    records = load_csv(csv, data_kind=source["data_kind"], columns=columns)
    ids = set()
    for case in payload["cases"]:
        if case["id"] in ids:
            raise ValueError("duplicate comparison case ID")
        ids.add(case["id"])
        scope = Scope(
            case["scope"].get("asset_id"),
            *(
                date.fromisoformat(case["scope"][key])
                if case["scope"].get(key)
                else None
                for key in ("start", "end")
            ),
        )
        by_id = {r.record_id: r for r in scope.select(records)}
        if len(set(case["relevant_record_ids"])) != len(
            case["relevant_record_ids"]
        ) or not set(case["relevant_record_ids"]) <= set(by_id):
            raise ValueError("relevance labels outside scope or duplicated")
        case["expected_selected_count"] = len(by_id)
        if case["task"] == "history" and not isinstance(
            case.get("expected_aggregate_groups"), list
        ):
            raise ValueError(
                "history comparisons require aggregate group labels, even an empty list"
            )
        TaskSpec(case["task"], case["query"]).requirements()
        if not set(case.get("expected_fields", {})) <= set(case["relevant_record_ids"]):
            raise ValueError("field labels require relevant records")
        for rid, reference in case.get("expected_fields", {}).items():
            reference["fields"] = validate_fields(
                by_id[rid],
                reference["fields"],
                reference.get("action_status", "unknown"),
                human_review=True,
            )
    return payload, records


def compare(
    path: Path,
    *,
    backend: str,
    base_url: str = "http://127.0.0.1:8081/v1",
    model: str = "local-model",
    trials: int = 1,
    max_steps: int = 20,
    timeout: float = 120,
):
    if not 1 <= trials <= 10:
        raise ValueError("trials must be between 1 and 10")
    payload, records = load_cases(path)
    rows = []
    for trial in range(trials):
        for case in payload["cases"]:
            scope = Scope(
                case["scope"].get("asset_id"),
                *(
                    date.fromisoformat(case["scope"][key])
                    if case["scope"].get(key)
                    else None
                    for key in ("start", "end")
                ),
            )
            workflows = ["deterministic", "fixed", "agent"]
            # Rotate execution order to reduce warm-cache/order advantages.
            offset = trial % 3
            workflows = workflows[offset:] + workflows[:offset]
            for workflow in workflows:
                if workflow == "deterministic":
                    report = deterministic(records, case, scope)
                else:
                    provider = (
                        LocalServer(base_url, model)
                        if backend == "local"
                        else Replay.from_file(path.parent / case[workflow + "_replay"])
                    )
                    chooser = (
                        FixedWorkflow(provider, case["query"], case["task"])
                        if workflow == "fixed"
                        else provider
                    )
                    report = run_agent(
                        records,
                        case["question"],
                        chooser,
                        scope=scope,
                        task=TaskSpec(case["task"], case["query"]),
                        max_steps=max_steps,
                        timeout_seconds=timeout,
                    )
                rows.append(
                    {
                        "trial": trial + 1,
                        "case_id": case["id"],
                        "workflow": workflow,
                        "metrics": score_case(report, case),
                        "run": report,
                    }
                )
    return {
        "schema_version": 1,
        "python": platform.python_version(),
        "backend": backend,
        "evidence_kind": "synthetic_replay_mechanics"
        if backend == "replay"
        else "local_model_on_declared_labels",
        "data_kind": payload["source"]["data_kind"],
        "source": payload["source"],
        "label_provenance": payload.get("label_provenance", "caller-declared labels"),
        "cases_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "trials": trials,
        "model_configuration": {
            "base_url": base_url,
            "model": model,
            "max_tokens": 512,
            "temperature": 0,
        }
        if backend == "local"
        else None,
        "limits": {"max_steps": max_steps, "timeout": timeout},
        "results": rows,
        "interpretation": "Labels are never passed into model context. Replay scores validate fixture mechanics only. Exact record sets and source spans measure the declared tasks; they do not establish commercial value. Cost is unknown unless priced actual usage is supplied.",
    }


def main(argv=None):
    if sys.version_info[:2] != (3, 11):
        print("Python 3.11 required", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--backend", choices=("local", "replay"), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--model", default="local-model")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload, _ = load_cases(args.cases)
        inputs = [args.cases, args.cases.parent / payload["source"]["csv"]]
        inputs += (
            [args.cases.parent / payload["source"]["profile"]]
            if payload["source"].get("profile")
            else []
        )
        inputs += [
            args.cases.parent / c[key]
            for c in payload["cases"]
            for key in ("agent_replay", "fixed_replay")
            if key in c
        ]
        if args.output.resolve() in {p.resolve() for p in inputs}:
            raise ValueError("comparison output must not overwrite inputs")
        result = compare(
            args.cases,
            backend=args.backend,
            base_url=args.base_url,
            model=args.model,
            trials=args.trials,
            max_steps=args.max_steps,
            timeout=args.timeout,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
        )
        print(f"Saved comparison: {args.output}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Comparison failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
