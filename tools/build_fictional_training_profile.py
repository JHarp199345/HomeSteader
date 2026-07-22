#!/usr/bin/env python3
"""Create a clearly marked, fictional training packet from local blank PDFs.

This script never edits a source template.  It overlays only invented data on
copies and labels every page so a generated file cannot be mistaken for a
participant record or a submission-ready form.
"""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color, HexColor
from reportlab.pdfgen import canvas


PROFILE = {
    "name": "Jordan Atlas",
    "first_name": "Jordan",
    "last_name": "Atlas",
    "hmis_id": "H-TRAIN-0001",
    "dob": "08/14/1992",
    "phone": "555-0100",
    "email": "jordan.atlas@example.invalid",
    "program": "TLS Adult SPA 2",
    "enrollment": "01/15/2026",
    "landlord": "Horizon Training Housing LLC",
    "landlord_contact": "Morgan Vale",
    "property": "421 Fictional Boulevard",
    "unit": "4B",
    "city": "Example City",
    "zip": "00000",
    "move_in": "02/01/2026",
    "rent": "$1,450.00",
    "deposit": "$1,450.00",
    "income_source": "Pacific Training Cooperative",
    "income": "$2,380.00",
    "staff": "Caseworker Demo",
    "supervisor": "Supervisor Demo",
    "emergency": "Mariah Atlas",
    "next_of_kin": "Orson Atlas",
    "provider": "Example Community Health",
    "mental_health": "Example Behavioral Health",
}

BLUE = HexColor("#145A9C")
RED = Color(0.72, 0.05, 0.05, alpha=0.78)


def draw_text(page: canvas.Canvas, x: float, y: float, text: str, size: float = 8) -> None:
    page.setFont("Helvetica", size)
    page.setFillColor(BLUE)
    page.drawString(x, y, text)


def draw_check(page: canvas.Canvas, x: float, y: float) -> None:
    page.setFont("Helvetica-Bold", 9)
    page.setFillColor(BLUE)
    page.drawString(x, y, "X")


def watermark(page: canvas.Canvas, width: float, height: float) -> None:
    page.saveState()
    page.setFillColor(RED)
    page.setFont("Helvetica-Bold", 7)
    page.drawRightString(width - 18, 14, "FICTIONAL TRAINING DATA - NOT FOR SUBMISSION")
    page.restoreState()


def overlay_pdf(source: Path, destination: Path, placements: dict[int, list[tuple]]) -> None:
    reader = PdfReader(source)
    writer = PdfWriter()
    for index, original_page in enumerate(reader.pages):
        width = float(original_page.mediabox.width)
        height = float(original_page.mediabox.height)
        stream = BytesIO()
        layer = canvas.Canvas(stream, pagesize=(width, height))
        watermark(layer, width, height)
        for item in placements.get(index, []):
            kind, *values = item
            if kind == "text":
                draw_text(layer, *values)
            elif kind == "check":
                draw_check(layer, *values)
        layer.save()
        stream.seek(0)
        original_page.merge_page(PdfReader(stream).pages[0])
        writer.add_page(original_page)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        writer.write(handle)


def intake_placements() -> dict[int, list[tuple]]:
    p = PROFILE
    return {
        # Participant information / contact sheet.
        7: [
            ("text", 55, 645, p["name"]), ("text", 360, 645, p["hmis_id"]),
            ("text", 85, 621, p["dob"]), ("text", 217, 621, p["phone"]),
            ("text", 55, 598, p["email"]),
            ("text", 100, 498, p["emergency"]), ("text", 385, 498, "Sister"),
            ("text", 65, 479, "123 Training Way, Example City, CA 00000"),
            ("text", 45, 459, "555-0102"),
            ("text", 100, 395, p["next_of_kin"]), ("text", 422, 395, "Father"),
            ("text", 65, 369, "123 Training Way, Example City, CA 00000"),
            ("text", 45, 348, "555-0103"),
            ("text", 95, 280, p["provider"]), ("text", 55, 260, "555-0110"),
            ("text", 98, 237, "Example Clinic"), ("text", 72, 215, "Training Plan"),
            ("text", 375, 280, p["mental_health"]), ("text", 330, 260, "555-0111"),
            ("text", 375, 237, "Example Clinic"), ("text", 350, 215, "Training Plan"),
        ],
        # Diligence form: identity, staff and a fictional contact attempt.
        8: [
            ("text", 95, 696, p["hmis_id"]), ("text", 300, 696, p["name"]),
            ("text", 100, 494, p["staff"]), ("text", 300, 494, "Hope the Mission - Training"),
            ("text", 100, 405, "01/10/2026"), ("text", 180, 405, "Example Shelter intake desk by phone"),
            ("text", 455, 405, "Training verification only"),
            ("text", 100, 165, p["staff"]), ("text", 100, 143, "Training Caseworker"),
            ("text", 300, 165, "training@example.invalid"), ("text", 470, 165, "555-0199"),
            ("text", 100, 121, "Caseworker Demo - TRAINING"), ("text", 470, 121, "01/10/2026"),
        ],
        # Program agreement and progressive timeline.
        12: [("text", 105, 85, p["name"]), ("text", 325, 85, "01/15/2026"), ("text", 105, 62, "Jordan Atlas - TRAINING"), ("text", 325, 62, "01/15/2026"), ("text", 105, 40, "Caseworker Demo - TRAINING"), ("text", 325, 40, "01/15/2026")],
        14: [("text", 98, 168, p["name"]), ("text", 98, 146, p["staff"]), ("text", 330, 146, "01/15/2026"), ("text", 98, 124, "Jordan Atlas - TRAINING"), ("text", 330, 124, "01/15/2026"), ("text", 98, 102, "Caseworker Demo - TRAINING"), ("text", 330, 102, "01/15/2026")],
        # Consent, privacy, rights, media and transportation acknowledgement signatures.
        16: [("text", 105, 112, p["name"]), ("text", 105, 90, "Jordan Atlas - TRAINING"), ("text", 330, 90, "01/15/2026"), ("text", 105, 68, "Caseworker Demo - TRAINING"), ("text", 330, 68, "01/15/2026")],
        23: [("text", 98, 145, p["name"]), ("text", 98, 122, "Jordan Atlas - TRAINING"), ("text", 330, 122, "01/15/2026"), ("text", 98, 99, p["staff"]), ("text", 330, 99, "01/15/2026")],
        24: [("text", 90, 682, p["name"]), ("text", 90, 660, "Jordan Atlas - TRAINING"), ("text", 330, 660, "01/15/2026"), ("text", 90, 638, p["staff"]), ("text", 330, 638, "01/15/2026")],
        27: [("text", 95, 194, p["name"]), ("text", 95, 172, "Jordan Atlas - TRAINING"), ("text", 330, 172, "01/15/2026")],
        28: [("check", 102, 606), ("text", 95, 570, p["name"]), ("text", 95, 548, "Jordan Atlas - TRAINING"), ("text", 330, 548, "01/15/2026"), ("text", 95, 526, p["staff"]), ("text", 330, 526, "01/15/2026")],
        31: [("text", 95, 676, p["name"]), ("text", 95, 654, "Jordan Atlas - TRAINING"), ("text", 330, 654, "01/15/2026")],
        32: [("check", 105, 354), ("text", 95, 280, p["name"]), ("text", 95, 258, "Jordan Atlas - TRAINING"), ("text", 330, 258, "01/15/2026"), ("text", 95, 236, p["staff"]), ("text", 330, 236, "01/15/2026")],
        33: [("text", 95, 594, p["name"]), ("text", 95, 572, "Jordan Atlas - TRAINING"), ("text", 330, 572, "01/15/2026")],
        34: [("check", 102, 510), ("text", 95, 132, p["name"]), ("text", 95, 110, "Jordan Atlas - TRAINING"), ("text", 330, 110, "01/15/2026"), ("text", 95, 88, p["staff"]), ("text", 330, 88, "01/15/2026")],
        # Initial income form and budget / asset forms.
        35: [("text", 90, 722, p["name"]), ("text", 340, 722, p["dob"]), ("text", 510, 722, p["hmis_id"]), ("check", 92, 528), ("text", 150, 493, p["income_source"]), ("text", 360, 493, p["income"]), ("text", 490, 493, "Monthly"), ("text", 100, 408, "Training scenario: employer letter unavailable."), ("text", 100, 386, "Fictional data used for Homesteader validation."), ("text", 100, 340, p["staff"]), ("text", 340, 340, "Case Manager"), ("text", 100, 318, "Caseworker Demo - TRAINING"), ("text", 340, 318, "01/15/2026")],
        37: [("text", 140, 716, p["rent"]), ("text", 412, 716, p["income"]), ("text", 140, 690, "$55.00"), ("text", 412, 690, "N/A"), ("text", 140, 664, "$110.00"), ("text", 412, 664, "N/A"), ("text", 140, 638, "$60.00"), ("text", 412, 638, "N/A"), ("text", 410, 102, p["name"])],
        43: [("text", 95, 680, p["name"]), ("text", 470, 680, "Jordan Atlas - TRAINING"), ("text", 95, 657, p["staff"]), ("text", 470, 657, "01/15/2026")],
        44: [("text", 95, 651, p["name"]), ("text", 95, 629, "None - fictional training profile"), ("text", 95, 110, "Jordan Atlas - TRAINING"), ("text", 330, 110, "01/15/2026")],
        45: [("text", 100, 706, p["name"]), ("text", 100, 678, "Maintain stable housing and build savings."), ("text", 100, 648, "Budget review, landlord communication, employment support."), ("text", 100, 475, p["staff"]), ("text", 330, 475, "01/15/2026")],
        46: [("text", 100, 596, p["name"]), ("text", 100, 570, "Follow up on employment and rent budget."), ("text", 100, 545, "Quarterly financial review completed."), ("text", 100, 520, p["staff"]), ("text", 330, 520, "01/15/2026")],
    }


def quarterly_placements(document_date: str, income: str) -> dict[int, list[tuple]]:
    p = PROFILE
    return {
        0: [("text", 148, 694, p["name"]), ("text", 485, 694, p["hmis_id"]), ("text", 145, 646, document_date), ("text", 415, 646, "10:00 AM"), ("text", 165, 617, "Hope the Mission - Training Office"), ("text", 115, 594, "Housing stability"), ("text", 230, 594, "Maintain rent budget and employment"), ("text", 468, 594, "In progress"), ("text", 80, 238, p["name"]), ("text", 270, 238, "Jordan Atlas - TRAINING"), ("text", 455, 238, document_date), ("text", 80, 172, p["staff"]), ("text", 270, 172, "Caseworker Demo - TRAINING"), ("text", 455, 172, document_date), ("text", 80, 116, p["supervisor"]), ("text", 270, 116, "Supervisor Demo - TRAINING"), ("text", 455, 116, document_date)],
        1: [("text", 105, 705, p["name"]), ("text", 340, 705, p["dob"]), ("text", 505, 705, p["hmis_id"]), ("check", 95, 525), ("text", 150, 494, p["income_source"]), ("text", 360, 494, income), ("text", 495, 494, "Monthly"), ("text", 100, 410, "Fictional training profile; source document simulated."), ("text", 100, 388, "No actual participant or financial data used."), ("text", 100, 340, p["staff"]), ("text", 340, 340, "Case Manager"), ("text", 100, 318, "Caseworker Demo - TRAINING"), ("text", 340, 318, document_date)],
        2: [("text", 125, 714, p["rent"]), ("text", 410, 714, income), ("text", 125, 688, "$55.00"), ("text", 125, 662, "$110.00"), ("text", 125, 636, "$60.00"), ("text", 410, 100, p["name"])],
        7: [("text", 105, 706, p["name"]), ("text", 470, 706, "Jordan Atlas - TRAINING"), ("text", 105, 683, p["staff"]), ("text", 470, 683, document_date)],
        8: [("text", 100, 625, "Not applicable - documented fictional income above."), ("text", 100, 112, "Jordan Atlas - TRAINING"), ("text", 330, 112, document_date)],
    }


def financial_assistance_placements() -> dict[int, list[tuple]]:
    p = PROFILE
    return {0: [
        ("text", 175, 597, "01/28/2026"), ("text", 175, 580, p["program"]), ("text", 175, 560, p["name"]),
        ("check", 99, 487),
        ("text", 140, 422, p["landlord"]), ("text", 140, 406, "123 Fictional Way, Example City, CA 00000"),
        ("text", 140, 390, "$1,000.00"),
        ("text", 140, 352, "February 2026 rental assistance for fictional training profile."),
        ("text", 100, 256, p["staff"]), ("text", 275, 256, "Caseworker Demo - TRAINING"), ("text", 440, 256, "01/28/2026"),
    ]}


def landlord_placements() -> dict[int, list[tuple]]:
    p = PROFILE
    return {
        0: [("text", 95, 698, p["landlord"]), ("text", 95, 676, "Horizon Training Housing LLC"), ("text", 95, 654, "123 Fictional Way"), ("text", 95, 632, "Example City, CA 00000"), ("text", 95, 610, "TRAINING-TIN-0001"), ("text", 390, 274, "Morgan Vale - TRAINING"), ("text", 505, 274, "01/28/2026")],
        6: [("text", 110, 684, p["landlord"]), ("text", 350, 684, p["name"]), ("text", 110, 662, p["property"]), ("text", 110, 640, "Example City, CA 00000"), ("text", 110, 618, "555-0120"), ("check", 105, 492), ("text", 105, 421, p["rent"]), ("text", 265, 421, p["deposit"]), ("text", 435, 421, "01/01/2026"), ("text", 105, 325, p["landlord"]), ("text", 270, 325, "Morgan Vale - TRAINING"), ("text", 440, 325, "01/28/2026")],
        7: [("text", 102, 704, p["name"]), ("text", 335, 704, p["landlord"]), ("text", 102, 680, p["property"]), ("text", 102, 656, p["unit"]), ("text", 102, 632, "One bedroom apartment"), ("text", 102, 608, p["rent"]), ("text", 350, 608, p["deposit"]), ("text", 102, 583, p["move_in"]), ("check", 105, 508), ("text", 102, 225, p["landlord_contact"]), ("text", 305, 225, "555-0120"), ("text", 102, 202, "Morgan Vale - TRAINING"), ("text", 305, 202, "01/28/2026")],
        8: [("text", 115, 414, p["landlord"]), ("text", 115, 392, p["name"]), ("text", 115, 368, p["property"]), ("text", 115, 344, p["unit"]), ("text", 115, 268, "Morgan Vale - TRAINING"), ("text", 330, 268, "01/28/2026")],
        9: [("text", 100, 706, p["name"]), ("text", 100, 682, p["landlord"]), ("text", 100, 658, p["property"]), ("text", 100, 634, p["unit"]), ("text", 100, 610, p["rent"]), ("text", 100, 412, "Not requested for fictional training profile."), ("text", 100, 116, p["staff"]), ("text", 330, 116, "01/28/2026")],
        10: [("text", 100, 706, p["name"]), ("text", 455, 706, p["hmis_id"]), ("text", 100, 660, p["staff"]), ("text", 100, 616, p["name"]), ("text", 100, 572, p["landlord"]), ("text", 100, 528, p["property"]), ("text", 100, 504, p["unit"]), ("text", 100, 460, p["move_in"]), ("text", 100, 436, p["rent"]), ("text", 100, 412, p["deposit"]), ("text", 100, 152, "Caseworker Demo - TRAINING"), ("text", 330, 152, "01/28/2026")],
        11: [("text", 135, 654, "Apartment"), ("text", 135, 630, p["property"]), ("text", 425, 630, p["unit"]), ("text", 135, 606, "Example City"), ("text", 425, 606, "CA"), ("text", 495, 606, "00000"), ("check", 530, 552), ("check", 530, 530), ("check", 530, 508), ("text", 135, 116, p["staff"]), ("text", 425, 116, "Caseworker Demo - TRAINING"), ("text", 135, 94, p["supervisor"]), ("text", 425, 94, "Supervisor Demo - TRAINING"), ("text", 510, 94, "01/28/2026")],
        12: [("text", 120, 640, "Fictional training inspection completed."), ("text", 120, 615, "Property meets training scenario standards."), ("text", 120, 590, "No repairs requested in fictional exercise."), ("text", 120, 300, "Fictional training profile only."), ("text", 120, 230, "Hope the Mission - Training"), ("text", 120, 206, p["staff"]), ("text", 120, 182, "Caseworker Demo - TRAINING"), ("text", 425, 182, "01/28/2026"), ("text", 120, 158, p["supervisor"]), ("text", 425, 158, "01/28/2026")],
    }


def recertification_placements() -> dict[int, list[tuple]]:
    p = PROFILE
    return {
        0: [("text", 110, 666, p["first_name"]), ("text", 310, 666, p["last_name"]), ("text", 500, 666, p["hmis_id"]), ("text", 130, 642, "07/15/2026"), ("check", 105, 607), ("check", 105, 538), ("text", 355, 513, p["enrollment"]), ("text", 505, 513, "6"), ("text", 355, 465, "5"), ("text", 355, 441, "06/01/2026"), ("check", 105, 356), ("check", 105, 260)],
        1: [("check", 105, 678), ("check", 105, 654), ("check", 105, 508), ("check", 105, 486), ("check", 105, 440), ("check", 105, 342), ("text", 105, 220, p["staff"]), ("text", 305, 220, "Caseworker Demo - TRAINING"), ("text", 490, 220, "07/15/2026"), ("text", 105, 196, p["supervisor"]), ("text", 305, 196, "Supervisor Demo - TRAINING"), ("text", 490, 196, "07/15/2026")],
    }


def write_manifest(output: Path) -> None:
    p = PROFILE
    (output / "TRAINING_PROFILE_MANIFEST.txt").write_text(
        "FICTIONAL TRAINING DATA - NOT FOR SUBMISSION\n\n"
        f"Participant: {p['name']}\nHMIS ID: {p['hmis_id']}\nDOB: {p['dob']}\n"
        f"Program: {p['program']}\nEnrollment: {p['enrollment']}\n\n"
        f"Housing: {p['property']}, Unit {p['unit']}\nLandlord: {p['landlord']}\n"
        f"Move-in: {p['move_in']}\nRent: {p['rent']}\nDeposit: {p['deposit']}\n\n"
        f"Income: {p['income_source']} - {p['income']} monthly\n\n"
        "Every name, identifier, address, contact detail, date, signature, and financial value in this folder is invented.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    template = args.template_dir
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    overlay_pdf(template / "01. TLS Intake Packet.pdf", output / "TRAINING_01_TLS_Intake_Packet_Jordan_Atlas.pdf", intake_placements())
    overlay_pdf(template / "BLANK Financial Assistance Request.pdf", output / "TRAINING_01_Financial_Assistance_Request_Jordan_Atlas.pdf", financial_assistance_placements())
    overlay_pdf(template / "00. Landlord Docs.pdf", output / "TRAINING_01_Move_In_and_Landlord_Docs_Jordan_Atlas.pdf", landlord_placements())
    overlay_pdf(template / "BLANK Quarterly.pdf", output / "TRAINING_01_Quarterly_2026-04_Jordan_Atlas.pdf", quarterly_placements("04/15/2026", "$2,380.00"))
    overlay_pdf(template / "BLANK Quarterly.pdf", output / "TRAINING_01_Quarterly_2026-07_Jordan_Atlas.pdf", quarterly_placements("07/15/2026", "$2,520.00"))
    overlay_pdf(template / "BLANK Recertification form.pdf", output / "TRAINING_01_Recertification_Jordan_Atlas.pdf", recertification_placements())
    write_manifest(output)
    print(output)


if __name__ == "__main__":
    main()
