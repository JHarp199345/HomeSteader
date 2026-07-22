"""Generic, evidence-backed document extraction contract."""

from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True)
class ExtractedFact:
    field: str
    value: str
    evidence: str
    provenance: str = "document_text"
    confidence: float = 1.0


def is_template_placeholder(val: str) -> bool:
    clean = val.strip("_.- ").casefold()
    return len(clean) == 0 or "hmis id" in clean or "participant" in clean or "________________" in val

def labeled_fact(text: str, label: str, field: str) -> ExtractedFact | None:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    val = match.group(1).strip()
    if is_template_placeholder(val):
        return None
    return ExtractedFact(field=field, value=val, evidence=match.group(0).strip())



def extract_common_facts(text: str) -> dict[str, dict]:
    """Extract labeled facts with source evidence.

    Future OCR and AI adapters must return this same field/evidence/provenance/
    confidence shape rather than bare values.
    """
    labels = {
        "Tenant": "tenant", "Participant": "participant", "Name": "participant", "Landlord": "landlord", "Program": "program",
        "HMIS number": "hmis_id", "HMIS ID": "hmis_id", "HMIS ID #": "hmis_id",
        "Date of birth": "date_of_birth", "Document date": "document_date", "Enrollment date": "enrollment_date", "Exit date": "exit_date", "Reporting period": "reporting_period",
        "Primary care provider": "primary_care_provider", "Mental health provider": "mental_health_provider",
        "Primary Care Provider Name": "primary_care_provider", "Mental Health Provider Name": "mental_health_provider",
        "Emergency contact": "emergency_contact", "Emergency Contact Name": "emergency_contact",
    }
    facts = {}
    for label, field in labels.items():
        fact = labeled_fact(text, label, field)
        if fact and field not in facts:
            facts[field] = asdict(fact)
    return facts
