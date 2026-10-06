"""Attach targeted evidence concerns to the completed history output."""

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

CHECKS = """    checked = [
        {"record_id": entry["record_id"], "fields": entry["fields"]}
        for entry in entries
    ]
    evidence_review = review_evidence(records, checked)

    if evidence_review["concerns"]:
        lines.insert(
            1,
            "Evidence review required: unresolved extraction concerns.",
        )
        lines.append("Extraction concerns:")
        for concern in evidence_review["concerns"]:
            lines.append(
                f"{concern['record_id']} / {concern['field']}: "
                f"{concern['message']}"
            )

    lines.append(LIMITATIONS)"""

STATUS = """        "status": (
            "needs_evidence_review"
            if evidence_review["concerns"]
            else "available_for_review"
        ),
        "evidence_review": evidence_review,"""


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(
            "Unexpected history_review.py implementation. Nothing changed."
        )
    return text.replace(old, new, 1)


def main():
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Activate your Python 3.11 environment.")

    root = Path.cwd()
    target = root / "src/maintlog/history_review.py"
    checker = root / "src/maintlog/evidence_review.py"

    if not target.is_file() or not checker.is_file():
        raise SystemExit("Save both production files before applying the gate.")

    text = target.read_text(encoding="utf-8")

    if '"evidence_review": evidence_review,' in text:
        print("Evidence-review gate already present; no changes.")
        return

    if "from .evidence_review import" in text:
        raise SystemExit("Partial integration detected. Nothing changed.")

    updated = replace_once(
        text,
        "from .domain import Record\n",
        "from .domain import Record\nfrom .evidence_review import review_evidence\n",
    )
    updated = replace_once(
        updated,
        "    lines.append(LIMITATIONS)",
        CHECKS,
    )
    updated = replace_once(
        updated,
        '        "status": "available_for_review",',
        STATUS,
    )

    compile(updated, str(target), "exec")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = root / "artifacts" / ("evidence-review-backup-" + stamp)
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(target, backup / target.name)

    try:
        target.write_text(updated, encoding="utf-8")
    except Exception:
        shutil.copy2(backup / target.name, target)
        raise

    print(f"Evidence-review gate installed. Original: {backup}")


if __name__ == "__main__":
    main()
