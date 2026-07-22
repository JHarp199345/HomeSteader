"""Evidence-backed correction findings for local case-file audits."""

from __future__ import annotations

RECOMMENDATIONS = {
    "identity_conflict": "Compare the source documents and HMIS record, then confirm the correct participant file before filing this document.",
    "missing_identity": "Locate or obtain the participant HMIS number, then confirm the correct participant file before filing.",
    "duplicate_check": "Compare the original source and intake occurrence. Mark it as an accidental duplicate or document why it is a distinct submission.",
    "ocr_confirmation": "Compare the original scan to the OCR text and confirm the participant association and extracted facts.",
    "missing_time_context": "Obtain or document the reporting period from a reliable source. Do not invent or backdate the source document date.",
    "classification": "Review the original document and classify it as a client record, a reusable form, or an item requiring policy guidance.",
    "other_review": "Review the source document and record the necessary correction or filing decision.",
    "temporary_identity": "Verify the participant HMIS number and replace the temporary identifier only after confirmation.",
    "source_archive_missing": "Restore the original source file from the approved intake location or backup before relying on extracted metadata.",
    "ingestion_integrity": "Re-ingest the original source through Homesteader's local intake path. Do not rely on a record that lacks its preserved-source evidence trail.",
    "scheduled_record_missing": "Verify whether this scheduled record was completed and upload or document the appropriate record. If an approved exception applies, record that exception in the participant ledger.",
    "revision_confirmation": "Compare both source documents. Confirm the newer copy only if it is the same document instance and its additional fields are supported by the source.",
    "move_in_fact_conflict": "Compare the cited original records, determine the correct value through the appropriate casework process, and preserve the conflicting source records rather than overwriting either one.",
    "packet_evidence_missing": "Locate the listed source record or document an approved exception. Do not mark the packet ready merely because other pages were uploaded.",
}


def correction_findings(store) -> list[dict]:
    """Return correction-report rows without changing any record.

    `caseworker` is currently optional local metadata. Until an assignment source
    exists, the report says "Not recorded" rather than guessing ownership.
    """
    documents = {document["id"]: document for document in store.data["documents"]}
    people = {entity["id"]: entity for entity in store.data["entities"] if entity["kind"] == "person"}
    findings = []

    def participant_details(person_id: str | None) -> tuple[str, str, str]:
        person = people.get(person_id or "")
        if not person:
            return "Unassigned participant", "", "Not recorded"
        attributes = person.get("attributes", {})
        return person["name"], attributes.get("hmis_id") or attributes.get("temporary_id") or "", attributes.get("caseworker") or "Not recorded"

    def append(
        *, category: str, person_id: str | None, document: dict | None,
        error: str, source: str, program: str = "", finding_date: str = "",
    ) -> None:
        ptc, identifier, caseworker = participant_details(person_id)
        extracted = (document or {}).get("extracted", {})
        findings.append({
            "caseworker": caseworker,
            "ptc": ptc,
            "participant_identifier": identifier,
            "document": document["original_name"] if document else "",
            "document_id": document["id"] if document else "",
            "category": category.replace("_", " ").title(),
            "error": error,
            "recommendation": RECOMMENDATIONS[category],
            "source": source,
            "program": program or extracted.get("program") or "",
            "finding_date": finding_date or extracted.get("document_date") or "",
        })

    for person in people.values():
        if not person.get("attributes", {}).get("hmis_id"):
            append(
                category="temporary_identity", person_id=person["id"], document=None,
                error="Participant file has a temporary identifier rather than a confirmed HMIS number.",
                source="Local participant identity record",
            )

    for review in store.pending_reviews():
        document = documents.get(review["document_id"])
        candidate_ids = [candidate.get("entity_id") for candidate in review.get("candidates", []) if candidate.get("entity_id")]
        proposed = review.get("proposed_person_id")
        append(
            category=review.get("category", "other_review"), person_id=proposed or (candidate_ids[0] if len(candidate_ids) == 1 else None),
            document=document, error=review["reason"], source="Homesteader review queue",
        )

    for document in documents.values():
        stored_path = document.get("stored_source_path")
        if stored_path and not (store.path.parent / stored_path).exists():
            append(
                category="source_archive_missing", person_id=None, document=document,
                error="The local archive copy of this source document is missing.",
                source="Local source archive check",
            )

    for integrity in store.ingestion_integrity():
        document = documents.get(integrity["document_id"])
        append(
            category="ingestion_integrity", person_id=None, document=document,
            error="This staged record is missing: " + ", ".join(integrity["missing"]) + ".",
            source="Canonical intake-path integrity check",
        )

    for status in store.housing_schedule_status():
        if status["status"] != "missing":
            continue
        person = people.get(status["person_id"])
        append(
            category="scheduled_record_missing", person_id=status["person_id"], document=None,
            error=(f"No {status['requirement']} was recorded for the period beginning "
                   f"{status['due_date']} in {status['program']} (enrolled {status['enrollment_date']})."),
            source="Housing Services standard schedule",
            program=status["program"], finding_date=status["due_date"],
        )

    for workflow in store.move_in_workflow_status():
        for conflict in workflow.get("conflicts", []):
            append(
                category="move_in_fact_conflict", person_id=workflow["participant_id"], document=None,
                error=(f"Move-in workflow has conflicting {conflict['field'].replace('_', ' ')} values: "
                       f"{'; '.join(conflict['values'])}."),
                source="Housing Services move-in workflow consistency check",
            )

    for packet in store.data.get("intake_packets", []):
        if packet.get("status") != "closed":
            continue
        status = store.packet_completeness(packet["id"])
        if status["status"] != "incomplete":
            continue
        for missing in status["missing"]:
            append(
                category="packet_evidence_missing", person_id=packet.get("proposed_person_id"), document=None,
                error=(f"{status['requirement']} packet '{packet.get('label') or packet['id']}' is missing local evidence for "
                       f"{missing['title']} (expected pages {missing['start_page']}–{missing['end_page']})."),
                source="Local Form Bank packet definition",
            )

    return sorted(findings, key=lambda row: (row["caseworker"], row["ptc"], row["category"], row["document"]))


def filter_correction_findings(
    findings: list[dict], *, query: str = "", caseworker: str | None = None,
    program: str | None = None, category: str | None = None,
    date_from: str | None = None, date_to: str | None = None,
) -> list[dict]:
    """Narrow correction findings without changing any local record.

    Dates are source document dates where available, or the due date for a
    missing scheduled record. Blank dates stay visible unless the user chooses
    a date filter; that prevents undated source records from being mistaken for
    nonexistent ones.
    """
    needle = query.strip().casefold()
    filtered = []
    for finding in findings:
        if needle and needle not in " ".join([
            finding.get("ptc", ""), finding.get("participant_identifier", ""),
            finding.get("document", ""), finding.get("error", ""),
        ]).casefold():
            continue
        if caseworker and finding.get("caseworker") != caseworker:
            continue
        if program and finding.get("program") != program:
            continue
        if category and finding.get("category") != category:
            continue
        finding_date = finding.get("finding_date") or ""
        if date_from and (not finding_date or finding_date < date_from):
            continue
        if date_to and (not finding_date or finding_date > date_to):
            continue
        filtered.append(finding)
    return filtered
