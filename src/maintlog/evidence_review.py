"""Advisory evidence checks; never a semantic approval or automatic repair."""

import re

SUBPART = re.compile(
    r"^\s+(?:(?:electrical|hydraulic|pneumatic|mechanical|power|signal)\s+)?"
    r"(?:connector|cable|seal|housing|plug|wire|terminal)\b",
    re.I,
)
CORRECTIVE = re.compile(
    r"\b(?:corrective\s+action|c/a)\s*[:\-]",
    re.I,
)
DIAGNOSTIC = re.compile(
    r"^\s*(?:found|diagnosed|identified)\b",
    re.I,
)


def review_evidence(records: list, proposals: list[dict]) -> dict:
    """Flag narrow concerns without changing evidence or action status.

    Caller supplies source-validated, resolved spans. A flag means inspect the
    excerpt, not that an error has been proved. Absence of flags is not approval.
    """
    sources = {record.record_id: record for record in records}
    concerns = []

    for proposal in proposals:
        rid = proposal["record_id"]
        if rid not in sources:
            continue

        record = sources[rid]
        fields = proposal["fields"]

        component = fields["component"]
        if component is not None:
            source = getattr(record, component["field"])
            match = SUBPART.match(source[component["end"] :])

            if match:
                concerns.append(
                    {
                        "record_id": rid,
                        "field": "component",
                        "code": "possible_omitted_subpart",
                        "message": (
                            "The selected component ends before a following "
                            "subpart noun; review the complete object involved "
                            "in the work."
                        ),
                        "source_continuation": match.group(),
                    }
                )

        problem = fields["problem"]
        if problem is not None:
            source = getattr(record, problem["field"])
            heading = CORRECTIVE.search(source)

            if (
                heading is not None
                and problem["start"] >= heading.end()
                and DIAGNOSTIC.match(problem["quote"])
            ):
                concerns.append(
                    {
                        "record_id": rid,
                        "field": "problem",
                        "code": "possible_diagnosis_in_symptom_field",
                        "message": (
                            "The problem excerpt is a diagnostic finding after "
                            "a corrective-action heading; review whether the "
                            "reported symptom was omitted."
                        ),
                    }
                )

        action = fields["action"]
        if action is not None and CORRECTIVE.match(action["quote"].lstrip()):
            concerns.append(
                {
                    "record_id": rid,
                    "field": "action",
                    "code": "action_contains_administrative_heading",
                    "message": (
                        "The action includes a corrective-action heading; "
                        "review its boundary and whether separate work or "
                        "checks were combined."
                    ),
                }
            )

    return {
        "method": "targeted_evidence_review_v1",
        "status": (
            "concerns_detected" if concerns else "no_targeted_concerns_detected"
        ),
        "concerns": concerns,
        "semantic_accuracy": None,
        "interpretation": (
            "Advisory checks only. Neither a warning nor its absence "
            "establishes semantic correctness. Source evidence is never "
            "rewritten."
        ),
    }
