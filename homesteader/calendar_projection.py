"""A local, one-way calendar projection of program schedule obligations.

This intentionally knows nothing about Google Calendar or any other network
service.  It turns locally derived schedule rows into display/export events.
An operator may import the resulting ``.ics`` copy wherever their organization
permits; Homesteader never receives calendar credentials or database access.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
from uuid import uuid5, NAMESPACE_URL


EXPORTABLE_STATUSES = frozenset({"due", "upcoming"})


def _safe_text(value: str) -> str:
    """Escape the small RFC 5545 subset used in local calendar exports."""
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "schedule"


def schedule_calendar_events(
    schedule_rows: list[dict], *, include_documented: bool = True, include_participant: bool = True,
) -> list[dict]:
    """Project schedule rows into display-friendly, source-free calendar events.

    Month-precision obligations occupy the whole month. Day-precision
    obligations (currently the CFA) occupy one all-day event.  The source
    document list and relationship graph are deliberately not copied here.
    """
    events: list[dict] = []
    for row in schedule_rows:
        if not include_documented and row.get("status") == "documented":
            continue
        start = date.fromisoformat(row["period_start"] if row.get("due_precision") == "month" else row["due_date"])
        end = date.fromisoformat(row["period_end"]) if row.get("due_precision") == "month" else start + timedelta(days=1)
        participant = row.get("ptc", "Participant")
        identifier = row.get("participant_identifier", "")
        identity = participant if include_participant else "Participant"
        if include_participant and identifier:
            identity += f" · {identifier}"
        status = row.get("status", "").replace("_", " ").title()
        fingerprint = "|".join((row.get("person_id", ""), row.get("requirement_key", ""), row.get("period_start", "")))
        events.append({
            "id": str(uuid5(NAMESPACE_URL, f"homesteader-calendar:{fingerprint}")),
            "start": start,
            "end": end,
            "all_day": True,
            "status": row.get("status", ""),
            "title": f"{identity} — {row.get('requirement', 'Program requirement').title()}",
            "detail": f"{status} · {row.get('program', 'Program')} · local Homesteader schedule",
            "requirement": row.get("requirement", ""),
            "person_id": row.get("person_id", ""),
            "participant": participant,
            "participant_identifier": identifier,
            "period_start": row.get("period_start", ""),
            "period_end": row.get("period_end", ""),
        })
    return sorted(events, key=lambda item: (item["start"], item["title"].casefold()))


def export_ics(events: list[dict], destination: Path) -> Path:
    """Write an importable calendar copy without contacting any calendar API."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Homesteader//Local Schedule Projection//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Homesteader schedule copy",
        "X-WR-CALDESC:One-way export from a local Homesteader workspace.",
    ]
    for event in events:
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{event['id']}@homesteader.local",
            f"DTSTAMP:{timestamp}",
            f"DTSTART;VALUE=DATE:{event['start'].strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{event['end'].strftime('%Y%m%d')}",
            f"SUMMARY:{_safe_text(event['title'])}",
            f"DESCRIPTION:{_safe_text(event['detail'])}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    destination.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return destination
