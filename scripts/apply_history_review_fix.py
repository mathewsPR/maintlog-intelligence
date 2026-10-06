"""Patch only extraction instructions and attach a source-backed history."""

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

RULES = '''
EXTRACTION_SYSTEM += """
Evidence selection rules:
- Select the complete equipment part phrase, including the head noun that names
  the item found faulty or worked on. A connector, cable, seal, housing or other
  subpart is not interchangeable with its parent assembly. Do not cut off that
  head noun merely because the parent name is already recognizable.
- Preserve location and identifying modifiers belonging to that part phrase.
  Exclude diagnostic verbs and condition words from component.
- Action should contain one complete statement of the selected maintenance work
  and its object. Omit administrative headings and independent preceding
  diagnostic statements when they are unnecessary to establish the work.
- A clause that combines the observed condition with the performed work may
  remain intact when shortening would lose the object or execution meaning.
- Keep independent subsequent tests and outcomes out of a repair excerpt.
  If the selected action is itself a test, retain that test and its relevant
  execution or verification wording. Never remove qualifying evidence needed
  to support the selected status.
- Prefer exact quote spans for unique text. Do not calculate offsets merely
  because component selection mode is unavailable.
- For quotes, omit a terminal sentence-ending period when it is not part of
  an abbreviation, identifier or number. Preserve all internal punctuation.
"""
'''

HISTORY = """    history_review = None
    if requirements["mode"] == "history" and result["status"] == "ready_for_review":
        try:
            history_review = build_history_review(
                [by_id[record_id] for record_id in final_ids], list(proposals.values())
            )
        except (ValueError, TypeError, KeyError) as exc:
            history_review = {
                "status": "blocked_invalid_evidence",
                "error": str(exc),
                "semantic_task_success": None,
            }

"""


def once(text, old, new, label):
    if text.count(old) != 1:
        raise SystemExit(f"Unexpected {label}; no production files changed.")
    return text.replace(old, new, 1)


def main():
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Activate your Python 3.11 environment.")

    root = Path.cwd()
    source = root / "src/maintlog"

    if not (source / "working_context.py").is_file():
        raise SystemExit("Install the previous reliability correction first.")

    if not (source / "history_review.py").is_file():
        raise SystemExit("Save history_review.py before running this script.")

    backend = source / "backends.py"
    agent = source / "agent.py"

    backend_text = backend.read_text(encoding="utf-8")
    agent_text = agent.read_text(encoding="utf-8")

    done = (
        "Evidence selection rules:" in backend_text,
        '"history_review": history_review,' in agent_text,
    )

    if all(done):
        print("History correction already present; no files changed.")
        return

    if any(done) or "from .history_review import" in agent_text:
        raise SystemExit("Partial correction detected; no production files changed.")

    updated_backend = once(
        backend_text,
        "\nEXTRACTION_SCHEMA = obj(",
        "\n" + RULES + "\nEXTRACTION_SCHEMA = obj(",
        "backend schema anchor",
    )

    updated_agent = once(
        agent_text,
        "from .domain import Record\n",
        "from .domain import Record\n"
        "from .history_review import build_history_review\n",
        "agent import anchor",
    )

    updated_agent = once(
        updated_agent,
        '    return {\n        "schema_version": 2,',
        HISTORY + '    return {\n        "schema_version": 2,',
        "agent report anchor",
    )

    updated_agent = once(
        updated_agent,
        '        "records_for_review": '
        "[asdict(by_id[record_id]) for record_id in final_ids],",
        '        "history_review": history_review,\n'
        '        "records_for_review": '
        "[asdict(by_id[record_id]) for record_id in final_ids],",
        "selected records anchor",
    )

    compile(updated_backend, str(backend), "exec")
    compile(updated_agent, str(agent), "exec")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = root / "artifacts" / ("history-review-backup-" + stamp)
    backup.mkdir(parents=True, exist_ok=False)

    shutil.copy2(backend, backup / "backends.py")
    shutil.copy2(agent, backup / "agent.py")

    try:
        backend.write_text(updated_backend, encoding="utf-8")
        agent.write_text(updated_agent, encoding="utf-8")
    except Exception:
        shutil.copy2(backup / "backends.py", backend)
        shutil.copy2(backup / "agent.py", agent)
        raise

    print(f"Updated backends.py and agent.py. Originals: {backup}")


if __name__ == "__main__":
    main()
