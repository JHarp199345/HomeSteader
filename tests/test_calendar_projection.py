"""Regression tests for the local schedule view and one-way calendar copy."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from homesteader.calendar_projection import EXPORTABLE_STATUSES, export_ics, schedule_calendar_events
from homesteader.core import HomesteaderStore


class CalendarProjectionTests(unittest.TestCase):
    def _row(self, **changes: object) -> dict:
        base = {
            "person_id": "person-a",
            "ptc": "Jasmine Morales",
            "participant_identifier": "H-000042",
            "program": "TLS Adult SPA 2",
            "requirement_key": "monthly_cfa",
            "requirement": "client financial assistance request (CFA)",
            "period_start": "2026-04-01",
            "period_end": "2026-05-01",
            "due_date": "2026-04-10",
            "due_precision": "day",
            "status": "upcoming",
        }
        return base | changes

    def test_same_name_files_get_separate_stable_calendar_events(self):
        first = self._row()
        second = self._row(person_id="person-b", participant_identifier="H-000043")

        first_run = schedule_calendar_events([first, second])
        second_run = schedule_calendar_events([second, first])

        self.assertEqual(len({event["id"] for event in first_run}), 2)
        self.assertEqual(
            {event["id"] for event in first_run}, {event["id"] for event in second_run},
        )
        self.assertTrue(all("Jasmine Morales" in event["title"] for event in first_run))
        self.assertEqual({event["participant_identifier"] for event in first_run}, {"H-000042", "H-000043"})

    def test_month_precision_event_spans_exactly_one_calendar_month(self):
        event = schedule_calendar_events([self._row(
            requirement_key="quarterly_income_verification",
            requirement="quarterly income eligibility / verification",
            due_date="2026-06-01", due_precision="month",
            period_start="2026-06-01", period_end="2026-07-01",
        )])[0]

        self.assertEqual(event["start"], date(2026, 6, 1))
        self.assertEqual(event["end"], date(2026, 7, 1))

    def test_export_copy_excludes_documented_items_and_source_record_data(self):
        rows = [
            self._row(status="documented"),
            self._row(person_id="person-b", participant_identifier="H-000043", status="due"),
        ]
        export_events = [
            event for event in schedule_calendar_events(rows, include_documented=False)
            if event["status"] in EXPORTABLE_STATUSES
        ]
        self.assertEqual(len(export_events), 1)
        self.assertEqual(export_events[0]["status"], "due")
        self.assertNotIn("stored_source_path", export_events[0])
        self.assertNotIn("evidence_document_ids", export_events[0])

    def test_ics_escapes_text_and_uses_all_day_exclusive_end_dates(self):
        event = schedule_calendar_events([self._row(
            ptc="Jasmine, Morales; Test",
            requirement="CFA\\follow-up",
        )])[0]
        with tempfile.TemporaryDirectory() as directory:
            output = export_ics([event], Path(directory) / "schedule.ics")
            data = output.read_bytes()
            content = data.decode("utf-8")

        self.assertIn(b"\r\n", data)
        self.assertIn("DTSTART;VALUE=DATE:20260410", content)
        self.assertIn("DTEND;VALUE=DATE:20260411", content)
        self.assertIn("Jasmine\\, Morales\\; Test", content)
        self.assertIn("Cfa\\\\Follow-Up", content)

    def test_future_projection_is_upcoming_without_creating_a_missing_finding(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            enrollment = folder / "enrollment.txt"
            enrollment.write_text("""PROGRAM ENROLLMENT
Participant: Jasmine Morales
HMIS number: H-000042
Program: TLS Adult SPA 2
Enrollment date: 2026-01-10
""")
            store = HomesteaderStore(folder / "state.json")
            store.ingest(enrollment)

            rows = store.housing_schedule_status(as_of=date(2026, 3, 11), through=date(2026, 6, 30))
            june_quarter = next(row for row in rows if row["requirement_key"] == "quarterly_income_verification" and row["period_start"] == "2026-06-01")
            june_cfa = next(row for row in rows if row["requirement_key"] == "monthly_cfa" and row["period_start"] == "2026-06-01")

            self.assertEqual(june_quarter["status"], "due")
            self.assertEqual(june_cfa["status"], "upcoming")


if __name__ == "__main__":
    unittest.main()
