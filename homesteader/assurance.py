"""Conservative validation for proposed document relationships.

This module intentionally does not call a model. It evaluates evidence returned
by any model or user workflow before metadata is allowed to become durable.
"""

from dataclasses import dataclass
from enum import StrEnum


class Decision(StrEnum):
    ACCEPT = "accept"
    REVIEW = "needs_review"


@dataclass(frozen=True)
class RelationshipAssessment:
    decision: Decision
    reasons: tuple[str, ...]


def assess_relationship(
    *,
    required_hard_matches: set[str],
    observed_hard_matches: set[str],
    conflicting_identifiers: set[str],
    ai_confidence: float,
    human_confirmed: bool = False,
) -> RelationshipAssessment:
    """Return an explainable decision without treating AI confidence as identity proof."""
    if conflicting_identifiers:
        return RelationshipAssessment(
            Decision.REVIEW,
            ("Conflicting hard identifiers: " + ", ".join(sorted(conflicting_identifiers)),),
        )
    if human_confirmed:
        return RelationshipAssessment(Decision.ACCEPT, ("Human explicitly confirmed this relationship.",))
    missing = required_hard_matches - observed_hard_matches
    if not missing:
        return RelationshipAssessment(
            Decision.ACCEPT,
            ("All required hard identifiers match.", "AI confidence is recorded as supporting evidence only."),
        )
    return RelationshipAssessment(
        Decision.REVIEW,
        (
            "Missing hard identifiers: " + ", ".join(sorted(missing)),
            f"AI confidence ({ai_confidence:.0%}) cannot establish identity by itself.",
        ),
    )
