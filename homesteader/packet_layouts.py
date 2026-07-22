"""Known logical-document layouts inside composite source PDFs.

A scan may be one PDF while containing many logical records.  This module
keeps the original scan intact and records page spans for human review and
selected export.  It never splits or reorders evidence at intake time.
"""

from __future__ import annotations


TLS_INTAKE_LAYOUT = {
    "layout_id": "tls_intake_packet_v1",
    "title": "TLS Intake Packet",
    "minimum_pages": 47,
    "parts": [
        ("filing_index", "Packet filing index", 1, 7, "Packet index"),
        ("participant_information", "Participant information and contact sheet", 8, 8, "Identity & intake"),
        ("homelessness_verification", "Homelessness verification", 9, 11, "Identity & intake"),
        ("program_agreement", "TLS program agreement and progressive assistance timeline", 12, 14, "Program documents"),
        ("hmis_consent", "HMIS consent to share protected personal information", 15, 17, "Program documents"),
        ("grievance_policy", "Grievance and ADA grievance policy, forms, and acknowledgement", 18, 26, "Program documents"),
        ("client_rights", "Privacy notice and client rights and responsibilities", 27, 32, "Program documents"),
        ("releases_and_conduct", "Media release, confidential-information release, and transportation code", 33, 35, "Program documents"),
        ("income_declaration", "Self-declaration of income or no income", 36, 37, "Income verification"),
        ("monthly_budget", "Monthly budget", 38, 38, "Income verification"),
        ("nmtc_income_certification", "New Markets Tax Credit income certification", 39, 43, "Income verification"),
        ("asset_certification", "Under-$5,000 asset certification", 44, 44, "Income verification"),
        ("housing_search_plan", "Housing search plan and housing history", 45, 47, "Case management"),
    ],
}


def logical_document_parts(text: str, page_count: int) -> dict | None:
    """Recognize a known composite packet and return its human-readable map.

    This is intentionally strict. A similar-looking PDF stays an ordinary
    source until a reviewer or a later layout definition identifies it.
    """
    upper = text.upper()
    if page_count < TLS_INTAKE_LAYOUT["minimum_pages"]:
        return None
    if "TLS TAB 1" not in upper or "TLS TAB 6" not in upper:
        return None
    if "GRIEVANCE" not in upper or "HOUSING SEARCH PLAN" not in upper:
        return None
    return {
        "layout_id": TLS_INTAKE_LAYOUT["layout_id"],
        "title": TLS_INTAKE_LAYOUT["title"],
        "page_count": page_count,
        "parts": [
            {
                "id": part_id,
                "title": title,
                "start_page": start,
                "end_page": end,
                "section": section,
                "order": index,
            }
            for index, (part_id, title, start, end, section) in enumerate(TLS_INTAKE_LAYOUT["parts"], start=1)
        ],
    }
