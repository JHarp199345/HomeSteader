#!/usr/bin/env python3
"""Create a clearly marked, fictional training packet from local blank PDFs.

This script never edits a source template.  It overlays only invented data on
copies and labels every page so a generated file cannot be mistaken for a
participant record or a submission-ready form.
"""

from __future__ import annotations

import argparse
import random
import shutil
from dataclasses import dataclass
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


def profile(**changes: str) -> dict[str, str]:
    """Return a fictional variation without ever touching a source template."""
    return PROFILE | changes


# The data intentionally creates difficult but legitimate identity situations.
# Every value is invented and deliberately unsuitable for any real submission.
HATEFUL_EIGHT = [
    profile(name="Jordan Atlas", first_name="Jordan", last_name="Atlas", hmis_id="H-TRAIN-0001", dob="08/14/1992", property="421 Fictional Boulevard", unit="4B"),
    profile(name="Riley Boone", first_name="Riley", last_name="Boone", hmis_id="H-TRAIN-0002", dob="03/22/1987", property="88 Practice Lane", unit="2A", enrollment="11/15/2025", move_in="12/01/2025"),
    profile(name="Jasmine Morales", first_name="Jasmine", last_name="Morales", hmis_id="H-TRAIN-0003", dob="05/09/1990", property="1415 Harbor View Avenue", unit="2A", landlord="Harbor View Training LLC", landlord_contact="Avery Collins"),
    profile(name="Jasmine Morales", first_name="Jasmine", last_name="Morales", hmis_id="H-TRAIN-0004", dob="11/30/1996", property="908 Learning Court", unit="3C", landlord="Learning Court Training LLC", landlord_contact="Avery Collins"),
    profile(name="Morgan Lee", first_name="Morgan", last_name="Lee", hmis_id="H-TRAIN-0005", dob="02/18/1991", property="73 Sample Street", unit="1D"),
    profile(name="Casey Reed", first_name="Casey", last_name="Reed", hmis_id="H-TRAIN-0006", dob="02/18/1991", property="73 Sample Street", unit="5A"),
    profile(name="Devin Cross", first_name="Devin", last_name="Cross", hmis_id="H-TRAIN-0007", dob="07/04/1985", property="220 Example Terrace", unit="7B"),
    profile(name="Taylor Quinn", first_name="Taylor", last_name="Quinn", hmis_id="H-TRAIN-0008", dob="12/12/1994", property="17 Mockingbird Way", unit="9F"),
]

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


@dataclass(frozen=True)
class TemplateField:
    """A value location derived from a stable, printed label in a blank PDF.

    These agency forms are flat PDFs: they have printed blanks but no native
    AcroForm widgets.  We therefore anchor each training value to text that is
    actually present in the source template, rather than guessing a page
    coordinate.  If a template revision moves or removes the label, generation
    stops instead of producing a quietly misaligned training record.
    """

    page: int
    label_fragment: str
    offset_x: float
    offset_y: float = 0
    occurrence: int = 0
    size: float = 8


def _text_anchors(page, label_fragment: str) -> list[tuple[float, float]]:
    """Return PDF coordinates for text fragments matching ``label_fragment``."""
    matches: list[tuple[float, float]] = []
    needle = " ".join(label_fragment.lower().split())

    def visitor(text, _cm, tm, _font_dict, _font_size) -> None:
        rendered = " ".join((text or "").lower().split())
        if needle and needle in rendered:
            matches.append((float(tm[4]), float(tm[5])))

    page.extract_text(visitor_text=visitor)
    return matches


def resolve_template_field(page, field: TemplateField, *, field_name: str, page_index: int) -> tuple[float, float, float]:
    """Resolve a named template field or fail loudly when the template changed."""
    if field.page != page_index:
        raise ValueError(f"Field {field_name!r} was requested on page {page_index + 1}, expected page {field.page + 1}.")
    anchors = _text_anchors(page, field.label_fragment)
    if len(anchors) <= field.occurrence:
        raise ValueError(
            f"Could not map training field {field_name!r}: label fragment "
            f"{field.label_fragment!r} was not found on page {page_index + 1}."
        )
    x, y = anchors[field.occurrence]
    return x + field.offset_x, y + field.offset_y, field.size


def resolve_widget_field(page, field_name: str, *, page_index: int) -> tuple[float, float, float, float]:
    """Locate a true AcroForm widget when a source PDF provides one.

    A few templates (currently the CFA request) do contain real widgets.  We
    use their rectangles directly rather than recreating an approximation from
    label text.  Flat PDFs use ``TemplateField`` above.
    """
    for annotation_ref in page.get("/Annots", []):
        annotation = annotation_ref.get_object()
        parent_ref = annotation.get("/Parent")
        parent = parent_ref.get_object() if parent_ref else annotation
        name = str(parent.get("/T") or annotation.get("/T") or "")
        if name != field_name:
            continue
        left, bottom, right, top = (float(value) for value in annotation["/Rect"])
        return left, bottom, right, top
    raise ValueError(f"Could not map AcroForm widget {field_name!r} on page {page_index + 1}.")


# Field map for Form 1080.  Values are tied to printed label positions, not a
# guessed absolute page coordinate.  The "Other" occurrence is deliberately
# the first one: it is the program field, not the later housing-status field.
RECERTIFICATION_FIELD_MAP = {
    "participant_first_name": TemplateField(0, "irst Name", 49),
    "participant_last_name": TemplateField(0, "ast Name", 44),
    "hmis_id": TemplateField(0, "HMIS ID:", 55),
    "recertification_date": TemplateField(0, "ate of Recertification", 95),
    "annual_recertification": TemplateField(0, "Annual Recertification", -16),
    "program_other": TemplateField(0, "Other: __", 42),
    "program_enrollment_date": TemplateField(0, "Program Enrollment Date:", 143),
    "months_enrolled": TemplateField(0, "Number of Months Enrolled in Program:", 215),
}


# The first three Quarterly pages carry the identity and financial facts that
# Homesteader is expected to read.  Map those facts to the source labels so the
# training corpus tests document understanding rather than bad PDF geometry.
QUARTERLY_FIELD_MAP = {
    "monthly_participant_name": TemplateField(0, "Participant Name:", 89),
    "monthly_hmis_id": TemplateField(0, "HMIS ID:", 45),
    "monthly_meeting_date": TemplateField(0, "Monthly Meeting Date:", 99),
    "monthly_meeting_time": TemplateField(0, "Monthly Meeting Date:", 366),
    "monthly_meeting_location": TemplateField(0, "Monthly Meeting Location:", 118),
    "monthly_category": TemplateField(0, "CATEGORY", 8, -31),
    "monthly_goals": TemplateField(0, "GOALS", 5, -31),
    "monthly_status": TemplateField(0, "STATUS:", 5, -31),
    "income_participant_name": TemplateField(1, "articipant Name", 74),
    "income_dob": TemplateField(1, "Date of Birth", 59),
    "income_hmis_id": TemplateField(1, "HMIS #:", 40),
    "income_source_1": TemplateField(1, "Source: ______________________", 108),
    "income_amount_1": TemplateField(1, "Amount: ___________", 59),
    "income_frequency_1": TemplateField(1, "Frequency: _____", 56),
}


CFA_FIELD_MAP = {
    "check_needed_by": TemplateField(0, "Check Needed by:", 128),
    "vendor_name": TemplateField(0, "Vendor Name:", 104),
    "vendor_address": TemplateField(0, "Vendor Address:", 118),
    "assistance_amount": TemplateField(0, "Amount:", 67),
    "memo": TemplateField(0, "Memo (if necessary):", 113),
}


INTAKE_FIELD_MAP = {
    "participant_name": TemplateField(7, "Name:________________________________", 45),
    "participant_hmis_id": TemplateField(7, "ID", 29),
    "participant_dob": TemplateField(7, "Birth:", 50),
    "participant_phone": TemplateField(7, "ell:", 20),
    "participant_email": TemplateField(7, "Email:", 34),
}


# The landlord packet is a single 13-page source containing several logical
# forms.  These are the fields that establish the move-in relationship, so
# they must be tied to the labels printed on each individual form.  In
# particular, the W-9 is intentionally filled only with the fictional payee
# information; participant and tenancy facts appear on the pages that actually
# ask for them.  That keeps the visible evidence and extracted relationships in
# agreement.
LANDLORD_FIELD_MAP = {
    # W-9: vendor/payee evidence only.
    "w9_legal_name": TemplateField(0, "Name (as shown", 0, -12),
    "w9_business_name": TemplateField(0, "Business name", 0, -12),
    "w9_address": TemplateField(0, "Address (number", 0, -12),
    "w9_city_state_zip": TemplateField(0, "City, state", 0, -12),
    "w9_signature": TemplateField(0, "Signature of", 42, -7),
    "w9_date": TemplateField(0, "Date", 22, -7),
    # Landlord Rental Assistance Acknowledgement (PDF page 7).
    "ack_date": TemplateField(6, "Date:", 35, -9),
    "ack_tenant": TemplateField(6, "Tenant", 85, -9),
    "ack_phone": TemplateField(6, "Phone:_", 35, -9),
    "ack_landlord": TemplateField(6, "Landlord/Property", 118, -9),
    "ack_management": TemplateField(6, "Management Company", 146, -9),
    "ack_owner_phone": TemplateField(6, "Phone:", 40, -9, occurrence=1),
    "ack_owner_email": TemplateField(6, "Email:", 38, -9),
    "ack_property": TemplateField(6, "Property", 100, -9, occurrence=1),
    "ack_city": TemplateField(6, "City:", 34, -9),
    "ack_state": TemplateField(6, "State:", 36, -9),
    "ack_zip": TemplateField(6, "Zip", 72, -9),
    "ack_rent": TemplateField(6, "TENANT’S MONTHLY RENTAL AMOUNT", 185, -9),
    "ack_due_day": TemplateField(6, "DUE", 42, -9),
    "ack_mailing_address": TemplateField(6, "Mailing", 62, -9),
    "ack_owner_name": TemplateField(6, "Owner’s", 100, -9, occurrence=0),
    "ack_owner_signature": TemplateField(6, "Owner’s", 300, -9, occurrence=0),
    "ack_signature_date": TemplateField(6, "Date:", 30, -9, occurrence=1),
    # Unit Information and Owner Certifications (PDF page 8).
    "unit_tenant": TemplateField(7, "Tenant/Client", 78, -9),
    "unit_address": TemplateField(7, "Property", 100, -9),
    "unit_number": TemplateField(7, "Apartment", 75, -9),
    "unit_city": TemplateField(7, "City:", 34, -9),
    "unit_state": TemplateField(7, "State:", 36, -9),
    "unit_zip": TemplateField(7, "Zip", 72, -9),
    "unit_rent": TemplateField(7, "Requested", 95, -9),
    "unit_deposit": TemplateField(7, "Security", 85, -9),
    "unit_move_in": TemplateField(7, "Date Available", 122, -9),
    "unit_owner": TemplateField(7, "Name of Legal Owner", 105, -9),
    "unit_owner_address": TemplateField(7, "Owner Address", 95, -9),
    "unit_owner_phone": TemplateField(7, "Phone:", 40, -9),
    "unit_owner_email": TemplateField(7, "Email:", 36, -9),
    # Landlord Incentive Fee Agreement (PDF page 10).
    "incentive_participant": TemplateField(9, "Participant Name", 80, 0),
    "incentive_landlord": TemplateField(9, "Name of Landlord", -22, 10),
    "incentive_applicant": TemplateField(9, "Name of Applicant", -225, 10),
    "incentive_address": TemplateField(9, "The property is located at", 116, 0),
    "incentive_unit": TemplateField(9, "Unit #/Apt #", -40, 10),
    "incentive_city": TemplateField(9, "(City)", -125, 10),
    "incentive_zip": TemplateField(9, "(Zip Code)", -90, 10),
    "incentive_rent": TemplateField(9, "Monthly Rent: $", 70, 0),
    "incentive_deposit": TemplateField(9, "Security Deposit: $", 83, 0),
    "incentive_move_month": TemplateField(9, "In Date:", 40, 0),
    "incentive_move_day": TemplateField(9, "In Date:", 84, 0),
    "incentive_move_year": TemplateField(9, "In Date:", 127, 0),
    "incentive_payee": TemplateField(9, "Please make checks payable", 140, 0),
    "incentive_landlord_name": TemplateField(9, "Landlord/ Property Management Name", 175, 0),
    "incentive_phone": TemplateField(9, "Telephone Number", 90, 0),
    "incentive_email": TemplateField(9, "mail Address", 72, 0),
    "incentive_signature": TemplateField(9, "Landlord/ Property Manager Signature", 175, 0),
    "incentive_date": TemplateField(9, "Date:", 30, 0, occurrence=1),
    # Move-In Assistance Request (PDF page 11).
    "move_participant": TemplateField(10, "PARTICIPANT", 105, 0),
    "move_hmis_id": TemplateField(10, "HMIS#:", 45, 0),
    "move_landlord": TemplateField(10, "Name of Landlord", -25, 10),
    "move_applicant": TemplateField(10, "Applicant’s Full Name", -74, 10),
    "move_address": TemplateField(10, "The property is located at", 123, 0),
    "move_unit": TemplateField(10, "(Unit #/Apt #)", -55, 10),
    "move_city": TemplateField(10, "(City)", -125, 10),
    "move_zip": TemplateField(10, "(Zip Code)", -90, 10),
    "move_rent": TemplateField(10, "Monthly Rent: $", 74, 0),
    "move_deposit": TemplateField(10, "Security Deposit: $", 88, 0),
    "move_month": TemplateField(10, "In Date:", 40, 0),
    "move_day": TemplateField(10, "In Date:", 84, 0),
    "move_year": TemplateField(10, "In Date:", 127, 0),
    "move_payee": TemplateField(10, "Please make checks payable", 145, 0),
    "move_landlord_name": TemplateField(10, "Landlord/ Property Management Name", 190, 0),
    "move_phone": TemplateField(10, "Telephone Number", 95, 0),
    "move_email": TemplateField(10, "mail Address", 78, 0),
    "move_signature": TemplateField(10, "Landlord/ Property Manager Signature", 185, 0),
    "move_signature_date": TemplateField(10, "Date:", 32, 0, occurrence=1),
    # Habitability property information (PDF page 12) and certification (page 13).
    "habitability_address": TemplateField(11, "Street Address", 75, 0),
    "habitability_unit": TemplateField(11, "Unit/Apt #", 55, 0),
    "habitability_city": TemplateField(11, "City:", 28, 0),
    "habitability_state": TemplateField(11, "State:", 28, 0),
    "habitability_zip": TemplateField(11, "Zip Code", 44, 0),
    "habitability_comment": TemplateField(12, "Comments:", 0, -18),
    "habitability_agency": TemplateField(12, "Certifying Agency", 100, 0),
    "habitability_staff": TemplateField(12, "Staff Name", 75, 0),
    "habitability_staff_title": TemplateField(12, "Staff Title", 63, 0),
    "habitability_staff_signature": TemplateField(12, "Staff Signature", 110, 0),
    "habitability_staff_date": TemplateField(12, "Date Completed", 80, 0, occurrence=0),
    "habitability_supervisor": TemplateField(12, "Supervisor Name", 95, 0),
    "habitability_supervisor_title": TemplateField(12, "Supervisor Title", 90, 0),
    "habitability_supervisor_signature": TemplateField(12, "Supervisor Signature", 125, 0),
    "habitability_supervisor_date": TemplateField(12, "Date Completed", 80, 0, occurrence=1),
    "habitability_household_head": TemplateField(12, "Name of Head of Household", 145, 0),
}


def overlay_pdf(
    source: Path,
    destination: Path,
    placements: dict[int, list[tuple]],
    *,
    field_map: dict[str, TemplateField] | None = None,
) -> None:
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
            elif kind == "field":
                if field_map is None:
                    raise ValueError(f"No template field map was supplied for {values[0]!r}.")
                field_name, text = values
                field = field_map.get(field_name)
                if field is None:
                    raise ValueError(f"Unknown mapped training field {field_name!r}.")
                x, y, size = resolve_template_field(original_page, field, field_name=field_name, page_index=index)
                draw_text(layer, x, y, text, size)
            elif kind == "field_check":
                if field_map is None:
                    raise ValueError(f"No template field map was supplied for {values[0]!r}.")
                field_name = values[0]
                field = field_map.get(field_name)
                if field is None:
                    raise ValueError(f"Unknown mapped training field {field_name!r}.")
                x, y, _size = resolve_template_field(original_page, field, field_name=field_name, page_index=index)
                draw_check(layer, x, y)
            elif kind == "widget":
                field_name, text = values
                left, bottom, _right, top = resolve_widget_field(original_page, field_name, page_index=index)
                draw_text(layer, left + 3, bottom + max(2, (top - bottom - 8) / 2), text)
            elif kind == "widget_check":
                field_name = values[0]
                left, bottom, right, top = resolve_widget_field(original_page, field_name, page_index=index)
                draw_check(layer, (left + right) / 2 - 3, (bottom + top) / 2 - 3)
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
            ("field", "participant_name", p["name"]), ("field", "participant_hmis_id", p["hmis_id"]),
            ("field", "participant_dob", p["dob"]), ("field", "participant_phone", p["phone"]),
            ("field", "participant_email", p["email"]),
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
        12: [("text", 105, 85, p["name"]), ("text", 325, 85, "01/15/2026"), ("text", 105, 62, f"{p['name']} - TRAINING"), ("text", 325, 62, "01/15/2026"), ("text", 105, 40, "Caseworker Demo - TRAINING"), ("text", 325, 40, "01/15/2026")],
        14: [("text", 98, 168, p["name"]), ("text", 98, 146, p["staff"]), ("text", 330, 146, "01/15/2026"), ("text", 98, 124, f"{p['name']} - TRAINING"), ("text", 330, 124, "01/15/2026"), ("text", 98, 102, "Caseworker Demo - TRAINING"), ("text", 330, 102, "01/15/2026")],
        # Consent, privacy, rights, media and transportation acknowledgement signatures.
        16: [("text", 105, 112, p["name"]), ("text", 105, 90, f"{p['name']} - TRAINING"), ("text", 330, 90, "01/15/2026"), ("text", 105, 68, "Caseworker Demo - TRAINING"), ("text", 330, 68, "01/15/2026")],
        23: [("text", 98, 145, p["name"]), ("text", 98, 122, f"{p['name']} - TRAINING"), ("text", 330, 122, "01/15/2026"), ("text", 98, 99, p["staff"]), ("text", 330, 99, "01/15/2026")],
        24: [("text", 90, 682, p["name"]), ("text", 90, 660, f"{p['name']} - TRAINING"), ("text", 330, 660, "01/15/2026"), ("text", 90, 638, p["staff"]), ("text", 330, 638, "01/15/2026")],
        27: [("text", 95, 194, p["name"]), ("text", 95, 172, f"{p['name']} - TRAINING"), ("text", 330, 172, "01/15/2026")],
        28: [("check", 102, 606), ("text", 95, 570, p["name"]), ("text", 95, 548, f"{p['name']} - TRAINING"), ("text", 330, 548, "01/15/2026"), ("text", 95, 526, p["staff"]), ("text", 330, 526, "01/15/2026")],
        31: [("text", 95, 676, p["name"]), ("text", 95, 654, f"{p['name']} - TRAINING"), ("text", 330, 654, "01/15/2026")],
        32: [("check", 105, 354), ("text", 95, 280, p["name"]), ("text", 95, 258, f"{p['name']} - TRAINING"), ("text", 330, 258, "01/15/2026"), ("text", 95, 236, p["staff"]), ("text", 330, 236, "01/15/2026")],
        33: [("text", 95, 594, p["name"]), ("text", 95, 572, f"{p['name']} - TRAINING"), ("text", 330, 572, "01/15/2026")],
        34: [("check", 102, 510), ("text", 95, 132, p["name"]), ("text", 95, 110, f"{p['name']} - TRAINING"), ("text", 330, 110, "01/15/2026"), ("text", 95, 88, p["staff"]), ("text", 330, 88, "01/15/2026")],
        # Initial income form and budget / asset forms.
        35: [("text", 90, 722, p["name"]), ("text", 340, 722, p["dob"]), ("text", 510, 722, p["hmis_id"]), ("check", 92, 528), ("text", 150, 493, p["income_source"]), ("text", 360, 493, p["income"]), ("text", 490, 493, "Monthly"), ("text", 100, 408, "Training scenario: employer letter unavailable."), ("text", 100, 386, "Fictional data used for Homesteader validation."), ("text", 100, 340, p["staff"]), ("text", 340, 340, "Case Manager"), ("text", 100, 318, "Caseworker Demo - TRAINING"), ("text", 340, 318, "01/15/2026")],
        37: [("text", 140, 716, p["rent"]), ("text", 412, 716, p["income"]), ("text", 140, 690, "$55.00"), ("text", 412, 690, "N/A"), ("text", 140, 664, "$110.00"), ("text", 412, 664, "N/A"), ("text", 140, 638, "$60.00"), ("text", 412, 638, "N/A"), ("text", 410, 102, p["name"])],
        43: [("text", 95, 680, p["name"]), ("text", 470, 680, f"{p['name']} - TRAINING"), ("text", 95, 657, p["staff"]), ("text", 470, 657, "01/15/2026")],
        44: [("text", 95, 651, p["name"]), ("text", 95, 629, "None - fictional training profile"), ("text", 95, 110, f"{p['name']} - TRAINING"), ("text", 330, 110, "01/15/2026")],
        45: [("text", 100, 706, p["name"]), ("text", 100, 678, "Maintain stable housing and build savings."), ("text", 100, 648, "Budget review, landlord communication, employment support."), ("text", 100, 475, p["staff"]), ("text", 330, 475, "01/15/2026")],
        46: [("text", 100, 596, p["name"]), ("text", 100, 570, "Follow up on employment and rent budget."), ("text", 100, 545, "Quarterly financial review completed."), ("text", 100, 520, p["staff"]), ("text", 330, 520, "01/15/2026")],
    }


def quarterly_placements(document_date: str, income: str) -> dict[int, list[tuple]]:
    p = PROFILE
    return {
        0: [
            ("field", "monthly_participant_name", p["name"]),
            ("field", "monthly_hmis_id", p["hmis_id"]),
            ("field", "monthly_meeting_date", document_date),
            ("field", "monthly_meeting_time", "10:00 AM"),
            ("field", "monthly_meeting_location", "Hope the Mission - Training Office"),
            ("field", "monthly_category", "Housing stability"),
            ("field", "monthly_goals", "Maintain rent budget and employment"),
            ("field", "monthly_status", "In progress"),
            ("text", 80, 238, p["name"]), ("text", 270, 238, f"{p['name']} - TRAINING"), ("text", 455, 238, document_date), ("text", 80, 172, p["staff"]), ("text", 270, 172, "Caseworker Demo - TRAINING"), ("text", 455, 172, document_date), ("text", 80, 116, p["supervisor"]), ("text", 270, 116, "Supervisor Demo - TRAINING"), ("text", 455, 116, document_date),
        ],
        1: [
            ("field", "income_participant_name", p["name"]),
            ("field", "income_dob", p["dob"]),
            ("field", "income_hmis_id", p["hmis_id"]),
            ("check", 95, 525),
            ("field", "income_source_1", p["income_source"]),
            ("field", "income_amount_1", income),
            ("field", "income_frequency_1", "Monthly"),
            ("text", 100, 410, "Fictional training profile; source document simulated."), ("text", 100, 388, "No actual participant or financial data used."), ("text", 100, 340, p["staff"]), ("text", 340, 340, "Case Manager"), ("text", 100, 318, "Caseworker Demo - TRAINING"), ("text", 340, 318, document_date),
        ],
        2: [("text", 125, 714, p["rent"]), ("text", 410, 714, income), ("text", 125, 688, "$55.00"), ("text", 125, 662, "$110.00"), ("text", 125, 636, "$60.00"), ("text", 410, 100, p["name"])],
        7: [("text", 105, 706, p["name"]), ("text", 470, 706, f"{p['name']} - TRAINING"), ("text", 105, 683, p["staff"]), ("text", 470, 683, document_date)],
        8: [("text", 100, 625, "Not applicable - documented fictional income above."), ("text", 100, 112, f"{p['name']} - TRAINING"), ("text", 330, 112, document_date)],
    }


def financial_assistance_placements(document_date: str) -> dict[int, list[tuple]]:
    p = PROFILE
    return {0: [
        ("widget", "Date of Request", document_date),
        ("widget", "Program", p["program"]),
        ("widget", "Must be from approved program name ndexCl i ent Name", p["name"]),
        ("widget_check", "Rental Ass"),
        ("field", "check_needed_by", document_date),
        ("field", "vendor_name", p["landlord"]),
        ("field", "vendor_address", "123 Fictional Way, Example City, CA 00000"),
        ("field", "assistance_amount", "$1,000.00"),
        ("field", "memo", "February 2026 rental assistance for fictional training profile."),
        ("widget", "HOTV STAFF Pr i ntRow1", p["staff"]),
        ("widget", "Signature77", "Caseworker Demo - TRAINING"),
        ("widget", "DateRow1", document_date),
    ]}


def landlord_placements() -> dict[int, list[tuple]]:
    p = PROFILE
    move_month, move_day, move_year = p["move_in"].split("/")
    return {
        # W-9: payee evidence only, never participant facts.
        0: [("field", "w9_legal_name", p["landlord"]), ("field", "w9_business_name", p["landlord"]), ("field", "w9_address", "123 Fictional Way"), ("field", "w9_city_state_zip", "Example City, CA 00000"), ("field", "w9_signature", f"{p['landlord_contact']} - TRAINING"), ("field", "w9_date", "01/28/2026")],
        # Landlord acknowledgement and unit certification.
        6: [("field", "ack_date", "01/28/2026"), ("field", "ack_tenant", p["name"]), ("field", "ack_phone", p["phone"]), ("field", "ack_landlord", p["landlord"]), ("field", "ack_management", p["landlord"]), ("field", "ack_owner_phone", "555-0120"), ("field", "ack_owner_email", "leasing@example.invalid"), ("field", "ack_property", p["property"]), ("field", "ack_city", p["city"]), ("field", "ack_state", "CA"), ("field", "ack_zip", p["zip"]), ("field", "ack_rent", p["rent"]), ("field", "ack_due_day", "1st"), ("field", "ack_mailing_address", "123 Fictional Way"), ("field", "ack_owner_name", p["landlord"]), ("field", "ack_owner_signature", f"{p['landlord_contact']} - TRAINING"), ("field", "ack_signature_date", "01/28/2026")],
        7: [("field", "unit_tenant", p["name"]), ("field", "unit_address", p["property"]), ("field", "unit_number", p["unit"]), ("field", "unit_city", p["city"]), ("field", "unit_state", "CA"), ("field", "unit_zip", p["zip"]), ("field", "unit_rent", p["rent"]), ("field", "unit_deposit", p["deposit"]), ("field", "unit_move_in", p["move_in"]), ("field", "unit_owner", p["landlord"]), ("field", "unit_owner_address", "123 Fictional Way"), ("field", "unit_owner_phone", "555-0120"), ("field", "unit_owner_email", "leasing@example.invalid")],
        # Landlord incentive and move-in assistance forms use the same facts,
        # each in the field where that form actually requests it.
        9: [("field", "incentive_participant", p["name"]), ("field", "incentive_landlord", p["landlord"]), ("field", "incentive_applicant", p["name"]), ("field", "incentive_address", p["property"]), ("field", "incentive_unit", p["unit"]), ("field", "incentive_city", p["city"]), ("field", "incentive_zip", p["zip"]), ("field", "incentive_rent", p["rent"]), ("field", "incentive_deposit", p["deposit"]), ("field", "incentive_move_month", move_month), ("field", "incentive_move_day", move_day), ("field", "incentive_move_year", move_year), ("field", "incentive_payee", p["landlord"]), ("field", "incentive_landlord_name", p["landlord"]), ("field", "incentive_phone", "555-0120"), ("field", "incentive_email", "leasing@example.invalid"), ("field", "incentive_signature", f"{p['landlord_contact']} - TRAINING"), ("field", "incentive_date", "01/28/2026")],
        10: [("field", "move_participant", p["name"]), ("field", "move_hmis_id", p["hmis_id"]), ("field", "move_landlord", p["landlord"]), ("field", "move_applicant", p["name"]), ("field", "move_address", p["property"]), ("field", "move_unit", p["unit"]), ("field", "move_city", p["city"]), ("field", "move_zip", p["zip"]), ("field", "move_rent", p["rent"]), ("field", "move_deposit", p["deposit"]), ("field", "move_month", move_month), ("field", "move_day", move_day), ("field", "move_year", move_year), ("field", "move_payee", p["landlord"]), ("field", "move_landlord_name", p["landlord"]), ("field", "move_phone", "555-0120"), ("field", "move_email", "leasing@example.invalid"), ("field", "move_signature", f"{p['landlord_contact']} - TRAINING"), ("field", "move_signature_date", "01/28/2026")],
        # Habitability property information and its certification page.
        11: [("field", "habitability_address", p["property"]), ("field", "habitability_unit", p["unit"]), ("field", "habitability_city", p["city"]), ("field", "habitability_state", "CA"), ("field", "habitability_zip", p["zip"]), ("check", 139, 612), ("check", 500, 493), ("check", 500, 467), ("check", 500, 436), ("check", 500, 405), ("check", 500, 370), ("check", 500, 336), ("check", 500, 302), ("check", 500, 267), ("check", 500, 236), ("check", 500, 143)],
        12: [("check", 44, 630), ("check", 44, 549), ("field", "habitability_comment", "Fictional training inspection: property meets all standards."), ("field", "habitability_agency", "Hope the Mission - Training"), ("field", "habitability_staff", p["staff"]), ("field", "habitability_staff_title", "Case Manager"), ("field", "habitability_staff_signature", "Caseworker Demo - TRAINING"), ("field", "habitability_staff_date", "01/28/2026"), ("field", "habitability_supervisor", p["supervisor"]), ("field", "habitability_supervisor_title", "Supervisor"), ("field", "habitability_supervisor_signature", "Supervisor Demo - TRAINING"), ("field", "habitability_supervisor_date", "01/28/2026"), ("field", "habitability_household_head", p["name"])],
    }


def recertification_placements(document_date: str) -> dict[int, list[tuple]]:
    p = PROFILE
    return {
        0: [
            ("field", "participant_first_name", p["first_name"]),
            ("field", "participant_last_name", p["last_name"]),
            ("field", "hmis_id", p["hmis_id"]),
            ("field", "recertification_date", document_date),
            ("field_check", "annual_recertification"),
            ("field", "program_other", p["program"]),
            ("field", "program_enrollment_date", p["enrollment"]),
            ("field", "months_enrolled", "12"),
        ],
        1: [("check", 105, 678), ("check", 105, 654), ("check", 105, 508), ("check", 105, 486), ("check", 105, 440), ("check", 105, 342), ("text", 105, 220, p["staff"]), ("text", 305, 220, "Caseworker Demo - TRAINING"), ("text", 490, 220, document_date), ("text", 105, 196, p["supervisor"]), ("text", 305, 196, "Supervisor Demo - TRAINING"), ("text", 490, 196, document_date)],
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


def build_profile(template: Path, output: Path, current_profile: dict[str, str]) -> dict[str, Path]:
    """Create one self-contained fictional profile and return its source copies."""
    global PROFILE
    PROFILE = current_profile
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "intake": output / f"TRAINING_01_TLS_Intake_Packet_{PROFILE['hmis_id']}.pdf",
        "cfa_february": output / f"TRAINING_01_CFA_2026-02_{PROFILE['hmis_id']}.pdf",
        "cfa_march": output / f"TRAINING_01_CFA_2026-03_{PROFILE['hmis_id']}.pdf",
        "move_in": output / f"TRAINING_01_Move_In_and_Landlord_Docs_{PROFILE['hmis_id']}.pdf",
        "quarterly_march": output / f"TRAINING_01_Quarterly_2026-03_{PROFILE['hmis_id']}.pdf",
        "quarterly_june": output / f"TRAINING_01_Quarterly_2026-06_{PROFILE['hmis_id']}.pdf",
        "recertification": output / f"TRAINING_01_Recertification_2027-01_{PROFILE['hmis_id']}.pdf",
    }
    overlay_pdf(template / "01. TLS Intake Packet.pdf", files["intake"], intake_placements(), field_map=INTAKE_FIELD_MAP)
    overlay_pdf(template / "BLANK Financial Assistance Request.pdf", files["cfa_february"], financial_assistance_placements("02/08/2026"), field_map=CFA_FIELD_MAP)
    overlay_pdf(template / "BLANK Financial Assistance Request.pdf", files["cfa_march"], financial_assistance_placements("03/08/2026"), field_map=CFA_FIELD_MAP)
    overlay_pdf(
        template / "00. Landlord Docs.pdf",
        files["move_in"],
        landlord_placements(),
        field_map=LANDLORD_FIELD_MAP,
    )
    overlay_pdf(template / "BLANK Quarterly.pdf", files["quarterly_march"], quarterly_placements("03/08/2026", "$2,380.00"), field_map=QUARTERLY_FIELD_MAP)
    overlay_pdf(template / "BLANK Quarterly.pdf", files["quarterly_june"], quarterly_placements("06/08/2026", "$2,520.00"), field_map=QUARTERLY_FIELD_MAP)
    overlay_pdf(
        template / "BLANK Recertification form.pdf",
        files["recertification"],
        recertification_placements("01/15/2027"),
        field_map=RECERTIFICATION_FIELD_MAP,
    )
    write_manifest(output)
    return files


def copy_as(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def build_hateful_eight(template: Path, output: Path) -> None:
    """Build independent adversarial upload batches for a clean Homesteader state."""
    global PROFILE
    root = output / "HATEFUL_EIGHT_FICTIONAL_TRAINING_V3_MAPPED"
    profiles_root = root / "00_PROFILE_SOURCES"
    profile_files: list[tuple[dict[str, str], dict[str, Path]]] = []
    for number, current in enumerate(HATEFUL_EIGHT, start=1):
        folder = profiles_root / f"{number:02d}_{current['hmis_id']}_{current['name'].replace(' ', '_')}"
        profile_files.append((current, build_profile(template, folder, current)))

    # Run 1: all complete records, deliberately shuffled and without client folders.
    full = root / "01_FULL_MIXED_UPLOAD"
    all_sources = [file for _, files in profile_files for file in files.values()]
    random.Random(8).shuffle(all_sources)
    for index, source in enumerate(all_sources, start=1):
        copy_as(source, full / f"{index:02d}_MIXED_{source.name}")

    # Run 2: incomplete and out-of-order records. Start Homesteader with a new blank state.
    partial = root / "02_PARTIAL_OUT_OF_ORDER_UPLOAD"
    partial_map = {
        "H-TRAIN-0001": ("intake", "cfa_february"),
        "H-TRAIN-0002": ("quarterly_june",),  # historical baseline arrives before intake
        "H-TRAIN-0003": ("move_in",),         # first Jasmine: housing material only
        "H-TRAIN-0004": ("quarterly_march",),  # second Jasmine: same name, distinct HMIS
        "H-TRAIN-0005": ("recertification",),  # shares DOB with Casey, different person
        "H-TRAIN-0006": ("cfa_march",),
        "H-TRAIN-0007": ("quarterly_march",), # followed by a completed revision below
        "H-TRAIN-0008": ("move_in", "cfa_february"),
    }
    partial_sources: list[Path] = []
    for current, files in profile_files:
        partial_sources.extend(files[key] for key in partial_map[current["hmis_id"]])
    random.Random(81).shuffle(partial_sources)
    for index, source in enumerate(partial_sources, start=1):
        copy_as(source, partial / f"{index:02d}_PARTIAL_{source.name}")

    # A deliberately incomplete quarterly revision for Devin: same person and period, no HMIS ID.
    devin = next(current for current in HATEFUL_EIGHT if current["hmis_id"] == "H-TRAIN-0007")
    incomplete = devin | {"hmis_id": ""}
    PROFILE = incomplete
    incomplete_path = partial / "99_PARTIAL_Quarterly_2026-03_Devin_Cross_MISSING_HMIS.pdf"
    overlay_pdf(template / "BLANK Quarterly.pdf", incomplete_path, quarterly_placements("03/08/2026", "$2,380.00"), field_map=QUARTERLY_FIELD_MAP)

    # Run 3: the missing records and completed revision arrive later. Originals remain in Run 2.
    follow_up = root / "03_CORRECTION_AND_MISSING_RECORD_FOLLOW_UP"
    for current, files in profile_files:
        for key, source in files.items():
            if key not in partial_map[current["hmis_id"]]:
                copy_as(source, follow_up / f"FOLLOW_UP_{source.name}")
    devin_full = next(files["quarterly_march"] for current, files in profile_files if current["hmis_id"] == "H-TRAIN-0007")
    copy_as(devin_full, follow_up / "COMPLETED_REVISION_Quarterly_2026-03_Devin_Cross_WITH_HMIS.pdf")

    # Run 4: true repeats, intentionally exact-byte copies, for raw-hash dedupe verification.
    duplicates = root / "04_EXACT_DUPLICATE_UPLOADS"
    for current, files in profile_files:
        source = files["quarterly_june"]
        copy_as(source, duplicates / f"DUPLICATE_{current['hmis_id']}_A.pdf")
        copy_as(source, duplicates / f"DUPLICATE_{current['hmis_id']}_B.pdf")

    (root / "README_TEST_RUNS.txt").write_text(
        "FICTIONAL TRAINING DATA — NOT FOR SUBMISSION\n\n"
        "Use a fresh Homesteader state for each numbered run.\n"
        "01_FULL_MIXED_UPLOAD: complete records, shuffled; verify separation and relationship graph.\n"
        "02_PARTIAL_OUT_OF_ORDER_UPLOAD: incomplete, out of order; verify review, missing-record, and schedule findings.\n"
        "03_CORRECTION_AND_MISSING_RECORD_FOLLOW_UP: ingest after run 02; verify additions and completed-revision proposals.\n"
        "04_EXACT_DUPLICATE_UPLOADS: ingest after the relevant source documents; verify raw-hash duplicate review.\n\n"
        "Identity stress cases:\n"
        "- Jasmine Morales H-TRAIN-0003 (DOB 05/09/1990) and H-TRAIN-0004 (DOB 11/30/1996).\n"
        "- Morgan Lee H-TRAIN-0005 and Casey Reed H-TRAIN-0006 share DOB 02/18/1991.\n"
        "- Devin Cross has an incomplete quarterly form followed by the completed version.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--hateful-eight", action="store_true", help="Create eight fictional profiles and adversarial upload batches.")
    args = parser.parse_args()
    template = args.template_dir
    output = args.output_dir
    if args.hateful_eight:
        build_hateful_eight(template, output)
        print(output / "HATEFUL_EIGHT_FICTIONAL_TRAINING_V3_MAPPED")
    else:
        build_profile(template, output, PROFILE)
        print(output)


if __name__ == "__main__":
    main()
