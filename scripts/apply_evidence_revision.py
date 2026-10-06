"""Apply one bounded source-checked evidence revision per record."""

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

EDITS = {
    "src/maintlog/agent.py": [
        (
            r"""from .domain import Record
from .extraction import STATUS_GUIDANCE, validate_fields
""",
            r"""from .domain import Record
from .evidence_review import review_evidence
from .extraction import STATUS_GUIDANCE, validate_fields
""",
        ),
        (
            r"""    proposals: dict[str, dict] = {}
    aggregates = None
""",
            r"""    proposals: dict[str, dict] = {}
    revision_attempted: set[str] = set()
    active_revision = None
    aggregates = None
""",
        ),
        (
            r"""    def choose(state: State):
        nonlocal completion

""",
            r"""    def choose(state: State):
        nonlocal completion, active_revision
        active_revision = None

""",
        ),
        (
            r"""
        extraction_candidates = sorted(
""",
            r"""
        concerns_by_record = {}
        for record_id in sorted(inspected - revision_attempted):
            if record_id in proposals:
                concerns = review_evidence([by_id[record_id]], [proposals[record_id]])[
                    "concerns"
                ]
                if concerns:
                    concerns_by_record[record_id] = concerns

        extraction_candidates = sorted(
""",
        ),
        (
            r"""            for record_id in inspected
            if needs_extraction(record_id) and record_id not in proposals
        )
""",
            r"""            for record_id in inspected
            if (needs_extraction(record_id) and record_id not in proposals)
            or record_id in concerns_by_record
        )
""",
        ),
        (
            r"""
            for observation in reversed(state["context"]["observations"]):
""",
            r"""
            if extraction_target in concerns_by_record:
                active_revision = {
                    "record_id": extraction_target,
                    "previous_proposal": proposals[extraction_target],
                    "concerns": concerns_by_record[extraction_target],
                    "instruction": (
                        "Review the flagged fields against the source. Revise only "
                        "those fields when justified; preserve all other fields and "
                        "action_status. A warning may be a false alarm: retaining "
                        "supported evidence is allowed. Do not invent evidence "
                        "or remove supported fields just to clear a warning."
                    ),
                }
                decision_context["evidence_revision"] = active_revision

            for observation in reversed(state["context"]["observations"]):
""",
        ),
        (
            r"""            for observation in reversed(state["context"]["observations"]):
                result = observation.get("result", {})
""",
            r"""            for observation in reversed(state["context"]["observations"]):
                if active_revision is not None:
                    break
                result = observation.get("result", {})
""",
        ),
        (
            r"""        try:
            response = backend.decide(
""",
            r"""        try:
            if active_revision is not None:
                revision_attempted.add(extraction_target)
            response = backend.decide(
""",
        ),
        (
            r"""            )
            if response.get("extraction_audit") is not None:
""",
            r"""            )
            if active_revision is not None:
                trace[-1]["evidence_revision"] = active_revision
            if response.get("extraction_audit") is not None:
""",
        ),
        (
            r"""                )
                output = {
""",
            r"""                )
                if active_revision is not None:
                    if record_id != active_revision["record_id"]:
                        raise ValueError("revision returned the wrong record")
                    previous = active_revision["previous_proposal"]
                    flagged = {item["field"] for item in active_revision["concerns"]}
                    if args["action_status"] != previous["action_status_proposal"]:
                        raise ValueError(
                            "evidence revision must preserve action status"
                        )
                    for name in spans:
                        if previous["fields"][name] is not None and spans[name] is None:
                            raise ValueError(
                                "evidence revision cannot discard previous evidence"
                            )
                        if (
                            name not in flagged
                            and spans[name] != previous["fields"][name]
                        ):
                            raise ValueError(
                                "evidence revision changed an unflagged field"
                            )

                output = {
""",
        ),
        (
            r"""        },
        "history_review": history_review,
""",
            r"""        },
        "evidence_revision_attempted": sorted(revision_attempted),
        "history_review": history_review,
""",
        ),
    ],
    "src/maintlog/backends.py": [
        (
            r"""            system = EXTRACTION_SYSTEM

""",
            r"""            system = EXTRACTION_SYSTEM
            if "evidence_revision" in context:
                focused_context["evidence_revision"] = context["evidence_revision"]
                system += (
                    "\nThis is the one permitted evidence revision for this record. "
                    "Use evidence_revision.concerns and the original source. "
                    "Change only flagged fields when the source supports correction. "
                    "Preserve unflagged fields and action_status. A warning is "
                    "advisory; retain evidence if the warning is a false alarm."
                )

""",
        ),
    ],
}


def main():
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Use the project's Python 3.11 environment.")

    root = Path.cwd()
    original = {name: (root / name).read_text(encoding="utf-8") for name in EDITS}

    installed = (
        '"evidence_revision_attempted"' in original["src/maintlog/agent.py"],
        'focused_context["evidence_revision"]' in original["src/maintlog/backends.py"],
    )

    if all(installed):
        print("Bounded revision already installed; no changes.")
        return
    if any(installed):
        raise SystemExit("Partial installation detected. Nothing changed.")

    revised = {}
    for name, changes in EDITS.items():
        text = original[name]
        for old, new in changes:
            if text.count(old) != 1:
                raise SystemExit(f"Unexpected source in {name}. Nothing changed.")
            text = text.replace(old, new, 1)
        compile(text, name, "exec")
        revised[name] = text

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = root / "artifacts" / ("evidence-revision-backup-" + stamp)
    backup.mkdir(parents=True, exist_ok=False)

    for name in original:
        shutil.copy2(root / name, backup / Path(name).name)

    try:
        for name, text in revised.items():
            (root / name).write_text(text, encoding="utf-8")
    except Exception:
        for name in original:
            shutil.copy2(backup / Path(name).name, root / name)
        raise

    print(f"Bounded revision installed. Originals: {backup}")


if __name__ == "__main__":
    main()
