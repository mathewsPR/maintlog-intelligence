"""Offline source review with portable decisions and append-only SQLite events."""

import argparse
import hashlib
import html
import json
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


def canonical(report: dict) -> str:
    return json.dumps(
        report, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
    )


def run_hash(report: dict) -> str:
    return hashlib.sha256(canonical(report).encode()).hexdigest()


def review_ids(report: dict) -> set[str]:
    return {r["record_id"] for r in report["records_for_review"]} | {
        p["record_id"] for p in report["extraction_proposals"]
    }


def render_html(report: dict) -> str:
    def esc(value):
        return html.escape(str(value))

    items = {r["record_id"]: r for r in report["records_for_review"]}
    # Extraction proposals can exist in an incomplete run. Preserve their source
    # record for inspection without pretending the run completed.
    for step in report["trace"]:
        result = step.get("tool_result", {})
        if step.get("decision", {}).get("tool") == "record" and "record_id" in result:
            if result["record_id"] in review_ids(report):
                items.setdefault(result["record_id"], result)
    proposals = {p["record_id"]: p for p in report["extraction_proposals"]}
    cards = []
    for record_id, record in items.items():
        source = record["evidence"]
        proposal = proposals.get(record_id)
        controls = []
        for name in ("component", "problem", "action"):
            span = proposal["fields"][name] if proposal else None
            default_source = (
                span["field"]
                if span
                else (
                    "component"
                    if name == "component" and record["component"]
                    else "narrative_raw"
                    if record.get("narrative_raw")
                    else "action_raw"
                    if name == "action"
                    else "issue_raw"
                )
            )
            quote = (
                span["quote"]
                if span
                else (record["component"] if name == "component" else "")
            )
            options = "".join(
                f'<option value="{field}" {"selected" if field == default_source else ""}>{field}</option>'
                for field in ("component", "issue_raw", "action_raw", "narrative_raw")
            )
            controls.append(f'''<fieldset data-field-review="{name}"><legend>{name.title()}</legend>
<p>Proposed excerpt: {esc(span["quote"] if span else "Unknown")}</p>
<label>Field decision <select class="field-choice"><option value="unreviewed">Unreviewed</option><option value="accepted">Accept proposal</option><option value="rejected">Reject / mark unknown</option><option value="corrected">Correct excerpt</option></select></label>
<div><label>Correction source <select class="source">{options}</select></label><label>Exact corrected quote <textarea class="quote" maxlength="6000">{esc(quote)}</textarea></label>
<label>For repeated quotes only: start <input class="start" type="number" min="0"> end <input class="end" type="number" min="1"></label></div></fieldset>''')
        proposed_status = proposal["action_status_proposal"] if proposal else "unknown"
        status_options = "".join(
            f'<option value="{value}" {"selected" if value == proposed_status else ""}>{value}</option>'
            for value in ("unknown", "planned", "attempted", "completed", "verified")
        )
        fields = (
            "<h3>Review individual fields</h3>"
            + "".join(controls)
            + f"""<fieldset class="status-review"><legend>Action status</legend><p>Proposed: {esc(proposed_status)}</p><select class="status-choice"><option value="unreviewed">Unreviewed</option><option value="accepted">Accept proposal</option><option value="rejected">Reject / mark unknown</option><option value="corrected">Correct status</option></select><select class="status-value">{status_options}</select></fieldset>"""
        )
        if proposal:
            fields += (
                "<details><summary>Proposed source spans</summary><pre>"
                + esc(json.dumps(proposal, indent=2, ensure_ascii=False))
                + "</pre></details>"
            )
        cards.append(f'''<article data-record="{esc(record_id)}"><h2>{esc(record_id)} · {esc(record["asset_id"])}</h2>
<p>{esc(record["event_date"])} · {esc(source["source_file"])} · CSV row {esc(source["csv_row"])} · {esc(source["data_kind"])}</p>
<dl><dt>Component from input</dt><dd>{esc(record["component"] or "Unknown")}</dd>
<dt>Issue from input</dt><dd>{esc(record["issue_raw"] or "Unknown")}</dd>
<dt>Action from input</dt><dd>{esc(record["action_raw"] or "Unknown")}</dd>
<dt>Raw narrative</dt><dd>{esc(record.get("narrative_raw") or "Not supplied")}</dd></dl>
<details><summary>Source hash and columns</summary><pre>{esc(json.dumps(source, indent=2))}</pre></details>{fields}
<label>Review this selected record and its extraction proposal (if present)
<select class="record-choice"><option value="unreviewed">Unreviewed</option><option value="accepted">Accept for this review</option><option value="rejected">Reject for this review</option></select></label>
<label>Reviewer note <textarea class="review-note" maxlength="2000"></textarea></label></article>''')
    payload = (
        json.dumps(
            {"run_sha256": run_hash(report), "record_ids": sorted(review_ids(report))},
            ensure_ascii=False,
        )
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )
    aggregates = esc(
        json.dumps(report.get("aggregate"), indent=2, ensure_ascii=False, default=str)
    )
    clarification = (
        f"<p><strong>Clarification needed:</strong> {esc(report['clarification'])}</p>"
        if report.get("clarification")
        else ""
    )
    if report.get("abstention"):
        clarification += (
            f"<p><strong>Abstained:</strong> {esc(report['abstention'])}</p>"
        )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Equipment history review</title><style>body{{font:16px system-ui;max-width:960px;margin:32px auto;padding:0 20px;background:#f5f7fa;color:#182535}}article,.panel{{background:white;padding:24px;border:1px solid #d7dee7;border-radius:10px;margin:20px 0}}pre,dd{{white-space:pre-wrap;overflow-wrap:anywhere}}pre{{font-size:13px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #d7dee7;overflow-wrap:anywhere}}dt{{font-weight:bold;margin-top:12px}}dd{{margin:4px 0}}label{{display:block;margin-top:16px}}textarea{{display:block;width:95%;min-height:60px}}fieldset{{margin-top:16px;border:1px solid #d7dee7}}select,input,button{{padding:8px;font:inherit}}button{{background:#173b63;color:white;border:0;border-radius:6px;cursor:pointer}}.status{{font-weight:bold}}@media print{{button,select,textarea{{display:none}}}}</style>
<h1>Equipment history review</h1><p class="status">{esc(report["status"])} · {esc(report["backend"])}</p>
<p>{esc(report["question"])}</p><p>Scope: {esc(json.dumps(report["scope"]))}. Selected records: {esc(report["selected_record_count"])}.</p>{clarification}
<div class="panel">{esc(report["interpretation"])}<p>Record acceptance does not approve individual fields. Reuse requires decisions on all three fields and action status. Acceptance records a human review decision. It does not confirm a diagnosis, repair success, or safety authorization.</p></div>
{"".join(cards) or "<p>No records selected for review.</p>"}
<details class="panel"><summary>Full deterministic aggregate (if requested)</summary><pre>{aggregates}</pre></details>
<div class="panel"><label>Reviewer name <input id="reviewer" maxlength="200" placeholder="Your name"></label><p>Choose a decision for each reviewed record. Download decisions, then import them with maintlog-review to preserve the audit history.</p><button id="download">Download review decisions</button><p id="message" role="status"></p></div>
<script type="application/json" id="run-data">{payload}</script><script>
const run=JSON.parse(document.getElementById('run-data').textContent);
document.getElementById('download').onclick=()=>{{
 const reviewer=document.getElementById('reviewer').value.trim();
 if(!reviewer){{document.getElementById('message').textContent='Enter a reviewer name.';return;}}
 const decisions=[];
 for(const el of document.querySelectorAll('article[data-record]')){{
  const decision=el.querySelector('.record-choice').value;
  if(decision==='unreviewed')continue;
  const row={{record_id:el.dataset.record,decision,note:el.querySelector('.review-note').value}};
  const fields={{}};
  for(const box of el.querySelectorAll('[data-field-review]')){{
   const choice=box.querySelector('.field-choice').value;
   if(choice==='unreviewed')continue;
   const review={{decision:choice}};
   if(choice==='corrected'){{
    const field=box.querySelector('.source').value;
    const quote=box.querySelector('.quote').value;
    const start=box.querySelector('.start').value,end=box.querySelector('.end').value;
    if((start==='')!==(end==='')){{document.getElementById('message').textContent='Enter both offsets or leave both blank.';return;}}
    review.span=start===''?{{field,quote}}:{{field,start:Number(start),end:Number(end),quote}};
   }}
   fields[box.dataset.fieldReview]=review;
  }}
  if(Object.keys(fields).length)row.fields=fields;
  const statusChoice=el.querySelector('.status-choice').value;
  if(statusChoice!=='unreviewed')row.action_status={{decision:statusChoice,value:statusChoice==='rejected'?'unknown':el.querySelector('.status-value').value}};
  decisions.push(row);
 }}
 const data={{run_sha256:run.run_sha256,reviewer,decisions}};
 const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{{type:'application/json'}}));
 const a=document.createElement('a');a.href=url;a.download='review-decisions.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 document.getElementById('message').textContent='Downloaded '+decisions.length+' decisions. Import this file to save review history.';
}};
</script></html>"""


def save_decisions(report: dict, decisions: dict, database: Path) -> int:
    if set(decisions) != {"run_sha256", "reviewer", "decisions"} or decisions[
        "run_sha256"
    ] != run_hash(report):
        raise ValueError("decisions do not match this exact run")
    reviewer = decisions["reviewer"]
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 200:
        raise ValueError("reviewer name is required")
    allowed = review_ids(report)
    rows = decisions["decisions"]
    if not isinstance(rows, list):
        raise ValueError("decisions must be a list")
    seen = set()
    field_reviews = []
    from .review_store import validate_field_review

    for row in rows:
        if (
            not isinstance(row, dict)
            or not {"record_id", "decision", "note"} <= set(row)
            or not set(row)
            <= {"record_id", "decision", "note", "fields", "action_status"}
        ):
            raise ValueError("invalid review fields")
        if (
            not isinstance(row["record_id"], str)
            or row["record_id"] not in allowed
            or row["record_id"] in seen
        ):
            raise ValueError("unknown or duplicate review record")
        seen.add(row["record_id"])
        if row["decision"] not in ("accepted", "rejected"):
            raise ValueError("invalid review decision")
        if not isinstance(row["note"], str) or len(row["note"]) > 2000:
            raise ValueError("invalid reviewer note")
        field_reviews.append(validate_field_review(report, row))
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS runs (sha256 TEXT PRIMARY KEY, report_json TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS review_events (event_id INTEGER PRIMARY KEY, run_sha256 TEXT NOT NULL REFERENCES runs(sha256), record_id TEXT NOT NULL, reviewer TEXT NOT NULL, decision TEXT NOT NULL, note TEXT NOT NULL, reviewed_at TEXT NOT NULL)"
        )
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT OR IGNORE INTO runs VALUES (?, ?)",
            (run_hash(report), canonical(report)),
        )
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS field_review_events (event_id INTEGER PRIMARY KEY REFERENCES review_events(event_id), review_json TEXT NOT NULL)"
        )
        for row, fields in zip(rows, field_reviews):
            cursor = conn.execute(
                "INSERT INTO review_events (run_sha256,record_id,reviewer,decision,note,reviewed_at) VALUES (?,?,?,?,?,?)",
                (
                    run_hash(report),
                    row["record_id"],
                    reviewer,
                    row["decision"],
                    row["note"],
                    now,
                ),
            )
            if fields is not None:
                conn.execute(
                    "INSERT INTO field_review_events VALUES (?,?)",
                    (cursor.lastrowid, canonical(fields)),
                )
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    if sys.version_info[:2] != (3, 11):
        print("maintlog requires Python 3.11 only.", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument(
        "--database", type=Path, default=Path("artifacts/reviews.sqlite3")
    )
    args = parser.parse_args(argv)
    try:
        if args.database.resolve() in {args.report.resolve(), args.decisions.resolve()}:
            raise ValueError("database must not overwrite an input file")
        report = json.loads(args.report.read_text(encoding="utf-8"))
        decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
        count = save_decisions(report, decisions, args.database)
        print(f"Saved {count} review events.")
        return 0
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
