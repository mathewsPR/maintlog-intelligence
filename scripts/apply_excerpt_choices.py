"""Install source excerpt choices in the existing bounded evidence revision."""

from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BACKEND_BLOCK = """        revision = context.get("evidence_revision")
        if isinstance(extraction_record, dict) and isinstance(revision, dict):
            contract = excerpt_contract(extraction_record, revision)
            if contract is not None:
                candidates = {}
                response_schema, shown = contract
                context.pop("component_candidates", None)
                context.pop("component_feedback_note", None)
                context.pop("component_span_options", None)
                context["excerpt_span_options"] = shown
                system = EXTRACTION_SYSTEM + (
                    "\\nReturn field/start/end from the supplied excerpt_span_options. "
                    "Quotes are shown for inspection only. Select the reported "
                    "symptom for problem and corrective work for action. "
                    "Separate checks remain in the full source history. "
                    "Alternatives are not verified interpretations. Retain the "
                    "original if alternatives omit needed evidence. "
                    "Preserve unchanged fields and action_status."
                )

"""

AGENT_BLOCK = """                    source_context = {
                        "record_id": record_id,
                        **{
                            name: getattr(by_id[record_id], name)
                            for name in ("component", "issue_raw", "action_raw", "narrative_raw")
                        },
                    }
                    for name, choices in excerpt_options(source_context, active_revision).items():
                        supplied = spans[name]
                        if supplied is None or {
                            key: supplied[key] for key in ("field", "start", "end")
                        } not in choices:
                            raise ValueError("evidence revision is outside source excerpt choices")
"""


def main():
    edits = {}

    for filename, anchor, block, imported in (
        (
            "backends.py",
            "        self.request_count += 1\n",
            BACKEND_BLOCK,
            "excerpt_contract",
        ),
        (
            "agent.py",
            '                    flagged = {item["field"] for item in active_revision["concerns"]}\n',
            AGENT_BLOCK,
            "excerpt_options",
        ),
    ):
        path = ROOT / "src" / "maintlog" / filename
        before = path.read_text(encoding="utf-8")

        if "from .revision_evidence import" in before:
            raise SystemExit(f"Already installed in {filename}; no files changed.")

        if before.count(anchor) != 1:
            raise SystemExit(f"Expected unique anchor in {filename}; no files changed.")

        import_anchor = "from .revision_component import component_revision_candidate\n"
        if before.count(import_anchor) != 1:
            raise SystemExit(f"Missing component fix in {filename}; no files changed.")

        after = before.replace(
            import_anchor,
            import_anchor + f"from .revision_evidence import {imported}\n",
        )
        after = after.replace(
            anchor, block + anchor if filename == "backends.py" else anchor + block
        )

        compile(after, str(path), "exec")
        edits[path] = (before, after)

    helper = ROOT / "src" / "maintlog" / "revision_evidence.py"
    compile(helper.read_text(encoding="utf-8"), str(helper), "exec")

    backup = (
        ROOT
        / "artifacts"
        / ("excerpt-choice-backup-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    )
    backup.mkdir(parents=True)

    for path, (before, _) in edits.items():
        (backup / path.name).write_text(before, encoding="utf-8")

    try:
        for path, (_, after) in edits.items():
            path.write_text(after, encoding="utf-8")
    except Exception:
        for path, (before, _) in edits.items():
            path.write_text(before, encoding="utf-8")
        raise

    print(f"Installed excerpt choices. Originals: {backup}")


if __name__ == "__main__":
    main()
