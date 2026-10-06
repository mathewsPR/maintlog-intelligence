"""Constrain omitted-subpart revisions in both backend and agent executor."""

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_BLOCK = r"""        corrected_component = None
        revision = context.get("evidence_revision")
        if isinstance(extraction_record, dict) and isinstance(revision, dict):
            corrected_component = component_revision_candidate(
                extraction_record, revision
            )
            if corrected_component is not None:
                candidates = {}
                response_schema = deepcopy(EXTRACTION_SCHEMA)
                args_schema = response_schema["properties"]["args"]
                args_schema["properties"]["record_id"] = {
                    "type": "string",
                    "enum": [extraction_record["record_id"]],
                }

                previous_component = revision["previous_proposal"]["fields"][
                    "component"
                ]
                original_component = {
                    key: previous_component[key]
                    for key in ("field", "start", "end")
                }
                options = [original_component, corrected_component]

                args_schema["properties"]["fields"]["properties"]["component"] = {
                    "anyOf": [
                        obj(
                            {
                                key: {
                                    "type": (
                                        "string" if key == "field" else "integer"
                                    ),
                                    "enum": [value],
                                }
                                for key, value in option.items()
                            }
                        )
                        for option in options
                    ]
                }

                context.pop("component_candidates", None)
                context.pop("component_feedback_note", None)
                context["component_span_options"] = options
                system = EXTRACTION_SYSTEM + (
                    "\nChoose fields.component exactly from component_span_options. "
                    "They contain the original span and its adjacent source subpart. "
                    "Retain the original when the warning is a false alarm. "
                    "Revise other flagged fields using evidence_revision; preserve "
                    "unflagged fields and action_status. Do not invent offsets."
                )

"""

AGENT_BLOCK = """                    original_component = previous["fields"]["component"]
                    if original_component is not None:
                        source_context = {
                            "record_id": record_id,
                            original_component["field"]: getattr(
                                by_id[record_id], original_component["field"]
                            ),
                        }
                        candidate = component_revision_candidate(
                            source_context, active_revision
                        )
                        if candidate is not None:
                            options = [
                                {
                                    key: original_component[key]
                                    for key in ("field", "start", "end")
                                },
                                candidate,
                            ]
                            supplied = spans["component"]
                            if supplied is None:
                                raise ValueError(
                                    "evidence revision cannot discard previous evidence"
                                )
                            if {
                                key: supplied[key]
                                for key in ("field", "start", "end")
                            } not in options:
                                raise ValueError(
                                    "component revision is outside source-backed boundary choices"
                                )
"""


def once(text, old, new, name):
    if text.count(old) != 1:
        raise SystemExit(f"Unexpected source in {name}. Nothing changed.")
    return text.replace(old, new, 1)


def main():
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Activate your Python 3.11 environment.")

    root = Path.cwd()
    module = root / "src/maintlog/revision_component.py"
    if not module.is_file():
        raise SystemExit("Save revision_component.py first.")

    paths = {
        "agent": root / "src/maintlog/agent.py",
        "backends": root / "src/maintlog/backends.py",
    }
    originals = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}

    installed = [
        "from .revision_component import component_revision_candidate" in text
        for text in originals.values()
    ]
    if all(installed):
        print("Component boundary correction already present.")
        return
    if any(installed):
        raise SystemExit("Partial correction detected. Nothing changed.")

    agent = once(
        originals["agent"],
        "from .retrieval import search\n",
        "from .retrieval import search\n"
        "from .revision_component import component_revision_candidate\n",
        "agent.py",
    )
    anchor = (
        "                    flagged = "
        '{item["field"] for item in active_revision["concerns"]}\n'
    )
    agent = once(agent, anchor, anchor + AGENT_BLOCK, "agent.py")

    backend = once(
        originals["backends"],
        "from .extraction import STATUS_GUIDANCE\n",
        "from .extraction import STATUS_GUIDANCE\n"
        "from .revision_component import component_revision_candidate\n",
        "backends.py",
    )
    backend = once(
        backend,
        "        self.request_count += 1\n",
        BACKEND_BLOCK + "        self.request_count += 1\n",
        "backends.py",
    )

    updates = {"agent": agent, "backends": backend}
    for name, text in updates.items():
        compile(text, str(paths[name]), "exec")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = root / "artifacts" / ("component-boundary-backup-" + stamp)
    backup.mkdir(parents=True, exist_ok=False)

    for path in paths.values():
        shutil.copy2(path, backup / path.name)

    try:
        for name, text in updates.items():
            paths[name].write_text(text, encoding="utf-8")
    except Exception:
        for path in paths.values():
            shutil.copy2(backup / path.name, path)
        raise

    print(f"Component boundary correction installed. Originals: {backup}")


if __name__ == "__main__":
    main()
