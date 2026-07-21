"""Model-neutral, evidence-bound proposals from an optional AI host."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


@dataclass(frozen=True)
class ProposedFact:
    field: str
    value: str
    evidence: str
    confidence: float
    evidence_type: str = "source_text"


@dataclass(frozen=True)
class AIProposal:
    document_id: str
    provider_id: str
    document_type: str
    facts: tuple[ProposedFact, ...]
    uncertainties: tuple[str, ...]
    overall_confidence: float
    transcription: str = ""

    @classmethod
    def from_dict(cls, value: dict) -> "AIProposal":
        facts = tuple(ProposedFact(**fact) for fact in value.get("facts", []))
        return cls(
            document_id=value["document_id"],
            provider_id=value["provider_id"],
            document_type=value["document_type"],
            facts=facts,
            uncertainties=tuple(value.get("uncertainties", [])),
            overall_confidence=float(value["overall_confidence"]),
            transcription=value.get("transcription", ""),
        )

    def as_dict(self) -> dict:
        return asdict(self)


def validate_proposal(proposal: AIProposal, source_text: str, *, source_format: str = "txt") -> tuple[str, ...]:
    """Reject unsupported claims before they reach durable metadata.

    A host may be Gemini, ChatGPT, Claude, or a local model. Its confidence is
    recorded, but every proposed fact must quote evidence actually present in
    the selected source. Relationship/identity rules remain in the core.
    """
    errors = []
    if not 0.0 <= proposal.overall_confidence <= 1.0:
        errors.append("overall_confidence must be between 0 and 1")
    for fact in proposal.facts:
        if not 0.0 <= fact.confidence <= 1.0:
            errors.append(f"{fact.field}: confidence must be between 0 and 1")
        if fact.evidence_type not in {"source_text", "visual_evidence"}:
            errors.append(f"{fact.field}: evidence_type must be source_text or visual_evidence")
        elif not fact.evidence.strip():
            errors.append(f"{fact.field}: evidence is required")
        elif fact.evidence_type == "source_text" and _normalized(fact.evidence) not in _normalized(source_text):
            errors.append(f"{fact.field}: quoted evidence is not present in the source")
        elif fact.evidence_type == "visual_evidence" and source_format.casefold() not in {"pdf", "png", "jpg", "jpeg", "heic", "tif", "tiff"}:
            errors.append(f"{fact.field}: visual evidence is only valid for an original scan or image")
    return tuple(errors)
