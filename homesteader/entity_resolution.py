"""Evidence-aware person resolution for unordered document intake."""

from dataclasses import dataclass
from enum import StrEnum


class IdentityDecision(StrEnum):
    CREATE_PROVISIONAL = "create_provisional"
    PROPOSE_EXISTING = "propose_existing"
    REVIEW = "needs_review"


@dataclass(frozen=True)
class PersonCandidate:
    entity_id: str
    name: str
    date_of_birth: str | None = None
    emergency_contact: str | None = None
    primary_care_provider: str | None = None
    mental_health_provider: str | None = None
    hmis_id: str | None = None


@dataclass(frozen=True)
class IdentityMatch:
    decision: IdentityDecision
    candidates: tuple[str, ...]
    reasons: tuple[str, ...]


def resolve_person(*, name: str, date_of_birth: str | None, candidates: list[PersonCandidate], hmis_id: str | None = None) -> IdentityMatch:
    """Resolve only what the evidence can support.

    A name is a search key, not a unique identity. Date of birth is treated as a
    hard disambiguator when supplied. Contact/provider data can later rank
    candidates but cannot prove identity by itself because households and
    providers can be shared.
    """
    if hmis_id:
        exact_hmis = [candidate for candidate in candidates if candidate.hmis_id == hmis_id]
        if len(exact_hmis) == 1:
            return IdentityMatch(IdentityDecision.PROPOSE_EXISTING, (exact_hmis[0].entity_id,), ("Exact HMIS number match.",))
        if len(exact_hmis) > 1:
            return IdentityMatch(IdentityDecision.REVIEW, tuple(candidate.entity_id for candidate in exact_hmis), ("More than one identity has this HMIS number; resolve the data-integrity conflict.",))
        return IdentityMatch(IdentityDecision.CREATE_PROVISIONAL, (), ("No existing identity has this HMIS number.",))
    same_name = [candidate for candidate in candidates if candidate.name.casefold() == name.casefold()]
    if not same_name:
        return IdentityMatch(IdentityDecision.CREATE_PROVISIONAL, (), ("No existing person has this name.",))
    if date_of_birth:
        exact = [candidate for candidate in same_name if candidate.date_of_birth == date_of_birth]
        if len(exact) == 1:
            return IdentityMatch(IdentityDecision.PROPOSE_EXISTING, (exact[0].entity_id,), ("Exact name and date-of-birth match.",))
        if len(exact) > 1:
            return IdentityMatch(IdentityDecision.REVIEW, tuple(candidate.entity_id for candidate in exact), ("More than one existing identity has the same name and date of birth.",))
        conflicts = [candidate for candidate in same_name if candidate.date_of_birth and candidate.date_of_birth != date_of_birth]
        if conflicts:
            return IdentityMatch(IdentityDecision.CREATE_PROVISIONAL, (), ("Same-name candidates have conflicting dates of birth; create a separate provisional identity.",))
    if len(same_name) == 1:
        # A participant name alone NEVER files a document automatically.
        # When HMIS ID is missing and DOB is missing, route to Needs Review.
        return IdentityMatch(IdentityDecision.REVIEW, tuple(candidate.entity_id for candidate in same_name), ("Document carries participant name but lacks corroborating hard identifier (HMIS ID or DOB). Select or confirm intended participant.",))
    return IdentityMatch(IdentityDecision.REVIEW, tuple(candidate.entity_id for candidate in same_name), ("Multiple people share this name and no hard identifier selects one.",))

