from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import uuid4

from pypdf import PdfReader

from .assurance import Decision, assess_relationship
from .audit import correction_findings
from .case_management import DOCUMENT_RULES
from .entity_resolution import IdentityDecision, PersonCandidate, resolve_person
from .extraction import extract_common_facts
from .housing_services import add_months, load_program_schedules, schedule_for_program, scheduled_occurrences, write_default_program_schedules
from .move_in import core_record_keys, load_move_in_definition, record_keys, write_default_move_in_definition
from .ocr import recognize_image_with_vision, recognize_pdf_with_vision
from .exporting import export_logical_parts
from .packet_layouts import load_logical_layouts, logical_document_parts, save_logical_layouts, write_default_logical_layouts
from .proposals import AIProposal, validate_proposal


IMAGE_INTAKE_SUFFIXES = {".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff"}
SUPPORTED_INTAKE_SUFFIXES = {".pdf", ".txt", *IMAGE_INTAKE_SUFFIXES}


def now() -> str:
    return datetime.now(UTC).isoformat()


def normalized_content_hash(text: str) -> str:
    """Fingerprint text while ignoring casing, whitespace, and punctuation-only changes.

    Matching fingerprints are *near-duplicate candidates*, not proof that two
    records are interchangeable. OCR and form variation can still matter.
    """
    normalized = re.sub(r"[^a-z0-9]+", "", text.lower())
    return sha256(normalized.encode()).hexdigest()


def normalized_entity_name(value: str) -> str:
    """Normalize presentation differences without asserting two entities match."""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


# These words select a record category for browsing. They are intentionally
# separate from identity aliases: searching "PTC" shows participant files, but
# never claims that two people, owners, or properties are the same record.
BROWSE_KIND_SYNONYMS = {
    "person": {
        "ptc", "ptcs", "participant", "participants", "client", "clients",
        "tenant", "tenants", "person", "people", "resident", "residents",
    },
    "landlord": {
        "landlord", "landlords", "owner", "owners", "property owner",
        "property owners", "housing provider", "housing providers", "lessor", "lessors",
    },
    "property": {
        "property", "properties", "address", "addresses", "apartment complex",
        "apartment complexes", "complex", "complexes", "building", "buildings", "site", "sites",
    },
    "unit": {"unit", "units", "apartment", "apartments", "suite", "suites"},
    "program": {"program", "programs", "service", "services"},
    "lease": {"lease", "leases", "rental agreement", "rental agreements", "tenancy", "tenancies"},
}


def browse_kind_from_query(query: str) -> str | None:
    """Return a category for a common workplace term, without matching an identity."""
    needle = normalized_entity_name(query)
    return next((kind for kind, terms in BROWSE_KIND_SYNONYMS.items() if needle in terms), None)


def review_category(reason: str) -> str:
    """Put human work into an actionable queue without relying on a model."""
    lowered = reason.casefold()
    if "duplicate" in lowered:
        return "duplicate_check"
    if "completed revision" in lowered or "corrected version" in lowered:
        return "revision_confirmation"
    if ("multiple" in lowered or "more than one" in lowered) and ("participant" in lowered or "identity" in lowered or "name" in lowered):
        return "identity_conflict"
    if "hmis" in lowered or "participant identity" in lowered or "participant name" in lowered:
        return "missing_identity"
    if "ocr" in lowered or "scan" in lowered:
        return "ocr_confirmation"
    if "unsupported" in lowered or "document type" in lowered:
        return "classification"
    if "date" in lowered or "reporting period" in lowered:
        return "missing_time_context"
    return "other_review"


@dataclass
class ExtractedDocument:
    document_type: str
    tenant: str | None = None
    participant: str | None = None
    landlord: str | None = None
    program: str | None = None
    property_address: str | None = None
    unit: str | None = None
    signed_date: str | None = None
    document_date: str | None = None
    enrollment_date: str | None = None
    exit_date: str | None = None
    reporting_period: str | None = None
    date_of_birth: str | None = None
    primary_care_provider: str | None = None
    mental_health_provider: str | None = None
    emergency_contact: str | None = None
    hmis_id: str | None = None
    referenced_lease_date: str | None = None
    monthly_rent: str | None = None
    security_deposit: str | None = None
    move_in_date: str | None = None
    lease_term: str | None = None
    legal_owner: str | None = None
    payee: str | None = None
    property_manager: str | None = None
    signer: str | None = None


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
    has_completed_identity = bool(
        value("tenant") or value("participant") or find_value("Premises", text)
        or find_value("Property address", text) or find_value("Payee name", text)
        or find_value("Legal owner", text) or has_nonblank_signature
    )
    move_in_type = None
    if "MOVE-IN ASSISTANCE REQUEST" in upper:
        move_in_type = "move_in_assistance_request"
    elif "LANDLORD RENTAL ASSISTANCE ACKNOWLEDGEMENT" in upper:
        move_in_type = "landlord_rental_assistance_acknowledgement"
    elif "UNIT INFORMATION AND OWNER CERTIFICATIONS" in upper:
        move_in_type = "unit_information_owner_certification"
    elif "REQUEST FOR TAXPAYER IDENTIFICATION NUMBER AND CERTIFICATION" in upper or "FORM W-9" in upper:
        move_in_type = "w9"
    elif "LETTER OF AUTHORIZATION" in upper and "AUTHORIZED TO SIGN" in upper:
        move_in_type = "letter_of_authorization"
    elif "LANDLORD INCENTIVE FEE AGREEMENT FORM" in upper:
        move_in_type = "landlord_incentive_fee_agreement"
    elif "HABITABILITY STANDARDS FOR PERMANENT HOUSING" in upper:
        move_in_type = "habitability_standards"
    elif "OWNERSHIP VERIFICATION" in upper and "ASSESSOR" in upper:
        move_in_type = "ownership_verification"

    if move_in_type and not has_completed_identity:
        document_type = "form_template"
    elif move_in_type:
        document_type = move_in_type
    elif "INCOME DECLARATION" in upper:
        document_type = "income_declaration"
    elif "CLIENT FINANCIAL ASSISTANCE CHECK REQUEST FORM" in upper or "FINANCIAL ASSISTANCE CHECK REQUEST" in upper:
        document_type = "financial_assistance_request"
    elif "HOUSEHOLD COMPOSITION & INCOME ELIGIBILITY" in upper or "MYORG CALCULATOR" in upper or "INCOME VERIFICATION" in upper:
        document_type = "income_verification"
    elif "RECERTIFICATION" in upper:
        document_type = "recertification"
    elif "CONTACT INFORMATION SHEET" in upper:
        document_type = "contact_information"
    elif "PROGRAM ENROLLMENT" in upper:
        document_type = "program_enrollment"
    elif any(marker in upper for marker in {"HMIS EXIT SUMMARY", "PROGRAM EXIT", "EXIT SUMMARY FORM", "PROGRAM GRADUATION"}):
        document_type = "program_exit"
    elif "CONSENT TO SHARE PROTECTED PERSONAL INFORMATION" in upper and not has_completed_identity:
        document_type = "form_template"
    elif "CONSENT TO SHARE PROTECTED PERSONAL INFORMATION" in upper:
        document_type = "consent_to_share"
    elif any(marker in upper for marker in {
        "RENT REASONABLENESS", "LANDLORD COMMUNICATION",
        "HOUSING RETENTION PLAN", "HOUSING SEARCH PLAN",
    }):
        document_type = "housing_record"
    elif "PET" in upper and "ADDENDUM" in upper:
        document_type = "lease_addendum"
    elif "LEASE" in upper:
        document_type = "lease"

    premises = find_value("Premises", text) or find_value("Property address", text)
    property_address = unit = None
    if premises:
        match = re.match(r"(.+?),\s*(?:Apartment|Unit)\s+(.+)$", premises, re.IGNORECASE)
        if match:
            property_address, unit = match.group(1).strip(), match.group(2).strip()
        else:
            property_address = premises
            unit = find_value("Unit", text)

    referenced = re.search(r"(?:executed|dated)\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", text)
    return ExtractedDocument(
        document_type=document_type,
        tenant=value("tenant") or value("participant"),
        participant=value("participant"),
        landlord=value("landlord"),
        program=value("program"),
        property_address=property_address,
        unit=unit,
        signed_date=find_value("Lease signed", text),
        document_date=value("document_date"),
        enrollment_date=value("enrollment_date"),
        exit_date=value("exit_date"),
        reporting_period=value("reporting_period"),
        date_of_birth=value("date_of_birth"),
        primary_care_provider=value("primary_care_provider"),
        mental_health_provider=value("mental_health_provider"),
        emergency_contact=value("emergency_contact"),
        hmis_id=value("hmis_id"),
        referenced_lease_date=referenced.group(1) if referenced else None,
        monthly_rent=find_value("Monthly rent", text) or find_value("Requested rent", text) or find_value("Tenant monthly rental amount", text),
        security_deposit=find_value("Security deposit", text),
        move_in_date=find_value("Move-in date", text) or find_value("Date available for move-in", text),
        lease_term=find_value("Lease term", text),
        legal_owner=find_value("Legal owner", text) or find_value("Name of legal owner", text),
        payee=find_value("Payee name", text) or find_value("Checks payable to", text),
        property_manager=find_value("Property manager", text) or find_value("Management company", text),
        signer=find_value("Signer", text) or find_value("Landlord/owner signature", text),
    )


class HomesteaderStore:
    """Small JSON-backed store. Events are appended; original source is preserved."""

    def __init__(self, path: Path, *, program_rules_path: Path | None = None, move_in_rules_path: Path | None = None, logical_layouts_path: Path | None = None):
        self.path = path
        self.program_rules_path = program_rules_path or path.parent / "program_rules.json"
        self.program_schedules = load_program_schedules(self.program_rules_path)
        self.move_in_rules_path = move_in_rules_path or path.parent / "move_in_packet.json"
        self.move_in_definition = load_move_in_definition(self.move_in_rules_path)
        self.logical_layouts_path = logical_layouts_path or path.parent / "logical_document_layouts.json"
        self.logical_layouts = load_logical_layouts(self.logical_layouts_path)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            data.setdefault("intake_occurrences", [])
            data.setdefault("intake_packets", [])
            data.setdefault("counters", {"temporary_file": 0})
            data.setdefault("ai_proposals", [])
            data.setdefault("intake_jobs", [])
            data.setdefault("entity_aliases", [])
            data.setdefault("move_in_workflows", [])
            for job in data["intake_jobs"]:
                if job.get("status") == "processing":
                    job["status"] = "waiting"
                    job["recovered_at"] = now()
            return data
        return {"documents": [], "intake_occurrences": [], "intake_packets": [], "entities": [], "relationships": [], "ledger_events": [], "review_queue": [], "ai_proposals": [], "intake_jobs": [], "entity_aliases": [], "move_in_workflows": [], "counters": {"temporary_file": 0}}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")

    def correction_findings(self) -> list[dict]:
        """Audit local record quality without altering records or calling a service."""
        return correction_findings(self)

    def export_document_parts(self, document_id: str, part_ids: list[str], destination: Path) -> list[Path]:
        """Prepare a selected local packet export without changing evidence."""
        document = next((item for item in self.data["documents"] if item["id"] == document_id), None)
        if not document:
            raise ValueError("The stored document could not be found.")
        outputs = export_logical_parts(document, part_ids, destination)
        self._event("logical_parts_exported", document_id, {
            "part_ids": part_ids,
            "destination": str(destination),
            "output_paths": [str(item) for item in outputs],
            "source": "explicit_local_export",
        })
        return outputs

    def initialize_program_rules(self) -> Path:
        """Write the local editable rules template once; never overwrite it."""
        if not self.program_rules_path.exists():
            write_default_program_schedules(self.program_rules_path)
        self.program_schedules = load_program_schedules(self.program_rules_path)
        return self.program_rules_path

    def initialize_move_in_rules(self) -> Path:
        """Create the editable move-in workflow rules template once."""
        if not self.move_in_rules_path.exists():
            write_default_move_in_definition(self.move_in_rules_path)
        self.move_in_definition = load_move_in_definition(self.move_in_rules_path)
        return self.move_in_rules_path

    def initialize_logical_layouts(self) -> Path:
        """Create the local, editable composite-packet definitions once."""
        write_default_logical_layouts(self.logical_layouts_path)
        self.logical_layouts = load_logical_layouts(self.logical_layouts_path)
        return self.logical_layouts_path

    def save_logical_layouts(self, layouts: list[dict]) -> Path:
        """Save an explicit local change to the packet-definition Form Bank."""
        saved = save_logical_layouts(self.logical_layouts_path, layouts)
        self.logical_layouts = load_logical_layouts(saved)
        self._event("logical_packet_definitions_updated", "logical_document_layouts", {
            "layout_ids": [layout["layout_id"] for layout in self.logical_layouts],
            "path": str(saved), "source": "explicit_local_form_bank_edit",
        })
        return saved

    def packet_completeness(self, packet_id: str, requirement: str | None = None) -> dict:
        """Compare a named intake packet to explicit Form Bank requirements.

        This evaluates only mapped logical records from sources attached to the
        packet. It never treats a filename, an upload order, or an empty page
        as proof that required evidence exists.
        """
        packet = next((item for item in self.data["intake_packets"] if item["id"] == packet_id), None)
        if not packet:
            raise ValueError("Intake packet does not exist.")
        label = (requirement or packet.get("label") or "").casefold()
        requirement_name = next((name for name in {tag for layout in self.logical_layouts for part in layout.get("parts", []) for tag in part.get("required_for", [])} if name.casefold() in label), None)
        if not requirement_name:
            return {"packet_id": packet_id, "status": "not_configured", "requirement": None, "present": [], "missing": []}
        documents = {document["id"]: document for document in self.data["documents"]}
        structures = [documents[doc_id].get("logical_document_structure") for doc_id in packet.get("document_ids", []) if doc_id in documents and documents[doc_id].get("logical_document_structure")]
        required_parts = [
            part for layout in self.logical_layouts for part in layout.get("parts", [])
            if requirement_name in part.get("required_for", [])
        ]
        present_ids = {part["id"] for structure in structures for part in structure.get("parts", [])}
        present = [part for part in required_parts if part["id"] in present_ids]
        missing = [part for part in required_parts if part["id"] not in present_ids]
        return {
            "packet_id": packet_id, "status": "complete" if not missing else "incomplete",
            "requirement": requirement_name, "present": present, "missing": missing,
            "mapped_source_count": len(structures),
        }

    def move_in_workflow_status(self, workflow_id: str | None = None) -> list[dict]:
        """Return local move-in readiness without making an external decision."""
        core = core_record_keys(self.move_in_definition)
        rows = []
        for workflow in self.data["move_in_workflows"]:
            if workflow_id and workflow["id"] != workflow_id:
                continue
            present = set(workflow.get("record_types", []))
            missing = sorted(core - present)
            claims_by_field: dict[str, list[dict]] = {}
            for claim in workflow.get("fact_claims", []):
                claims_by_field.setdefault(claim["field"], []).append(claim)
            conflicts = []
            for field, claims in claims_by_field.items():
                values = {claim["normalized_value"] for claim in claims if claim.get("normalized_value")}
                if len(values) > 1:
                    conflicts.append({
                        "field": field,
                        "values": sorted({claim["value"] for claim in claims}),
                        "document_ids": sorted({claim["document_id"] for claim in claims}),
                    })
            rows.append({
                **workflow,
                "present_record_types": sorted(present),
                "missing_record_types": missing,
                "conflicts": conflicts,
                "status": "needs_review" if conflicts else ("complete_for_local_review" if not missing else "in_progress"),
            })
        return rows

    def queue_intake_sources(self, packet_id: str, sources: list[Path]) -> list[dict]:
        """Persist local intake jobs without moving or transmitting any source."""
        packet = next((item for item in self.data["intake_packets"] if item["id"] == packet_id), None)
        if not packet or packet.get("status", "open") != "open":
            raise ValueError("Open a packet before queueing scans.")
        queued = []
        existing = {
            (item.get("packet_id"), item.get("source_path")) for item in self.data["intake_jobs"]
            if item.get("status") in {"waiting", "processing"}
        }
        for source in sources:
            key = (packet_id, str(source))
            if key in existing:
                continue
            job = {
                "id": str(uuid4()), "packet_id": packet_id, "source_path": str(source),
                "source_name": source.name, "status": "waiting", "queued_at": now(),
            }
            self.data["intake_jobs"].append(job)
            queued.append(job)
        return queued

    def claim_next_intake_job(self) -> dict | None:
        """Claim one waiting job so only one local worker processes it."""
        job = next((item for item in self.data["intake_jobs"] if item.get("status") == "waiting"), None)
        if not job:
            return None
        job["status"] = "processing"
        job["started_at"] = now()
        return job

    def finish_intake_job(self, job_id: str, *, result: dict | None = None, error: str | None = None) -> dict:
        job = next((item for item in self.data["intake_jobs"] if item["id"] == job_id), None)
        if not job:
            raise ValueError("Intake job does not exist.")
        job["status"] = "failed" if error else "completed"
        job["finished_at"] = now()
        if result is not None:
            job["result"] = result
        if error:
            job["error"] = error
        return job

    def intake_job_counts(self) -> dict[str, int]:
        counts = {"waiting": 0, "processing": 0, "completed": 0, "failed": 0}
        for job in self.data["intake_jobs"]:
            status = job.get("status")
            if status in counts:
                counts[status] += 1
        return counts

    def add_entity_alias(self, entity_id: str, alias: str, *, source: str = "human_confirmed", note: str | None = None) -> dict:
        """Record a confirmed alternate name without merging entities.

        An alias is only a second way to find one canonical entity. It does not
        assert that a similarly named property, LLC, manager, or contact is the
        same entity. Those connections remain explicit relationships.
        """
        entity = next((item for item in self.data["entities"] if item["id"] == entity_id), None)
        if not entity:
            raise ValueError("Entity does not exist.")
        cleaned = alias.strip()
        if not cleaned:
            raise ValueError("An alias cannot be blank.")
        normalized = normalized_entity_name(cleaned)
        conflicts = [
            item for item in self.data["entity_aliases"]
            if item["entity_id"] != entity_id and item["entity_kind"] == entity["kind"] and item["normalized"] == normalized
        ]
        if conflicts:
            raise ValueError("That alias is already confirmed for another entity of the same type; review the relationship instead of merging them.")
        existing = next((item for item in self.data["entity_aliases"] if item["entity_id"] == entity_id and item["normalized"] == normalized), None)
        if existing:
            return existing
        record = {
            "id": str(uuid4()), "entity_id": entity_id, "entity_kind": entity["kind"],
            "alias": cleaned, "normalized": normalized, "source": source, "note": note, "created_at": now(),
        }
        self.data["entity_aliases"].append(record)
        self._event("entity_alias_confirmed", entity_id, {"alias_id": record["id"], "alias": cleaned, "source": source, "note": note})
        return record

    def entity_directory_search(self, query: str) -> list[dict]:
        """Search canonical names and human-confirmed aliases, never fuzzy merges."""
        needle = normalized_entity_name(query)
        if not needle:
            return []
        aliases_by_entity: dict[str, list[str]] = {}
        for alias in self.data["entity_aliases"]:
            aliases_by_entity.setdefault(alias["entity_id"], []).append(alias["alias"])
        results = []
        for entity in self.data["entities"]:
            names = [entity["name"], *aliases_by_entity.get(entity["id"], [])]
            matched = [name for name in names if needle in normalized_entity_name(name)]
            if matched:
                results.append({
                    "entity_id": entity["id"], "name": entity["name"], "kind": entity["kind"],
                    "matched_names": matched, "aliases": aliases_by_entity.get(entity["id"], []),
                })
        return sorted(results, key=lambda item: (item["kind"], item["name"].casefold()))

    BROWSABLE_KINDS = ("person", "landlord", "property", "unit", "program", "lease")

    def entity_directory(self, kind: str | None = None) -> list[dict]:
        """Browse everything the local database has recorded of one kind.

        This answers "which landlords / properties / participants are in here"
        without requiring the user to remember any name. It lists canonical
        entities only; similar names remain separate entries.
        """
        kinds = (kind,) if kind else self.BROWSABLE_KINDS
        aliases_by_entity: dict[str, list[str]] = {}
        for alias in self.data["entity_aliases"]:
            aliases_by_entity.setdefault(alias["entity_id"], []).append(alias["alias"])
        degree: dict[str, int] = {}
        for relationship in self.data["relationships"]:
            for entity_id in (relationship.get("from_entity_id"), relationship.get("to_entity_id")):
                if entity_id:
                    degree[entity_id] = degree.get(entity_id, 0) + 1
        rows = []
        for entity in self.data["entities"]:
            if entity["kind"] not in kinds:
                continue
            attributes = entity.get("attributes") or {}
            rows.append({
                "entity_id": entity["id"], "name": entity["name"], "kind": entity["kind"],
                "aliases": aliases_by_entity.get(entity["id"], []),
                "identifier": attributes.get("hmis_id") or attributes.get("temporary_id"),
                "relationship_count": degree.get(entity["id"], 0),
            })
        return sorted(rows, key=lambda item: (item["kind"], item["name"].casefold()))

    def entity_network(self, entity_id: str) -> dict:
        """Return one entity with its recorded connections and naming documents.

        This is the reverse lookup for non-participant entities: a landlord
        shows the tenants and properties recorded with it, and a property
        shows everyone recorded at that address. Only explicit, recorded
        relationships are followed; a similar name never adds a connection.
        """
        entities = {entity["id"]: entity for entity in self.data["entities"]}
        entity = entities.get(entity_id)
        if not entity:
            raise ValueError("Entity does not exist.")
        adjacent: dict[str, list[tuple[str, str]]] = {}
        for relationship in self.data["relationships"]:
            from_id, to_id = relationship.get("from_entity_id"), relationship.get("to_entity_id")
            if from_id and to_id:
                adjacent.setdefault(from_id, []).append((to_id, relationship["type"]))
                adjacent.setdefault(to_id, []).append((from_id, relationship["type"]))
        nearby: dict[str, dict] = {}
        frontier = [(entity_id, 0, [])]
        visited = {entity_id}
        while frontier:
            current, distance, path = frontier.pop(0)
            if distance >= 4:
                continue
            for neighbor_id, relation in adjacent.get(current, []):
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                neighbor = entities.get(neighbor_id)
                next_path = [*path, relation]
                if neighbor and neighbor["kind"] not in {"participant_ledger", "income_ledger", "case_ledger"}:
                    attributes = neighbor.get("attributes") or {}
                    nearby[neighbor_id] = {
                        "entity_id": neighbor_id, "name": neighbor["name"], "kind": neighbor["kind"],
                        "distance": distance + 1, "path": next_path,
                        "identifier": attributes.get("hmis_id") or attributes.get("temporary_id"),
                    }
                frontier.append((neighbor_id, distance + 1, next_path))
        connected: dict[str, list[dict]] = {}
        for item in sorted(nearby.values(), key=lambda entry: (entry["distance"], entry["name"].casefold())):
            connected.setdefault(item["kind"], []).append(item)
        searchable_names = {normalized_entity_name(entity["name"])}
        alias_names = []
        for alias in self.data["entity_aliases"]:
            if alias["entity_id"] == entity_id:
                searchable_names.add(alias["normalized"])
                alias_names.append(alias["alias"])
        documents = []
        for document in self.data["documents"]:
            extracted = document.get("extracted") or {}
            stated = [extracted.get("landlord"), extracted.get("property_address"), extracted.get("participant"), extracted.get("tenant")]
            if any(value and normalized_entity_name(value) in searchable_names for value in stated):
                documents.append({
                    "document_id": document["id"], "name": document["original_name"],
                    "type": extracted.get("document_type", "unknown"),
                    "document_date": extracted.get("document_date"),
                })
        return {
            "entity_id": entity_id, "name": entity["name"], "kind": entity["kind"],
            "attributes": entity.get("attributes") or {},
            "aliases": sorted(alias_names, key=str.casefold),
            "connected": connected,
            "documents": sorted(documents, key=lambda item: item["name"].casefold()),
        }

    def universal_search(self, query: str) -> dict:
        """Search local entities, connected files, and stored document names together.

        This is an index entry point, not fuzzy identity resolution. Names and
        confirmed aliases make something findable; relationships remain explicit
        and a similar name never merges records.
        """
        needle = normalized_entity_name(query)
        empty = {"entities": [], "related_entities": [], "participant_files": [], "documents": []}
        if not needle:
            return empty
        entities = {entity["id"]: entity for entity in self.data["entities"]}
        starting = {item["entity_id"] for item in self.entity_directory_search(query)}
        direct_participant_files = self.search_files(query)
        starting.update(item["person_id"] for item in direct_participant_files)
        adjacency: dict[str, set[str]] = {}
        for relationship in self.data["relationships"]:
            from_id, to_id = relationship.get("from_entity_id"), relationship.get("to_entity_id")
            if from_id in entities and to_id in entities:
                adjacency.setdefault(from_id, set()).add(to_id)
                adjacency.setdefault(to_id, set()).add(from_id)
        distances = {entity_id: 0 for entity_id in starting if entity_id in entities}
        frontier = list(distances)
        while frontier:
            current = frontier.pop(0)
            if distances[current] >= 3:
                continue
            for neighbor in adjacency.get(current, set()):
                if neighbor not in distances:
                    distances[neighbor] = distances[current] + 1
                    frontier.append(neighbor)
        directory = self.entity_directory_search(query)
        related = [
            {"entity_id": entity_id, "name": entities[entity_id]["name"], "kind": entities[entity_id]["kind"], "distance": distance}
            for entity_id, distance in distances.items()
            if distance and entity_id in entities
        ]
        document_matches = []
        for document in self.data["documents"]:
            searchable = " ".join([
                document.get("original_name", ""),
                document.get("extracted", {}).get("participant") or "",
                document.get("extracted", {}).get("tenant") or "",
                document.get("extracted", {}).get("property_address") or "",
                document.get("extracted", {}).get("landlord") or "",
            ])
            if needle in normalized_entity_name(searchable):
                document_matches.append({"document_id": document["id"], "name": document["original_name"], "type": document.get("extracted", {}).get("document_type", "unknown")})
        participant_ids = {item["person_id"] for item in direct_participant_files}
        participant_ids.update(entity_id for entity_id in distances if entities.get(entity_id, {}).get("kind") == "person")
        participant_files = []
        for person_id in participant_ids:
            person = entities.get(person_id)
            if not person:
                continue
            summary = self.participant_file(person_id)
            attributes = person.get("attributes", {})
            participant_files.append({
                "person_id": person_id, "name": person["name"], "hmis_id": attributes.get("hmis_id"),
                "temporary_id": attributes.get("temporary_id"),
                "status": "confirmed" if attributes.get("hmis_id") else "temporary",
                "document_count": len(summary["documents"]),
            })
        return {
            "entities": directory,
            "related_entities": sorted(related, key=lambda item: (item["distance"], item["kind"], item["name"].casefold())),
            "participant_files": sorted(participant_files, key=lambda item: item["name"].casefold()),
            "documents": sorted(document_matches, key=lambda item: item["name"].casefold()),
        }

    def housing_schedule_status(self, *, as_of: date | None = None, through: date | None = None) -> list[dict]:
        """Derive standard program obligations without changing any file.

        Only a recorded enrollment starts a schedule.  Extensions, transfers,
        and pauses are intentionally not inferred; those will become explicit
        ledger events before they alter the standard timeline.
        """
        today = as_of or date.today()
        horizon = through or today
        documents = {document["id"]: document for document in self.data["documents"]}
        people = {entity["id"]: entity for entity in self.data["entities"] if entity["kind"] == "person"}
        statuses = []
        baseline_events = [event for event in self.data["ledger_events"] if event["type"] == "program_baseline_established"]
        for enrollment in baseline_events:
            details = enrollment.get("details", {})
            enrollment_date = details.get("enrollment_date")
            baseline_date = details.get("baseline_date")
            person = people.get(details.get("participant_id"))
            program = next((entity for entity in self.data["entities"] if entity["id"] == details.get("program_id")), None)
            if not person or not program or not enrollment_date:
                continue
            try:
                start = date.fromisoformat(enrollment_date)
                baseline = date.fromisoformat(baseline_date)
            except ValueError:
                continue
            source_document = documents.get(details.get("document_id"))
            packet_id = (source_document or {}).get("intake_packet_id")
            packet = next((item for item in self.data["intake_packets"] if item["id"] == packet_id), None) if packet_id else None
            if packet and packet.get("status", "open") == "open":
                continue
            schedule = schedule_for_program(program["name"], self.program_schedules)
            if not schedule:
                continue
            exit_events = [
                event for event in self.data["ledger_events"]
                if event["type"] == "program_exit_recorded" and event.get("details", {}).get("participant_id") == person["id"]
                and event.get("details", {}).get("program_id") == program["id"]
            ]
            exit_date = None
            if exit_events:
                try:
                    exit_date = min(date.fromisoformat(event.get("details", {}).get("exit_date", "")) for event in exit_events)
                except ValueError:
                    exit_date = None
            end = add_months(start, schedule.duration_months)
            participant_events = [
                event for event in self.data["ledger_events"]
                if event.get("details", {}).get("participant_id") == person["id"]
            ]
            for requirement in schedule.scheduled_requirements:
                for occurrence in scheduled_occurrences(requirement, start, end, horizon):
                    period_start, period_end, due = occurrence["period_start"], occurrence["period_end"], occurrence["due_date"]
                    # Homesteader begins with whatever real-world checkpoint
                    # it first receives. Historical requirements before that
                    # baseline are not silently converted into accusations.
                    if period_start < baseline or (exit_date and period_start >= exit_date):
                        continue
                    evidence = []
                    for event in participant_events:
                        if event["type"] not in requirement.event_types:
                            continue
                        document = documents.get(event.get("details", {}).get("document_id"))
                        value = event.get("details", {}).get("document_date") or (document or {}).get("extracted", {}).get("document_date")
                        try:
                            document_day = date.fromisoformat(value) if value else None
                        except ValueError:
                            document_day = None
                        if document_day and period_start <= document_day < period_end:
                            evidence.append(event)
                    if evidence:
                        status = "documented"
                    elif due and today < due:
                        status = "upcoming"
                    elif due is None and today < period_end:
                        status = "due"
                    else:
                        status = "missing"
                    statuses.append({
                        "person_id": person["id"], "ptc": person["name"],
                        "participant_identifier": person.get("attributes", {}).get("hmis_id") or person.get("attributes", {}).get("temporary_id") or "",
                        "program": program["name"], "schedule": schedule.key,
                        "enrollment_date": start.isoformat(), "baseline_date": baseline.isoformat(), "standard_end_date": end.isoformat(),
                        "exit_date": exit_date.isoformat() if exit_date else None,
                        "requirement_key": requirement.key, "requirement": requirement.label,
                        "due_date": due.isoformat() if due else period_start.isoformat(),
                        "due_precision": "day" if due else "month",
                        "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
                        "status": status,
                        "evidence_document_ids": [event["details"]["document_id"] for event in evidence],
                    })
        return sorted(statuses, key=lambda item: (item["ptc"], item["due_date"], item["requirement_key"]))

    def submit_ai_proposal(self, payload: dict) -> dict:
        """Store an optional host-AI proposal after local evidence validation.

        This does not apply facts, create relationships, or make network calls.
        Valid proposals become a local review artifact; invalid proposals remain
        rejected with their exact validation failures.
        """
        proposal = AIProposal.from_dict(payload)
        document = next((item for item in self.data["documents"] if item["id"] == proposal.document_id), None)
        if not document:
            raise ValueError("AI proposal references a document that does not exist locally.")
        errors = validate_proposal(
            proposal, document.get("source_text", ""), source_format=document.get("source_format", "txt"),
        )
        record = {
            "id": str(uuid4()), "proposal": proposal.as_dict(), "status": "needs_review" if not errors else "rejected",
            "validation_errors": list(errors), "submitted_at": now(),
        }
        self.data["ai_proposals"].append(record)
        self._event("ai_proposal_received", document["id"], {
            "proposal_id": record["id"], "document_id": document["id"], "provider_id": proposal.provider_id,
            "status": record["status"], "source": "local_proposal_import",
        })
        return record

    def _archive_source(self, source: Path, content_hash: str, source_bytes: bytes) -> str:
        """Preserve an accepted source locally without moving its intake copy.

        The hash is part of the archive name, so the same raw source is stored
        once even if it is encountered again from an inbox or packet. The path
        stored in state is relative to the state directory, keeping an archive
        portable with its JSON state and avoiding a hard-coded user path.
        """
        archive_dir = self.path.parent / "sources"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived = archive_dir / f"{content_hash}{source.suffix.casefold()}"
        if not archived.exists():
            archived.write_bytes(source_bytes)
        return str(archived.relative_to(self.path.parent))

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
        if not needle:
            return []
        results = []
        for entity in self.data["entities"]:
            if entity["kind"] != "person":
                continue
            searchable = " ".join([
                entity["name"],
                str(entity.get("attributes", {}).get("hmis_id") or ""),
                str(entity.get("attributes", {}).get("temporary_id") or ""),
            ]).casefold()
            if needle not in searchable:
                continue
            summary = self.participant_file(entity["id"])
            results.append({
                "person_id": entity["id"],
                "name": entity["name"],
                "hmis_id": entity.get("attributes", {}).get("hmis_id"),
                "temporary_id": entity.get("attributes", {}).get("temporary_id"),
                "status": "confirmed" if entity.get("attributes", {}).get("hmis_id") else "temporary",
                "document_count": len(summary["documents"]),
            })
        return results

    def participant_file(self, person_id: str) -> dict:
        """Return a small, evidence-first view of one participant file.

        This is intentionally derived from recorded events rather than a
        separate mutable list of "file documents." A human can inspect what
        supports a proposed association before assigning a new document.
        """
        person = next((entity for entity in self.data["entities"] if entity["id"] == person_id and entity["kind"] == "person"), None)
        if not person:
            raise ValueError("Participant file does not exist.")
        document_ids = []
        relevant_events = []
        for event in self.data["ledger_events"]:
            details = event.get("details", {})
            if details.get("participant_id") != person_id and details.get("person_id") != person_id:
                continue
            relevant_events.append(event)
            document_id = details.get("document_id")
            if document_id and document_id not in document_ids:
                document_ids.append(document_id)

        documents_by_id = {document["id"]: document for document in self.data["documents"]}
        documents = [
            {
                "id": document["id"],
                "original_name": document["original_name"],
                "document_type": document.get("extracted", {}).get("document_type", "unknown"),
                "document_date": document.get("extracted", {}).get("document_date"),
                "reporting_period": document.get("extracted", {}).get("reporting_period"),
            }
            for document_id in document_ids
            if (document := documents_by_id.get(document_id))
        ]

        entities = {entity["id"]: entity for entity in self.data["entities"]}
        adjacent: dict[str, list[tuple[str, str]]] = {}
        for relationship in self.data["relationships"]:
            from_id = relationship.get("from_entity_id")
            to_id = relationship.get("to_entity_id")
            if from_id and to_id:
                adjacent.setdefault(from_id, []).append((to_id, relationship["type"]))
                adjacent.setdefault(to_id, []).append((from_id, relationship["type"]))
        nearby = {}
        frontier = [(person_id, 0, [])]
        visited = {person_id}
        while frontier:
            entity_id, distance, path = frontier.pop(0)
            if distance >= 4:
                continue
            for neighbor_id, relationship_type in adjacent.get(entity_id, []):
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                neighbor = entities.get(neighbor_id)
                next_path = [*path, relationship_type]
                if neighbor and neighbor["kind"] not in {"person", "participant_ledger"}:
                    nearby[neighbor_id] = {
                        "id": neighbor_id,
                        "name": neighbor["name"],
                        "kind": neighbor["kind"],
                        "distance": distance + 1,
                        "path": next_path,
                    }
                frontier.append((neighbor_id, distance + 1, next_path))
        return {
            "person_id": person["id"],
            "name": person["name"],
            "attributes": person.get("attributes", {}),
            "status": "confirmed" if person.get("attributes", {}).get("hmis_id") else "temporary",
            "documents": documents,
            "event_count": len(relevant_events),
            "events": sorted(relevant_events, key=lambda event: event.get("recorded_at", ""), reverse=True),
            "related_entities": sorted(nearby.values(), key=lambda item: (item["distance"], item["kind"], item["name"].casefold())),
        }

    def participant_documents_grouped_by_date(self, person_id: str) -> list[dict]:
        """Return documents associated with a participant, sectioned chronologically by upload date."""
        summary = self.participant_file(person_id)
        doc_ids = [doc["id"] for doc in summary.get("documents", [])]
        documents_by_id = {doc["id"]: doc for doc in self.data.get("documents", [])}

        superseded_doc_ids = set()
        for rel in self.data.get("relationships", []):
            if rel.get("type") == "supersedes_for_fields" and rel.get("to_document_id"):
                superseded_doc_ids.add(rel["to_document_id"])

        pending_review_doc_ids = {
            item.get("document_id") for item in self.data.get("review_queue", [])
            if item.get("status") == "needs_review" and item.get("document_id")
        }

        duplicate_doc_ids = set()
        for event in self.data.get("ledger_events", []):
            if event.get("type") == "duplicate_detected":
                doc_id = event.get("details", {}).get("document_id")
                if doc_id:
                    duplicate_doc_ids.add(doc_id)

        grouped: dict[str, list[dict]] = {}
        for doc_id in doc_ids:
            doc = documents_by_id.get(doc_id)
            if not doc:
                continue
            ingested_raw = doc.get("ingested_at") or doc.get("created_at") or now()
            upload_date_str = ingested_raw[:10]

            if (doc.get("staging_disposition") or {}).get("kind") == "non_viable":
                status_code = "non_viable"
                status_label = "Non-viable source"
                status_color = "grey"
            elif doc_id in pending_review_doc_ids:
                status_code = "needs_review"
                status_label = "Needs Review"
                status_color = "warning"
            elif doc_id in duplicate_doc_ids:
                status_code = "true_duplicate"
                status_label = "True Duplicate"
                status_color = "grey"
            elif doc_id in superseded_doc_ids:
                status_code = "superseded_revision"
                status_label = "Superseded Revision"
                status_color = "amber"
            else:
                status_code = "active_export"
                status_label = "Active Export Source"
                status_color = "positive"

            doc_entry = {
                "id": doc["id"],
                "original_name": doc.get("original_name", "Untitled Document"),
                "document_type": doc.get("extracted", {}).get("document_type") or "Document",
                "document_date": doc.get("extracted", {}).get("document_date"),
                "reporting_period": doc.get("extracted", {}).get("reporting_period"),
                "ingested_at": ingested_raw,
                "upload_date": upload_date_str,
                "status_code": status_code,
                "status_label": status_label,
                "status_color": status_color,
                "source_path": doc.get("source_path"),
                "sha256": doc.get("sha256"),
            }
            grouped.setdefault(upload_date_str, []).append(doc_entry)

        sorted_groups = []
        today_str = date.today().isoformat()
        for upload_date in sorted(grouped.keys(), reverse=True):
            docs = grouped[upload_date]
            try:
                dt = date.fromisoformat(upload_date)
                formatted_date = dt.strftime("%B %d, %Y")
            except ValueError:
                formatted_date = upload_date

            if upload_date == today_str:
                date_label = f"Uploaded Today — {formatted_date}"
            else:
                date_label = f"Uploaded {formatted_date}"

            sorted_groups.append({
                "upload_date": upload_date,
                "date_label": date_label,
                "documents": docs,
            })

        return sorted_groups

    def participant_index(
        self,
        *,
        query: str = "",
        status: str = "all",
        program: str | None = None,
        has_lease: bool = False,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """Return a compact participant-file index, not a dashboard model."""
        needle = query.casefold().strip()
        entities = {entity["id"]: entity for entity in self.data["entities"]}
        rows = []
        for person in (entity for entity in self.data["entities"] if entity["kind"] == "person"):
            attributes = person.get("attributes", {})
            identifier = attributes.get("hmis_id") or attributes.get("temporary_id") or ""
            if needle and needle not in f"{person['name']} {identifier}".casefold():
                continue
            person_status = "confirmed" if attributes.get("hmis_id") else "temporary"
            if status != "all" and person_status != status:
                continue
            summary = self.participant_file(person["id"])
            programs = sorted({
                entities[relationship["to_entity_id"]]["name"]
                for relationship in self.data["relationships"]
                if relationship.get("type") == "enrolled_in" and relationship.get("from_entity_id") == person["id"]
                and relationship.get("to_entity_id") in entities
            })
            if program and program not in programs:
                continue
            lease_count = sum(1 for relationship in self.data["relationships"] if relationship.get("type") == "tenant_under" and relationship.get("from_entity_id") == person["id"])
            if has_lease and not lease_count:
                continue
            document_dates = [document.get("document_date") for document in summary["documents"] if document.get("document_date")]
            if date_from and not any(date >= date_from for date in document_dates):
                continue
            if date_to and not any(date <= date_to for date in document_dates):
                continue
            rows.append({
                "person_id": person["id"], "name": person["name"], "identifier": identifier,
                "status": person_status, "document_count": len(summary["documents"]),
                "programs": programs, "lease_count": lease_count,
            })
        return sorted(rows, key=lambda item: item["name"].casefold())

    def relationship_search(self, query: str) -> list[dict]:
        """Find participant files through a named relationship, not just a name.

        A landlord or property search can therefore discover participant files
        linked through property -> unit -> lease -> participant relationships.
        This remains graph traversal over recorded links, not an AI guess.
        """
        needle = query.casefold().strip()
        if not needle:
            return []
        entities = {entity["id"]: entity for entity in self.data["entities"]}
        starting_ids = [item["entity_id"] for item in self.entity_directory_search(query)]
        adjacent: dict[str, set[str]] = {}
        for relationship in self.data["relationships"]:
            from_id = relationship.get("from_entity_id")
            to_id = relationship.get("to_entity_id")
            if not from_id or not to_id:
                continue
            adjacent.setdefault(from_id, set()).add(to_id)
            adjacent.setdefault(to_id, set()).add(from_id)
        found: dict[str, dict] = {}
        for starting_id in starting_ids:
            frontier = [(starting_id, 0)]
            visited = {starting_id}
            while frontier:
                entity_id, distance = frontier.pop(0)
                entity = entities.get(entity_id)
                if entity and entity["kind"] == "person" and entity_id != starting_id:
                    found[entity_id] = {
                        "person_id": entity_id,
                        "name": entity["name"],
                        "hmis_id": entity.get("attributes", {}).get("hmis_id"),
                        "temporary_id": entity.get("attributes", {}).get("temporary_id"),
                        "relationship_distance": distance,
                    }
                if distance >= 4:
                    continue
                for neighbor in adjacent.get(entity_id, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        frontier.append((neighbor, distance + 1))
        return sorted(found.values(), key=lambda item: (item["relationship_distance"], item["name"].casefold()))

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

    def _completed_revision_candidate(self, document: dict, extracted: ExtractedDocument) -> tuple[dict, list[str]] | None:
        """Find a safe candidate for an intentionally re-uploaded completed copy.

        A revision requires a shared HMIS number, form type, and stated period
        or document date.  This deliberately excludes loose name matching and
        recurring quarterly forms from automatic revision proposals.
        """
        if not extracted.hmis_id or not (extracted.reporting_period or extracted.document_date):
            return None
        fields = ("participant", "hmis_id", "program", "document_date", "reporting_period", "enrollment_date", "date_of_birth", "primary_care_provider", "mental_health_provider", "emergency_contact")
        for prior in reversed(self.data["documents"][:-1]):
            prior_facts = prior.get("extracted", {})
            same_identity = prior_facts.get("hmis_id") == extracted.hmis_id
            same_instance = (
                prior_facts.get("document_type") == extracted.document_type
                and (prior_facts.get("reporting_period") == extracted.reporting_period or prior_facts.get("document_date") == extracted.document_date)
            )
            if not (same_identity and same_instance):
                continue
            improvements = [field for field in fields if not prior_facts.get(field) and getattr(extracted, field, None)]
            conflicts = [field for field in fields if prior_facts.get(field) and getattr(extracted, field, None) and prior_facts[field] != getattr(extracted, field)]
            if improvements and not conflicts:
                return prior, improvements
        return None

    def ingest(self, source: Path, *, packet_id: str | None = None, original_name: str | None = None) -> dict:
        text, extraction_issue, extraction_method = self._extract_source_text(source)
        extracted = extract_document(text)
        source_bytes = source.read_bytes()
        content_hash = sha256(source_bytes).hexdigest()
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
            "id": str(uuid4()), "original_name": original_name or source.name, "sha256": content_hash,
            "normalized_sha256": normalized_hash,
            "source_text": text, "source_format": source.suffix.casefold().lstrip(".") or "unknown",
            "source_size_bytes": len(source_bytes), "intake_packet_id": packet_id,
            "stored_source_path": self._archive_source(source, content_hash, source_bytes),
            "extracted": asdict(extracted), "ingested_at": now(),
        }
        if source.suffix.casefold() == ".pdf":
            try:
                structure = logical_document_parts(text, len(PdfReader(source).pages), self.logical_layouts)
            except Exception:
                structure = None
            if structure:
                document["logical_document_structure"] = structure
        self.data["documents"].append(document)

        document["text_extraction"] = {"method": extraction_method, "issue": extraction_issue}
        if extraction_issue:
            return self._review(document, extraction_issue)


        revision = self._completed_revision_candidate(document, extracted)
        if revision:
            prior, fields = revision
            self._event("completed_revision_proposed", prior["id"], {
                "candidate_document_id": document["id"], "filled_fields": fields, "source": "deterministic_document_comparison",
            })
            return self._review(
                document,
                f"Possible completed revision of '{prior['original_name']}'. It matches the HMIS number, form type, and reporting period/date, and fills: {', '.join(fields)}.",
                revision_of_document_id=prior["id"], revision_fields=fields,
            )

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
        if extracted.document_type in {"income_declaration", "income_verification"}:
            return self._record_income_declaration(document, extracted)
        if extracted.document_type == "contact_information":
            return self._record_contact_information(document, extracted)
        if extracted.document_type == "housing_record" or extracted.document_type in record_keys(self.move_in_definition):
            return self._record_housing_document(document, extracted)
        if extracted.document_type in {"program_enrollment", "consent_to_share", "program_exit", "financial_assistance_request", "recertification"}:
            return self._record_case_document(document, extracted)
        if extracted.document_type == "form_template":
            return self._catalog_form(document)
        return self._review(document, "Document type is not supported by the v0 prototype.")

    def _extract_source_text(self, source: Path) -> tuple[str, str | None, str]:
        if source.suffix.casefold() == ".txt":
            return source.read_text(), None, "plain_text"
        if source.suffix.casefold() != ".pdf":
            if source.suffix.casefold() in IMAGE_INTAKE_SUFFIXES:
                text, issue = recognize_image_with_vision(source)
                return text, issue, "macos_vision_ocr"
            return "", f"Unsupported file type '{source.suffix or 'unknown'}'.", "unsupported"
        try:
            text = "\n".join(page.extract_text() or "" for page in PdfReader(source).pages).strip()
        except Exception as error:
            return "", f"PDF text could not be read locally: {error}", "embedded_pdf_text"
        if text:
            return text, None, "embedded_pdf_text"
        text, issue = recognize_pdf_with_vision(source)
        return text, issue, "macos_vision_ocr"

    def ingest_inbox(self, path: Path, *, packet_id: str | None = None) -> dict:
        """Process only source files not already preserved by their raw hash."""
        processed, skipped = [], []
        if not path.exists():
            return {"processed": processed, "skipped": skipped}
        known_hashes = {document["sha256"] for document in self.data["documents"]}
        for source in sorted(item for item in path.iterdir() if item.is_file() and not item.name.startswith(".")):
            if source.suffix.casefold() not in SUPPORTED_INTAKE_SUFFIXES:
                skipped.append({"path": str(source), "reason": "Unsupported file type."})
                continue
            source_hash = sha256(source.read_bytes()).hexdigest()
            if source_hash in known_hashes:
                skipped.append({"path": str(source), "reason": "Already processed source file."})
                continue
            if packet_id:
                result = self.add_to_intake_packet(packet_id, [source])
                processed.append({"path": str(source), "result": result["results"][0]["result"]})
            else:
                processed.append({"path": str(source), "result": self.ingest(source)})
            known_hashes.add(source_hash)
        return {"processed": processed, "skipped": skipped}

    def start_intake_packet(self, label: str | None = None) -> dict:
        """Open a packet that can receive scans over time in any order."""
        packet = {
            "id": str(uuid4()),
            "label": label or f"Packet received {now()}",
            "created_at": now(),
            "status": "open",
            "document_ids": [],
            "intake_occurrence_ids": [],
            "source_names": [],
        }
        self.data["intake_packets"].append(packet)
        return packet

    def open_intake_packets(self) -> list[dict]:
        return [packet for packet in self.data["intake_packets"] if packet.get("status", "open") == "open"]

    def add_to_intake_packet(self, packet_id: str, sources: list[Path]) -> dict:
        """Add newly scanned sources to an open packet and refresh its proposal."""
        packet = next((item for item in self.data["intake_packets"] if item["id"] == packet_id), None)
        if not packet:
            raise ValueError(f"Intake packet '{packet_id}' does not exist.")
        if packet.get("status", "open") != "open":
            raise ValueError("This intake packet is closed. Start a new packet or resume an open one.")
        results = []
        for source in sources:
            before_occurrences = len(self.data["intake_occurrences"])
            result = self.ingest(source, packet_id=packet["id"])
            results.append({"path": str(source), "result": result})
            occurrence = self.data["intake_occurrences"][before_occurrences]
            packet["intake_occurrence_ids"].append(occurrence["id"])
            packet["source_names"].append(source.name)
            document = next((item for item in self.data["documents"] if item["id"] == result.get("document_id")), None)
            if document and document.get("intake_packet_id") == packet["id"]:
                packet["document_ids"].append(result["document_id"])
        self._refresh_packet_anchor(packet)
        return {
            "packet_id": packet["id"],
            "results": results,
            "proposed_person_id": packet.get("proposed_person_id"),
            "anchor_conflict": packet.get("anchor_conflict"),
        }

    def attach_document_to_intake_packet(self, packet_id: str, document_id: str) -> dict:
        """Bring a previously detached document into an open packet for review."""
        packet = next((item for item in self.data["intake_packets"] if item["id"] == packet_id), None)
        document = next((item for item in self.data["documents"] if item["id"] == document_id), None)
        if not packet or not document:
            raise ValueError("Both the intake packet and document must exist.")
        if packet.get("status", "open") != "open":
            raise ValueError("This intake packet is closed.")
        if document.get("intake_packet_id") and document["intake_packet_id"] != packet_id:
            raise ValueError("This document already belongs to another intake packet.")
        document["intake_packet_id"] = packet_id
        if document_id not in packet["document_ids"]:
            packet["document_ids"].append(document_id)
        self._refresh_packet_anchor(packet)
        return {"packet_id": packet_id, "document_id": document_id, "proposed_person_id": packet.get("proposed_person_id")}

    def close_intake_packet(self, packet_id: str) -> dict:
        packet = next((item for item in self.data["intake_packets"] if item["id"] == packet_id), None)
        if not packet:
            raise ValueError(f"Intake packet '{packet_id}' does not exist.")
        self._refresh_packet_anchor(packet)
        packet["status"] = "closed"
        packet["closed_at"] = now()
        return packet

    def ingest_packet(self, sources: list[Path], *, label: str | None = None) -> dict:
        """Convenience wrapper for a packet that is complete in one sitting."""
        packet = self.start_intake_packet(label)
        result = self.add_to_intake_packet(packet["id"], sources)
        self.close_intake_packet(packet["id"])
        return result

    def _refresh_packet_anchor(self, packet: dict) -> None:
        anchor_people = self._packet_anchor_people(packet["document_ids"])
        packet.pop("proposed_person_id", None)
        packet.pop("anchor_conflict", None)
        if len(anchor_people) == 1:
            anchor = anchor_people[0]
            packet["proposed_person_id"] = anchor["id"]
            self._offer_packet_anchor_to_reviews(packet, anchor)
        elif len(anchor_people) > 1:
            packet["anchor_conflict"] = "Multiple client identities were established in this packet; no association was proposed."

    def _packet_anchor_people(self, document_ids: list[str]) -> list[dict]:
        person_ids = {
            event["details"].get("person_id") or event["details"].get("participant_id")
            for event in self.data["ledger_events"]
            if event.get("details", {}).get("document_id") in document_ids
        }
        return [
            entity for entity in self.data["entities"]
            if entity["kind"] == "person" and entity["id"] in person_ids
        ]

    def _offer_packet_anchor_to_reviews(self, packet: dict, person: dict) -> None:
        """Offer, but do not apply, a packet client to unresolved documents."""
        person_name = person["name"]
        candidate = {"entity_id": person["id"], "name": person_name, "source": "packet_anchor"}
        for item in self.data["review_queue"]:
            if item["status"] != "needs_review" or item.get("intake_occurrence_id"):
                continue
            document = next((entry for entry in self.data["documents"] if entry["id"] == item["document_id"]), None)
            if not document or document.get("intake_packet_id") != packet["id"]:
                continue
            extracted = document["extracted"]
            stated_name = extracted.get("participant") or extracted.get("tenant")
            stated_hmis_id = extracted.get("hmis_id")
            anchor_hmis_id = person.get("attributes", {}).get("hmis_id")
            if stated_hmis_id and anchor_hmis_id and stated_hmis_id != anchor_hmis_id:
                continue
            if stated_name and stated_name.casefold() != person_name.casefold():
                continue
            if item.get("proposed_person_id") == person["id"]:
                continue
            item["candidates"] = [candidate, *[entry for entry in item.get("candidates", []) if entry.get("entity_id") != person["id"]]]
            item["proposed_person_id"] = person["id"]
            item["packet_id"] = packet["id"]
            self._event("packet_client_proposed", document["id"], {
                "packet_id": packet["id"], "document_id": document["id"], "proposed_person_id": person["id"],
                "source": "single_hard_identity_anchor",
            })

    def _record_income_declaration(self, document: dict, extracted: ExtractedDocument) -> dict:
        if not extracted.participant:
            return self._review(document, "Income declaration has no participant identity.")
        if not extracted.reporting_period:
            return self._review(document, "Income declaration is undated or lacks a reporting period. The source remains undated; provide context later if available.")
        participant, review = self._resolve_person_for_document(document, extracted)
        if review:
            return review
        ledger = self._income_ledger(participant)
        event_type = "income_verification_recorded" if extracted.document_type == "income_verification" else "income_declaration_recorded"
        self._event(event_type, ledger["id"], {
            "document_id": document["id"], "participant_id": participant["id"],
            "document_date": extracted.document_date, "reporting_period": extracted.reporting_period,
            "source": "document_extraction",
        })
        self._record_program_checkpoint(participant, document, extracted)
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
        if extracted.document_type == "program_exit":
            return self._record_program_exit(document, extracted, participant)
        program = self._entity("program", extracted.program)
        case_ledger = self._entity("case_ledger", f"{participant['id']} / {extracted.program}")
        self._relationship("enrolled_in", participant["id"], program["id"], "document_extraction")
        self._relationship("has_case", participant["id"], case_ledger["id"], "document_extraction")
        self._event(rule.ledger_event, case_ledger["id"], {
            "document_id": document["id"], "participant_id": participant["id"], "program_id": program["id"],
            "document_date": extracted.document_date, "enrollment_date": extracted.enrollment_date,
            "source": "document_extraction",
        })
        if extracted.document_type == "program_enrollment" and extracted.enrollment_date:
            self._ensure_program_baseline(
                participant, program, case_ledger, enrollment_date=extracted.enrollment_date,
                baseline_date=extracted.enrollment_date, document_id=document["id"], source="enrollment_record",
            )
        return {"status": "filed", "document_id": document["id"], "case_ledger_id": case_ledger["id"], "document_type": extracted.document_type, "confidence": 1.0, "reasons": ["Participant and program are stated in the source document."]}

    def _record_program_exit(self, document: dict, extracted: ExtractedDocument, participant: dict) -> dict:
        if not extracted.exit_date:
            return self._review(document, "Program exit record lacks an exit date. It cannot safely close a program case.")
        candidate_programs = []
        if extracted.program:
            candidate_programs = [entity for entity in self.data["entities"] if entity["kind"] == "program" and entity["name"] == extracted.program]
        else:
            program_ids = {
                relationship["to_entity_id"] for relationship in self.data["relationships"]
                if relationship.get("from_entity_id") == participant["id"] and relationship.get("type") in {"enrolled_in", "program_documented_for"}
            }
            candidate_programs = [entity for entity in self.data["entities"] if entity["id"] in program_ids and entity["kind"] == "program"]
        if len(candidate_programs) != 1:
            return self._review(document, "Program exit record does not identify one unambiguous program case to close.")
        program = candidate_programs[0]
        case_ledger = self._entity("case_ledger", f"{participant['id']} / {program['name']}")
        self._relationship("has_case", participant["id"], case_ledger["id"], "document_extraction")
        self._event("program_exit_recorded", case_ledger["id"], {
            "document_id": document["id"], "participant_id": participant["id"], "program_id": program["id"],
            "exit_date": extracted.exit_date, "document_date": extracted.document_date,
            "source": "document_extraction",
        })
        return {"status": "filed", "document_id": document["id"], "case_ledger_id": case_ledger["id"], "document_type": extracted.document_type, "confidence": 1.0, "reasons": ["Exact HMIS identity and one program case were recorded."]}

    def _record_program_checkpoint(self, participant: dict, document: dict, extracted: ExtractedDocument) -> None:
        """Use a periodic form as evidence of a case without backfilling its past.

        A quarterly form often carries enough legitimate information to build a
        participant/program network.  Its arrival establishes Homesteader's
        baseline *today*, while the form's enrollment date remains the timeline
        anchor.  That avoids treating unimported historical paperwork as an
        error during an in-progress rollout.
        """
        if not extracted.program:
            return
        program = self._entity("program", extracted.program)
        case_ledger = self._entity("case_ledger", f"{participant['id']} / {extracted.program}")
        self._relationship("program_documented_for", participant["id"], program["id"], "document_extraction")
        self._relationship("has_case", participant["id"], case_ledger["id"], "document_extraction")
        self._event("program_checkpoint_recorded", case_ledger["id"], {
            "document_id": document["id"], "participant_id": participant["id"], "program_id": program["id"],
            "document_date": extracted.document_date, "reporting_period": extracted.reporting_period,
            "enrollment_date": extracted.enrollment_date, "source": "document_extraction",
        })
        if extracted.enrollment_date:
            self._ensure_program_baseline(
                participant, program, case_ledger, enrollment_date=extracted.enrollment_date,
                baseline_date=datetime.now(UTC).date().isoformat(), document_id=document["id"], source="periodic_checkpoint",
            )

    def _ensure_program_baseline(self, participant: dict, program: dict, case_ledger: dict, *, enrollment_date: str, baseline_date: str, document_id: str, source: str) -> None:
        existing = next((event for event in self.data["ledger_events"] if event["type"] == "program_baseline_established" and event.get("details", {}).get("participant_id") == participant["id"] and event.get("details", {}).get("program_id") == program["id"]), None)
        if existing:
            return
        self._event("program_baseline_established", case_ledger["id"], {
            "participant_id": participant["id"], "program_id": program["id"], "document_id": document_id,
            "enrollment_date": enrollment_date, "baseline_date": baseline_date, "source": source,
        })

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
        if not extracted.participant and not extracted.hmis_id:
            return None, self._review(document, "Document lacks both a participant name and an HMIS number. It cannot be automatically assigned.")
        match = resolve_person(
            name=extracted.participant,
            date_of_birth=extracted.date_of_birth,
            candidates=self._person_candidates(), hmis_id=extracted.hmis_id,
        )
        if match.decision is IdentityDecision.REVIEW:
            rows = [{"entity_id": candidate.entity_id, "name": candidate.name, "date_of_birth": candidate.date_of_birth} for candidate in self._person_candidates() if candidate.entity_id in match.candidates]
            return None, self._review(document, "; ".join(match.reasons), rows)
        if match.decision is IdentityDecision.CREATE_PROVISIONAL:
            name = extracted.participant or f"Participant {extracted.hmis_id}"
            return self._new_entity("person", name, date_of_birth=extracted.date_of_birth, hmis_id=extracted.hmis_id), None
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

    def _record_housing_document(self, document: dict, extracted: ExtractedDocument) -> dict:
        """File a housing record using only the facts the document actually carries."""
        if not extracted.participant:
            return self._review(document, "Housing record has no participant name to associate with a file.")
        name_matches = [entity for entity in self.data["entities"] if entity["kind"] == "person" and entity["name"].casefold() == extracted.participant.casefold()]
        if len(name_matches) > 1:
            return self._review(
                document,
                "Housing record names multiple possible participant files. Select the intended participant before filing its relationships.",
                [{"entity_id": candidate["id"], "name": candidate["name"], "hmis_id": candidate.get("attributes", {}).get("hmis_id")} for candidate in name_matches],
            )
        participant = name_matches[0] if name_matches else self._new_entity("person", extracted.participant)
        return self._file_housing_relationships(
            document,
            extracted,
            participant,
            association_source="document_extraction" if name_matches else "unique_name_provisional",
        )

    def _file_housing_relationships(self, document: dict, extracted: ExtractedDocument, participant: dict, *, association_source: str) -> dict:
        record = self._new_entity(
            "housing_record",
            f"{extracted.document_type} / {document['original_name']}",
            document_id=document["id"], document_date=extracted.document_date,
        )
        self._relationship("has_housing_record", participant["id"], record["id"], association_source)
        property_entity = unit = None
        if extracted.property_address:
            property_entity = self._entity("property", extracted.property_address)
            self._relationship("concerns_property", record["id"], property_entity["id"], association_source)
            if extracted.unit:
                unit = self._entity("unit", f"{extracted.property_address} / {extracted.unit}")
                self._relationship("unit_of", unit["id"], property_entity["id"], association_source)
                self._relationship("concerns_unit", record["id"], unit["id"], association_source)
        landlord = None
        if extracted.landlord:
            landlord = self._entity("landlord", extracted.landlord)
            self._relationship("involves_landlord", record["id"], landlord["id"], association_source)
            if property_entity:
                self._relationship("landlord_for", landlord["id"], property_entity["id"], association_source)
        ledger = self._participant_ledger(participant)
        self._event("housing_document_recorded", ledger["id"], {
            "document_id": document["id"], "participant_id": participant["id"], "housing_record_id": record["id"],
            "document_type": extracted.document_type, "document_date": extracted.document_date,
            "property_id": property_entity["id"] if property_entity else None,
            "landlord_id": landlord["id"] if landlord else None,
            "source": association_source,
        })
        workflow = self._attach_move_in_workflow(
            document, extracted, participant,
            property_id=property_entity["id"] if property_entity else None,
            unit_id=unit["id"] if unit else None,
            association_source=association_source,
        )
        return {
            "status": "filed", "document_id": document["id"], "participant_id": participant["id"],
            "housing_record_id": record["id"], "move_in_workflow_id": workflow["id"] if workflow else None,
            "confidence": 1.0 if association_source == "document_extraction" else 0.8,
        }

    def _catalog_form(self, document: dict) -> dict:
        title = next((line.strip().title() for line in document["source_text"].splitlines() if line.strip()), document["original_name"])
        form = self._entity("form_template", title)
        self._event("form_cataloged", form["id"], {"document_id": document["id"], "source": "characteristic_classification", "reason": "Blank form title with no completed identity fields."})
        return {"status": "filed", "document_id": document["id"], "form_id": form["id"], "destination": "form_bank", "confidence": 0.95, "reasons": ["Recognized blank form title", "No tenant, premises, or signature fields were completed"]}

    def _create_lease(self, document: dict, extracted: ExtractedDocument) -> dict:
        if not all([extracted.tenant, extracted.property_address, extracted.unit, extracted.signed_date]):
            return self._review(document, "Lease is missing an identifier required for safe filing.")
        name_matches = [entity for entity in self.data["entities"] if entity["kind"] == "person" and entity["name"].casefold() == extracted.tenant.casefold()]
        if len(name_matches) > 1:
            return self._review(
                document,
                "Lease names multiple possible participant files. Select the intended participant before filing the lease relationship.",
                [{"entity_id": candidate["id"], "name": candidate["name"], "hmis_id": candidate.get("attributes", {}).get("hmis_id")} for candidate in name_matches],
            )
        tenant = name_matches[0] if name_matches else self._new_entity("person", extracted.tenant)
        return self._file_lease_relationship(
            document,
            extracted,
            tenant,
            association_source="document_extraction" if name_matches else "unique_name_provisional",
        )

    def _file_lease_relationship(self, document: dict, extracted: ExtractedDocument, tenant: dict, *, association_source: str) -> dict:
        """Create the relationship graph once the participant association is safe.

        This is used both by deterministic intake and after a human resolves
        same-name ambiguity. The source is recorded so a manual selection is
        never misrepresented as an automatic identity match.
        """
        property_entity = self._entity("property", extracted.property_address)
        unit = self._entity("unit", f"{extracted.property_address} / {extracted.unit}")
        self._relationship("unit_of", unit["id"], property_entity["id"], association_source)
        landlord = self._entity("landlord", extracted.landlord) if extracted.landlord else None
        if landlord:
            self._relationship("landlord_for", landlord["id"], property_entity["id"], association_source)
        lease = self._entity("lease", f"{extracted.tenant} / {extracted.property_address} / {extracted.unit} / {extracted.signed_date}")
        self._relationship("governs", lease["id"], unit["id"], association_source)
        self._relationship("tenant_under", tenant["id"], lease["id"], association_source)
        self._event("lease_created", lease["id"], {
            "document_id": document["id"], "tenant_id": tenant["id"], "property_id": property_entity["id"],
            "unit_id": unit["id"], "source": association_source,
        })
        workflow = self._attach_move_in_workflow(
            document, extracted, tenant, property_id=property_entity["id"], unit_id=unit["id"],
            association_source=association_source,
        )
        reasons = ["Lease contains participant, property, unit, and signing date."]
        if landlord:
            reasons.append("Lease identifies a landlord linked to the property.")
        confidence = 1.0 if association_source == "document_extraction" else 0.8
        return {
            "status": "filed", "document_id": document["id"], "lease_id": lease["id"],
            "participant_id": tenant["id"], "move_in_workflow_id": workflow["id"] if workflow else None,
            "confidence": confidence, "reasons": reasons,
        }

    def _attach_move_in_workflow(
        self, document: dict, extracted: ExtractedDocument, participant: dict, *,
        property_id: str | None, unit_id: str | None, association_source: str,
    ) -> dict | None:
        """Attach one recognized record to a participant's local move-in workflow.

        This intentionally uses only the participant plus recorded property/unit
        context. A W-9 or ownership record without safe participant context stays
        available for review rather than being attached to a guessed move-in.
        """
        eligible_types = record_keys(self.move_in_definition) | {"lease"}
        if extracted.document_type not in eligible_types:
            return None
        candidates = [
            workflow for workflow in self.data["move_in_workflows"]
            if workflow.get("participant_id") == participant["id"]
            and (not property_id or not workflow.get("property_id") or workflow.get("property_id") == property_id)
            and (not unit_id or not workflow.get("unit_id") or workflow.get("unit_id") == unit_id)
        ]
        workflow = candidates[0] if len(candidates) == 1 else None
        if not workflow:
            workflow = {
                "id": str(uuid4()), "kind": "housing_move_in", "participant_id": participant["id"],
                "property_id": property_id, "unit_id": unit_id, "record_types": [],
                "document_ids": [], "fact_claims": [], "created_at": now(), "source": association_source,
            }
            self.data["move_in_workflows"].append(workflow)
            self._event("move_in_workflow_opened", workflow["id"], {
                "participant_id": participant["id"], "property_id": property_id, "unit_id": unit_id,
                "document_id": document["id"], "source": association_source,
            })
        if property_id and not workflow.get("property_id"):
            workflow["property_id"] = property_id
        if unit_id and not workflow.get("unit_id"):
            workflow["unit_id"] = unit_id
        if document["id"] not in workflow["document_ids"]:
            workflow["document_ids"].append(document["id"])
        if extracted.document_type not in workflow["record_types"]:
            workflow["record_types"].append(extracted.document_type)
        workflow.setdefault("fact_claims", [])
        for field, value in self._move_in_fact_values(extracted).items():
            normalized_value = self._normalize_move_in_fact(field, value)
            if not normalized_value:
                continue
            existing = next((claim for claim in workflow["fact_claims"] if claim["document_id"] == document["id"] and claim["field"] == field), None)
            if existing:
                continue
            workflow["fact_claims"].append({
                "field": field, "value": value, "normalized_value": normalized_value,
                "document_id": document["id"], "record_type": extracted.document_type,
                "provenance": association_source, "recorded_at": now(),
            })
        self._event("move_in_record_attached", workflow["id"], {
            "participant_id": participant["id"], "property_id": workflow.get("property_id"),
            "unit_id": workflow.get("unit_id"), "document_id": document["id"],
            "record_type": extracted.document_type, "source": association_source,
        })
        return workflow

    @staticmethod
    def _move_in_fact_values(extracted: ExtractedDocument) -> dict[str, str]:
        """Return only cross-document facts that should agree when both exist."""
        return {
            field: value for field, value in {
                "property_address": extracted.property_address,
                "unit": extracted.unit,
                "monthly_rent": extracted.monthly_rent,
                "security_deposit": extracted.security_deposit,
                "move_in_date": extracted.move_in_date,
                "lease_term": extracted.lease_term,
            }.items() if value
        }

    @staticmethod
    def _normalize_move_in_fact(field: str, value: str) -> str:
        compact = re.sub(r"\s+", " ", value).strip().casefold()
        if field in {"monthly_rent", "security_deposit"}:
            amount = re.sub(r"[^0-9.]", "", compact)
            try:
                return format(Decimal(amount).normalize(), "f")
            except (InvalidOperation, ValueError):
                return amount
        return compact

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

    def _review(self, document: dict, reason: str, candidates: list[dict] | None = None, **details) -> dict:
        item = {"id": str(uuid4()), "document_id": document["id"], "reason": reason, "category": review_category(reason), "candidates": candidates or [], "status": "needs_review", "created_at": now(), **details}
        self.data["review_queue"].append(item)
        return {"status": "needs_review", "review_id": item["id"], "document_id": document["id"], "reason": reason, "candidates": item["candidates"]}

    def _review_existing(self, document: dict, reason: str, intake_occurrence_id: str) -> dict:
        item = {"id": str(uuid4()), "document_id": document["id"], "intake_occurrence_id": intake_occurrence_id, "reason": reason, "category": review_category(reason), "status": "needs_review", "created_at": now()}
        self.data["review_queue"].append(item)
        return {"status": "needs_review", "document_id": document["id"], "intake_occurrence_id": intake_occurrence_id, "reason": reason}

    def pending_reviews(self) -> list[dict]:
        return [item for item in self.data["review_queue"] if item["status"] == "needs_review"]

    def review_suggestion(self, review: dict) -> dict:
        """Describe the next safe staging action without changing the source.

        A suggestion is deliberately not a verdict or an automatic filing
        decision.  It helps a reviewer distinguish a usable-but-ambiguous
        record from a blank or otherwise non-viable upload.
        """
        document = next((item for item in self.data["documents"] if item["id"] == review.get("document_id")), None)
        if not document:
            return {"kind": "source_missing", "label": "Source unavailable", "detail": "The archived source is unavailable; restore it before making a filing decision."}
        extracted = document.get("extracted", {})
        if extracted.get("document_type") == "form_template":
            return {"kind": "form_template", "label": "Reusable blank form", "detail": "This appears to be a blank reusable form, not participant evidence. Store it in the Form Bank if that is correct."}
        meaningful_fields = ("participant", "tenant", "hmis_id", "date_of_birth", "property_address", "unit", "landlord", "document_date", "signed_date")
        if not any(extracted.get(field) for field in meaningful_fields):
            return {"kind": "non_viable", "label": "Document is not viable for a participant file", "detail": "No usable identity, property, date, or completed-record evidence was extracted. Preserve the source locally, but exclude it from files, packet evidence, and export unless it is later reopened."}
        return {"kind": "needs_review", "label": "Usable source needs a human decision", "detail": "The source contains potentially useful evidence, but the current association or required facts are not supported strongly enough to file automatically."}

    def resolve_review(self, review_id: str, action: str, *, entity_id: str | None = None, new_person_name: str | None = None, note: str | None = None, context_note: str | None = None) -> dict:
        item = next((review for review in self.data["review_queue"] if review["id"] == review_id), None)
        if not item:
            raise ValueError(f"Review item '{review_id}' does not exist.")
        if item["status"] != "needs_review":
            raise ValueError(f"Review item '{review_id}' is already resolved.")
        resolution: dict[str, str | None] = {"action": action, "entity_id": entity_id, "note": note, "context_note": context_note}
        person: dict | None = None
        if action == "assign_existing":
            person = next((entity for entity in self.data["entities"] if entity["id"] == entity_id and entity["kind"] == "person"), None)
            if not person:
                raise ValueError("assign_existing requires an existing entity ID.")
        elif action == "create_person":
            if not new_person_name:
                raise ValueError("create_person requires new_person_name.")
            person = self._new_entity("person", new_person_name)
            resolution["entity_id"] = person["id"]
        elif action == "catalog_form":
            pass
        elif action == "archive_non_viable":
            if not note or not note.strip():
                raise ValueError("archive_non_viable requires a brief reason so the source can be understood later.")
        elif action == "accept_revision":
            if not item.get("revision_of_document_id"):
                raise ValueError("accept_revision is only available for a completed-revision proposal.")
        elif action != "leave_unassigned":
            raise ValueError("Action must be assign_existing, create_person, catalog_form, archive_non_viable, accept_revision, or leave_unassigned.")
        item["status"] = "resolved"
        item["resolution"] = resolution
        item["resolved_at"] = now()
        self._event("human_review_resolved", item["document_id"], {"review_id": review_id, **resolution})
        document = next((entry for entry in self.data["documents"] if entry["id"] == item["document_id"]), None)
        if document and context_note and context_note.strip():
            annotation = {
                "id": str(uuid4()), "text": context_note.strip(), "provenance": "user_context_note",
                "recorded_at": now(), "review_id": review_id,
            }
            document.setdefault("context_annotations", []).append(annotation)
            self._event("document_context_annotated", document["id"], {
                "document_id": document["id"], "annotation_id": annotation["id"], "source": "user_context_note",
            })
        if action == "catalog_form" and document:
            form_result = self._catalog_form(document)
            resolution["form_id"] = form_result["form_id"]
            item["resolution"] = resolution
        if action == "archive_non_viable" and document:
            disposition = {
                "kind": "non_viable", "reason": note.strip(), "review_id": review_id,
                "recorded_at": now(), "source": "human_review",
            }
            document["staging_disposition"] = disposition
            document.setdefault("staging_disposition_history", []).append(disposition.copy())
            self._event("staging_disposition_recorded", document["id"], {
                "document_id": document["id"], "review_id": review_id,
                "disposition": "non_viable", "reason": note.strip(), "source": "human_review",
            })
        if action == "accept_revision" and document:
            prior_id = item["revision_of_document_id"]
            relationship = {
                "id": str(uuid4()), "type": "supersedes_for_fields", "from_document_id": document["id"],
                "to_document_id": prior_id, "fields": item.get("revision_fields", []),
                "provenance": "human_review", "created_at": now(),
            }
            self.data["relationships"].append(relationship)
            document["accepted_revision_of_document_id"] = prior_id
            document["authoritative_fields"] = item.get("revision_fields", [])
            self._event("completed_revision_confirmed", document["id"], {
                "document_id": document["id"], "prior_document_id": prior_id,
                "fields": item.get("revision_fields", []), "review_id": review_id, "note": note,
                "source": "human_review",
            })
        if person:
            ledger = self._participant_ledger(person)
            self._event("document_manually_assigned", ledger["id"], {
                "document_id": item["document_id"], "participant_id": person["id"], "review_id": review_id,
                "action": action, "note": note, "source": "human_review",
            })
            if document and context_note and context_note.strip():
                evidence = self._new_entity("context_evidence", f"{document['original_name']} / {document['id']}", document_id=document["id"])
                self._relationship("has_context_evidence", person["id"], evidence["id"], "human_review")
                self._link_context_note_entities(evidence, context_note.strip())
                self._event("context_evidence_linked", evidence["id"], {
                    "document_id": document["id"], "participant_id": person["id"], "review_id": review_id,
                    "source": "human_context_note",
                })
            if action == "assign_existing" and document:
                extracted = ExtractedDocument(**document["extracted"])
                if extracted.document_type == "lease":
                    lease_result = self._file_lease_relationship(document, extracted, person, association_source="human_review")
                    self._event("lease_relationship_confirmed", lease_result["lease_id"], {
                        "document_id": document["id"], "participant_id": person["id"], "review_id": review_id,
                        "source": "human_review",
                    })
                elif extracted.document_type == "housing_record" or extracted.document_type in record_keys(self.move_in_definition):
                    record_result = self._file_housing_relationships(document, extracted, person, association_source="human_review")
                    self._event("housing_relationships_confirmed", record_result["housing_record_id"], {
                        "document_id": document["id"], "participant_id": person["id"], "review_id": review_id,
                        "source": "human_review",
                    })
        return {"status": "resolved", "review_id": review_id, "resolution": resolution}

    def reopen_non_viable_document(self, document_id: str, *, note: str | None = None) -> dict:
        """Return a retained non-viable source to the human review queue.

        The prior disposition remains in history; reopening never erases the
        original scan, the earlier decision, or its reason.
        """
        document = next((item for item in self.data["documents"] if item["id"] == document_id), None)
        if not document:
            raise ValueError("Document does not exist.")
        disposition = document.get("staging_disposition") or {}
        if disposition.get("kind") != "non_viable":
            raise ValueError("Only a non-viable source can be reopened.")
        previous = disposition.copy()
        document.pop("staging_disposition", None)
        self._event("staging_disposition_reopened", document_id, {
            "document_id": document_id, "previous_disposition": previous,
            "note": note or "", "source": "human_review",
        })
        result = self._review(
            document,
            "A previously non-viable staging source was reopened; inspect the original before filing.",
            reopened_from_disposition=previous,
        )
        return {"status": "needs_review", "review_id": result["review_id"], "document_id": document_id}

    def _link_context_note_entities(self, evidence: dict, context_note: str) -> None:
        """Link only exact, already-known entities explicitly named in context.

        A user note is useful provenance, but it should not create a guessed
        property or landlord from a vague phrase. Exact known names and clear
        unit labels are safe enough to record as user-context relationships.
        """
        note = context_note.casefold()
        for entity in self.data["entities"]:
            if entity["kind"] == "property" and entity["name"].casefold() in note:
                self._relationship("context_mentions_property", evidence["id"], entity["id"], "user_context_note")
            elif entity["kind"] == "landlord" and entity["name"].casefold() in note:
                self._relationship("context_mentions_landlord", evidence["id"], entity["id"], "user_context_note")
            elif entity["kind"] == "unit":
                unit_label = entity["name"].rsplit(" / ", 1)[-1].casefold()
                if unit_label and re.search(rf"\bunit\s+{re.escape(unit_label)}\b", note):
                    self._relationship("context_mentions_unit", evidence["id"], entity["id"], "user_context_note")
