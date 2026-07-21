"""Case-management domain vocabulary for Homesteader's generic core.

The core owns intake, source preservation, relationships, ledgers, review, and
provenance. This module names the case-management documents and the minimum
facts needed to file them safely.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CaseDocumentRule:
    document_type: str
    required_fields: frozenset[str]
    ledger_event: str


DOCUMENT_RULES = {
    "program_enrollment": CaseDocumentRule(
        "program_enrollment", frozenset({"participant", "program", "hmis_id"}), "program_enrollment_recorded"
    ),
    "consent_to_share": CaseDocumentRule(
        "consent_to_share", frozenset({"participant", "program", "hmis_id"}), "consent_recorded"
    ),
    "program_exit": CaseDocumentRule(
        "program_exit", frozenset({"participant", "hmis_id"}), "program_exit_recorded"
    ),
    "income_declaration": CaseDocumentRule(
        "income_declaration", frozenset({"participant", "reporting_period", "hmis_id"}), "income_declaration_recorded"
    ),
}
