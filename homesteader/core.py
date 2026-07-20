from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import uuid4

from .assurance import Decision, assess_relationship
from .case_management import DOCUMENT_RULES
from .entity_resolution import IdentityDecision, PersonCandidate, resolve_person
from .extraction import extract_common_facts


def now() -> str:
    return datetime.now(UTC).isoformat()


def normalized_content_hash(text: str) -> str:
    """Fingerprint text while ignoring casing, whitespace, and punctuation-only changes.

    Matching fingerprints are *near-duplicate candidates*, not proof that two
    records are interchangeable. OCR and form variation can still matter.
    """
    normalized = re.sub(r"[^a-z0-9]+", "", text.lower())
    return sha256(normalized.encode()).hexdigest()


@dataclass
class ExtractedDocument:
    document_type: str
    tenant: str | None = None
    participant: str | None = None
    program: str | None = None
    property_address: str | None = None
    unit: str | None = None
    signed_date: str | None = None
    document_date: str | None = None
    reporting_period: str | None = None
    date_of_birth: str | None = None
    primary_care_provider: str | None = None
    mental_health_provider: str | None = None
    emergency_contact: str | None = None
    hmis_id: str | None = None
    referenced_lease_date: str | None = None


def find_value(label: str, text: str) -> str | None:
    match = re.search(rf"^{label}:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def extract_document(text: str) -> ExtractedDocument:
    upper = text.upper()
    facts = extract_common_facts(text)
    def value(field: str) -> str | None:
        return facts.get(field, {}).get("value")
    document_type = "unknown"
    signature = find_value("Signature", text) or find_value("Signed", text)
    has_nonblank_signature = bool(signature and signature.replace("_", "").strip())
    has_completed_identity = bool(value("tenant") or value("participant") or find_value("Premises", text) or has_nonblank_signature)
    if "INCOME DECLARATION" in upper:
        document_type = "income_declaration"
    elif "CONTACT INFORMATION SHEET" in upper:
        document_type = "contact_information"
    elif "PROGRAM ENROLLMENT" in upper:
        document_type = "program_enrollment"
    elif "CONSENT TO SHARE PROTECTED PERSONAL INFORMATION" in upper and not has_completed_identity:
        document_type = "form_template"
    elif "CONSENT TO SHARE PROTECTED PERSONAL INFORMATION" in upper:
        document_type = "consent_to_share"
    elif "PET" in upper and "ADDENDUM" in upper:
        document_type = "lease_addendum"
    elif "LEASE" in upper:
        document_type = "lease"

    premises = find_value("Premises", text)
    property_address = unit = None
    if premises:
        match = re.match(r"(.+?),\s*(?:Apartment|Unit)\s+(.+)$", premises, re.IGNORECASE)
        if match:
            property_address, unit = match.group(1).strip(), match.group(2).strip()
        else:
            property_address = premises

    referenced = re.search(r"(?:executed|dated)\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", text)
    return ExtractedDocument(
        document_type=document_type,
        tenant=value("tenant"),
        participant=value("participant"),
        program=value("program"),
        property_address=property_address,
        unit=unit,
        signed_date=find_value("Lease signed", text),
        document_date=value("document_date"),
        reporting_period=value("reporting_period"),
        date_of_birth=value("date_of_birth"),
        primary_care_provider=value("primary_care_provider"),
        mental_health_provider=value("mental_health_provider"),
        emergency_contact=value("emergency_contact"),
        hmis_id=value("hmis_id"),
        referenced_lease_date=referenced.group(1) if referenced else None,
    )


class HomesteaderStore:
    """Small JSON-backed store. Events are appended; original source is preserved."""

    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            data.setdefault("intake_occurrences", [])
            data.setdefault("counters", {"temporary_file": 0})
            return data
        return {"documents": [], "intake_occurrences": [], "entities": [], "relationships": [], "ledger_events": [], "review_queue": [], "counters": {"temporary_file": 0}}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")

    def _entity(self, kind: str, name: str) -> dict:
        existing = next((e for e in self.data["entities"] if e["kind"] == kind and e["name"] == name), None)
        if existing:
            return existing
        entity = {"id": str(uuid4()), "kind": kind, "name": name, "created_at": now()}
        self.data["entities"].append(entity)
        return entity

    def _new_entity(self, kind: str, name: str, **attributes: str | None) -> dict:
        """Create a distinct provisional entity even when names collide."""
        entity = {"id": str(uuid4()), "kind": kind, "name": name, "created_at": now(), "attributes": attributes, "provisional": True}
        self.data["entities"].append(entity)
        return entity

    def create_temporary_file(self, name: str) -> dict:
        self.data["counters"]["temporary_file"] += 1
        temporary_id = f"T-{self.data['counters']['temporary_file']:06d}"
        person = self._new_entity("person", name, temporary_id=temporary_id)
        ledger = self._participant_ledger(person)
        self._event("temporary_file_created", ledger["id"], {"person_id": person["id"], "temporary_id": temporary_id})
        return {"person_id": person["id"], "temporary_id": temporary_id, "participant_ledger_id": ledger["id"]}

    def search_files(self, query: str) -> list[dict]:
        needle = query.casefold().strip()
        return [{"person_id": entity["id"], "name": entity["name"], "hmis_id": entity.get("attributes", {}).get("hmis_id"), "temporary_id": entity.get("attributes", {}).get("temporary_id"), "status": "confirmed" if entity.get("attributes", {}).get("hmis_id") else "temporary"} for entity in self.data["entities"] if entity["kind"] == "person" and needle in " ".join([entity["name"], str(entity.get("attributes", {}).get("hmis_id") or ""), str(entity.get("attributes", {}).get("temporary_id") or "")]).casefold()]

    def confirm_hmis_identity(self, person_id: str, hmis_id: str, note: str | None = None) -> dict:
        person = next((entity for entity in self.data["entities"] if entity["id"] == person_id and entity["kind"] == "person"), None)
        if not person:
            raise ValueError("Participant file does not exist.")
        existing = next((entity for entity in self.data["entities"] if entity["kind"] == "person" and entity.get("attributes", {}).get("hmis_id") == hmis_id and entity["id"] != person_id), None)
        if existing:
            raise ValueError("That HMIS number already belongs to another file; use review/merge instead.")
        attributes = person.setdefault("attributes", {})
        temporary_id = attributes.pop("temporary_id", None)
        attributes["hmis_id"] = hmis_id
        person["provisional"] = False
        ledger = self._participant_ledger(person)
        self._event("hmis_identity_confirmed", ledger["id"], {"person_id": person_id, "replaced_temporary_id": temporary_id, "hmis_id": hmis_id, "note": note})
        return {"person_id": person_id, "hmis_id": hmis_id, "replaced_temporary_id": temporary_id, "participant_ledger_id": ledger["id"]}

    def _event(self, event_type: str, subject_id: str, details: dict) -> None:
        self.data["ledger_events"].append({"id": str(uuid4()), "type": event_type, "subject_id": subject_id, "details": details, "recorded_at": now()})

    def _relationship(self, relationship_type: str, from_entity_id: str, to_entity_id: str, source: str) -> dict:
        existing = next((relationship for relationship in self.data["relationships"] if relationship.get("type") == relationship_type and relationship.get("from_entity_id") == from_entity_id and relationship.get("to_entity_id") == to_entity_id), None)
        if existing:
            return existing
        relationship = {"id": str(uuid4()), "type": relationship_type, "from_entity_id": from_entity_id, "to_entity_id": to_entity_id, "provenance": source, "created_at": now()}
        self.data["relationships"].append(relationship)
        return relationship

    def ingest(self, source: Path) -> dict:
        text = source.read_text()
        extracted = extract_document(text)
        content_hash = sha256(text.encode()).hexdigest()
        normalized_hash = normalized_content_hash(text)
        occurrence = {"id": str(uuid4()), "source_name": source.name, "sha256": content_hash, "observed_at": now()}
        self.data["intake_occurrences"].append(occurrence)
        duplicate = next((item for item in self.data["documents"] if item["sha256"] == content_hash), None)
        if duplicate:
            self._event("duplicate_candidate_detected", duplicate["id"], {"intake_occurrence_id": occurrence["id"], "attempted_name": source.name, "sha256": content_hash, "source": "exact_content_hash"})
            return self._review_existing(
                duplicate,
                f"Exact content match. Confirm whether this is an accidental duplicate or a separate recurring intake occurrence.",
                occurrence["id"],
            )
        document = {
            "id": str(uuid4()), "original_name": source.name, "sha256": content_hash,
            "normalized_sha256": normalized_hash,
            "source_text": text, "extracted": asdict(extracted), "ingested_at": now(),
        }
        self.data["documents"].append(document)

        near_duplicate = next(
            (item for item in self.data["documents"][:-1] if item.get("normalized_sha256") == normalized_hash),
            None,
        )
        if near_duplicate:
            self._event("possible_duplicate_detected", near_duplicate["id"], {
                "candidate_document_id": document["id"],
                "source": "normalized_content_hash",
            })
            result = self._review(
                document,
                f"Likely near duplicate of '{near_duplicate['original_name']}' after ignoring casing, whitespace, and punctuation. Confirm whether it is a duplicate or a distinct version.",
            )
            result["possible_duplicate_of"] = near_duplicate["id"]
            return result

        if extracted.document_type == "lease":
            return self._create_lease(document, extracted)
        if extracted.document_type == "lease_addendum":
            return self._link_addendum(document, extracted)
        if extracted.document_type == "income_declaration":
            return self._record_income_declaration(document, extracted)
        if extracted.document_type == "contact_information":
            return self._record_contact_information(document, extracted)
        if extracted.document_type in {"program_enrollment", "consent_to_share"}:
            return self._record_case_document(document, extracted)
        if extracted.document_type == "form_template":
            return self._catalog_form(document)
        return self._review(document, "Document type is not supported by the v0 prototype.")

    def _record_income_declaration(self, document: dict, extracted: ExtractedDocument) -> dict:
        if not extracted.participant:
            return self._review(document, "Income declaration has no participant identity.")
        if not extracted.reporting_period:
            return self._review(document, "Income declaration is undated or lacks a reporting period. The source remains undated; provide context later if available.")
        participant, review = self._resolve_person_for_document(document, extracted)
        if review:
            return review
        ledger = self._income_ledger(participant)
        self._event("income_declaration_recorded", ledger["id"], {
            "document_id": document["id"], "participant_id": participant["id"],
            "document_date": extracted.document_date, "reporting_period": extracted.reporting_period,
            "source": "document_extraction",
        })
        return {"status": "filed", "document_id": document["id"], "income_ledger_id": ledger["id"], "reporting_period": extracted.reporting_period, "confidence": 1.0, "reasons": ["Participant and reporting period are stated in the source document."]}

    def _record_case_document(self, document: dict, extracted: ExtractedDocument) -> dict:
        rule = DOCUMENT_RULES[extracted.document_type]
        values = {"participant": extracted.participant, "program": extracted.program, "hmis_id": extracted.hmis_id}
        missing = [field for field in rule.required_fields if not values.get(field)]
        if missing:
            return self._review(document, f"{extracted.document_type} lacks required case identity: {', '.join(sorted(missing))}.")
        participant, review = self._resolve_person_for_document(document, extracted)
        if review:
            return review
        program = self._entity("program", extracted.program)
        case_ledger = self._entity("case_ledger", f"{participant['id']} / {extracted.program}")
        self._relationship("enrolled_in", participant["id"], program["id"], "document_extraction")
        self._relationship("has_case", participant["id"], case_ledger["id"], "document_extraction")
        self._event(rule.ledger_event, case_ledger["id"], {
            "document_id": document["id"], "participant_id": participant["id"], "program_id": program["id"],
            "document_date": extracted.document_date, "source": "document_extraction",
        })
        return {"status": "filed", "document_id": document["id"], "case_ledger_id": case_ledger["id"], "document_type": extracted.document_type, "confidence": 1.0, "reasons": ["Participant and program are stated in the source document."]}

    def _person_candidates(self) -> list[PersonCandidate]:
        return [
            PersonCandidate(
                entity_id=entity["id"], name=entity["name"],
                date_of_birth=entity.get("attributes", {}).get("date_of_birth"),
                emergency_contact=entity.get("attributes", {}).get("emergency_contact"),
                primary_care_provider=entity.get("attributes", {}).get("primary_care_provider"),
                mental_health_provider=entity.get("attributes", {}).get("mental_health_provider"),
                hmis_id=entity.get("attributes", {}).get("hmis_id"),
            )
            for entity in self.data["entities"] if entity["kind"] == "person"
        ]

    def _resolve_person_for_document(self, document: dict, extracted: ExtractedDocument) -> tuple[dict | None, dict | None]:
        """Resolve without assuming documents arrive in a profile-first order."""
        if not extracted.hmis_id:
            return None, self._review(document, "Case document lacks an HMIS number. It cannot be automatically assigned to a participant.")
        match = resolve_person(
            name=extracted.participant,
            date_of_birth=extracted.date_of_birth,
            candidates=self._person_candidates(), hmis_id=extracted.hmis_id,
        )
        if match.decision is IdentityDecision.REVIEW:
            rows = [{"entity_id": candidate.entity_id, "name": candidate.name, "date_of_birth": candidate.date_of_birth} for candidate in self._person_candidates() if candidate.entity_id in match.candidates]
            return None, self._review(document, "; ".join(match.reasons), rows)
        if match.decision is IdentityDecision.CREATE_PROVISIONAL:
            return self._new_entity("person", extracted.participant, date_of_birth=extracted.date_of_birth, hmis_id=extracted.hmis_id), None
        return next(entity for entity in self.data["entities"] if entity["id"] == match.candidates[0]), None

    def _income_ledger(self, person: dict) -> dict:
        existing = next((entity for entity in self.data["entities"] if entity["kind"] == "income_ledger" and entity.get("attributes", {}).get("person_id") == person["id"]), None)
        if existing:
            return existing
        return self._new_entity("income_ledger", person["name"], person_id=person["id"])

    def _participant_ledger(self, person: dict) -> dict:
        existing = next((entity for entity in self.data["entities"] if entity["kind"] == "participant_ledger" and entity.get("attributes", {}).get("person_id") == person["id"]), None)
        if existing:
            return existing
        ledger = self._new_entity("participant_ledger", person["name"], person_id=person["id"])
        self._relationship("has_participant_ledger", person["id"], ledger["id"], "document_extraction")
        return ledger

    def _record_contact_information(self, document: dict, extracted: ExtractedDocument) -> dict:
        if not extracted.participant:
            return self._review(document, "Contact information sheet has no participant name.")
        person, review = self._resolve_person_for_document(document, extracted)
        if review:
            return review
        attributes = {
            "date_of_birth": extracted.date_of_birth,
            "primary_care_provider": extracted.primary_care_provider,
            "mental_health_provider": extracted.mental_health_provider,
            "emergency_contact": extracted.emergency_contact,
        }
        person.setdefault("attributes", {}).update({key: item for key, item in attributes.items() if item and not person.get("attributes", {}).get(key)})
        association = "hmis_identity_match"
        ledger = self._participant_ledger(person)
        self._event("contact_information_recorded", ledger["id"], {
            "document_id": document["id"], "person_id": person["id"], "association": association,
            "facts": extract_common_facts(document["source_text"]), "source": "document_extraction",
        })
        return {"status": "filed", "document_id": document["id"], "person_id": person["id"], "participant_ledger_id": ledger["id"], "association": association, "reasons": ["Exact HMIS number match or new HMIS identity."]}

    def _catalog_form(self, document: dict) -> dict:
        title = document["source_text"].splitlines()[0].strip().title()
        form = self._entity("form_template", title)
        self._event("form_cataloged", form["id"], {"document_id": document["id"], "source": "characteristic_classification", "reason": "Blank form title with no completed identity fields."})
        return {"status": "filed", "document_id": document["id"], "form_id": form["id"], "destination": "form_bank", "confidence": 0.95, "reasons": ["Recognized blank form title", "No tenant, premises, or signature fields were completed"]}

    def _create_lease(self, document: dict, extracted: ExtractedDocument) -> dict:
        if not all([extracted.tenant, extracted.property_address, extracted.unit, extracted.signed_date]):
            return self._review(document, "Lease is missing an identifier required for safe filing.")
        tenant = self._entity("person", extracted.tenant)
        property_entity = self._entity("property", extracted.property_address)
        unit = self._entity("unit", f"{extracted.property_address} / {extracted.unit}")
        lease = self._entity("lease", f"{extracted.tenant} / {extracted.property_address} / {extracted.unit} / {extracted.signed_date}")
        self._event("lease_created", lease["id"], {"document_id": document["id"], "tenant_id": tenant["id"], "property_id": property_entity["id"], "unit_id": unit["id"], "source": "document_extraction"})
        return {"status": "filed", "document_id": document["id"], "lease_id": lease["id"], "confidence": 1.0, "reasons": ["Lease contains tenant, property, unit, and signing date."]}

    def _link_addendum(self, document: dict, extracted: ExtractedDocument) -> dict:
        required = {"tenant", "property", "unit", "lease_date"}
        observed = {
            field for field, value in {
                "tenant": extracted.tenant,
                "property": extracted.property_address,
                "unit": extracted.unit,
                "lease_date": extracted.referenced_lease_date,
            }.items() if value
        }
        initial_assessment = assess_relationship(
            required_hard_matches=required,
            observed_hard_matches=observed,
            conflicting_identifiers=set(),
            ai_confidence=0.0,
        )
        if initial_assessment.decision is Decision.REVIEW:
            return self._review(document, "; ".join(initial_assessment.reasons))
        candidates = [e for e in self.data["entities"] if e["kind"] == "lease"]
        expected_name = f"{extracted.tenant} / {extracted.property_address} / {extracted.unit} / {extracted.referenced_lease_date}"
        match = next((lease for lease in candidates if lease["name"] == expected_name), None)
        if not match:
            return self._review(document, "No lease matches all hard identifiers; no automatic relationship was created.")
        evidence = ["Exact tenant match", "Exact property match", "Exact unit match", "Explicit referenced lease date match"]
        relationship = {"id": str(uuid4()), "type": "modifies", "from_document_id": document["id"], "to_entity_id": match["id"], "confidence": 1.0, "evidence": evidence, "provenance": "deterministic_v0_match", "created_at": now()}
        self.data["relationships"].append(relationship)
        self._event("document_linked", match["id"], {"document_id": document["id"], "relationship_id": relationship["id"], "relationship": "modifies", "source": "deterministic_v0_match"})
        return {"status": "filed", "document_id": document["id"], "lease_id": match["id"], "confidence": 1.0, "reasons": evidence}

    def _review(self, document: dict, reason: str, candidates: list[dict] | None = None) -> dict:
        item = {"id": str(uuid4()), "document_id": document["id"], "reason": reason, "candidates": candidates or [], "status": "needs_review", "created_at": now()}
        self.data["review_queue"].append(item)
        return {"status": "needs_review", "review_id": item["id"], "document_id": document["id"], "reason": reason, "candidates": item["candidates"]}

    def _review_existing(self, document: dict, reason: str, intake_occurrence_id: str) -> dict:
        item = {"id": str(uuid4()), "document_id": document["id"], "intake_occurrence_id": intake_occurrence_id, "reason": reason, "status": "needs_review", "created_at": now()}
        self.data["review_queue"].append(item)
        return {"status": "needs_review", "document_id": document["id"], "intake_occurrence_id": intake_occurrence_id, "reason": reason}

    def pending_reviews(self) -> list[dict]:
        return [item for item in self.data["review_queue"] if item["status"] == "needs_review"]

    def resolve_review(self, review_id: str, action: str, *, entity_id: str | None = None, new_person_name: str | None = None, note: str | None = None) -> dict:
        item = next((review for review in self.data["review_queue"] if review["id"] == review_id), None)
        if not item:
            raise ValueError(f"Review item '{review_id}' does not exist.")
        if item["status"] != "needs_review":
            raise ValueError(f"Review item '{review_id}' is already resolved.")
        resolution: dict[str, str | None] = {"action": action, "entity_id": entity_id, "note": note}
        if action == "assign_existing":
            if not entity_id or not any(entity["id"] == entity_id for entity in self.data["entities"]):
                raise ValueError("assign_existing requires an existing entity ID.")
        elif action == "create_person":
            if not new_person_name:
                raise ValueError("create_person requires new_person_name.")
            person = self._new_entity("person", new_person_name)
            resolution["entity_id"] = person["id"]
        elif action != "leave_unassigned":
            raise ValueError("Action must be assign_existing, create_person, or leave_unassigned.")
        item["status"] = "resolved"
        item["resolution"] = resolution
        item["resolved_at"] = now()
        self._event("human_review_resolved", item["document_id"], {"review_id": review_id, **resolution})
        return {"status": "resolved", "review_id": review_id, "resolution": resolution}
