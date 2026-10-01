"""Deterministic workflow requirements, separate from semantic task success."""

from dataclasses import asdict, dataclass

MODES = ("history", "search", "inspect", "extract")


@dataclass(frozen=True)
class TaskSpec:
    mode: str = "history"
    initial_query: str | None = None

    def requirements(self) -> dict:
        if self.mode not in MODES:
            raise ValueError("unsupported task mode")
        if self.initial_query is not None and (
            not isinstance(self.initial_query, str)
            or not self.initial_query.strip()
            or len(self.initial_query) > 500
        ):
            raise ValueError("invalid initial query")
        return {
            **asdict(self),
            "search_required": self.mode in {"history", "search"},
            "aggregate_required": self.mode == "history",
            "inspect_every_final_record": True,
            "extract_every_final_record": self.mode == "extract",
            "extract_final_narratives": self.mode == "history",
        }


def check_finish(
    ids: list[str],
    requirements: dict,
    inspected: set[str],
    proposals: dict,
    records: dict,
    searches: int,
    found: set[str],
    aggregate_done: bool,
) -> dict:
    missing = []
    if requirements["search_required"] and not searches:
        missing.append("perform a search")
    if requirements["aggregate_required"] and not aggregate_done:
        missing.append("compute the full-scope aggregate")
    if not ids:
        if not searches or found:
            missing.append(
                "empty finish requires a completed search with no hits; use abstain if relevance is uncertain"
            )
    for rid in ids:
        if rid not in inspected:
            missing.append(f"inspect {rid}")
        if requirements["extract_every_final_record"] or (
            requirements["extract_final_narratives"] and records[rid].narrative_raw
        ):
            if rid not in proposals:
                missing.append(f"extract or explicitly mark unknown fields for {rid}")
    return {
        "requirements_met": not missing,
        "missing": missing,
        "outcome": "evidence_selected" if ids else "no_lexical_matches",
        "semantic_task_success": None,
        "interpretation": "Workflow checks do not establish relevance, classification accuracy or complete recall.",
    }
