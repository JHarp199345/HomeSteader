import tempfile
import unittest
from datetime import date
from pathlib import Path

from homesteader.core import HomesteaderStore


ROOT = Path(__file__).resolve().parents[1]


class CorrectionAuditTests(unittest.TestCase):
    def test_correction_findings_name_the_ptc_error_and_recommendation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HomesteaderStore(Path(directory) / "state.json")
            person = store.create_temporary_file("Jasmine Morales")
            result = store.ingest(ROOT / "fixtures/completed_consent_missing_participant.txt")

            rows = store.correction_findings()

            temporary = next(row for row in rows if row["category"] == "Temporary Identity")
            review = next(row for row in rows if row["document_id"] == result["document_id"])
            self.assertEqual(temporary["ptc"], "Jasmine Morales")
            self.assertIn("HMIS", temporary["recommendation"])
            self.assertEqual(review["source"], "Homesteader review queue")
            self.assertTrue(review["recommendation"])

    def test_tls_schedule_flags_missing_quarter_but_not_due_diligence(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = HomesteaderStore(folder / "state.json")
            enrollment = folder / "enrollment.txt"
            enrollment.write_text("""PROGRAM ENROLLMENT
Participant: Jasmine Morales
HMIS number: H-000042
Program: TLS Adult SPA 2
Enrollment date: 2026-01-10
""")
            initial = folder / "initial.txt"
            initial.write_text("""INCOME VERIFICATION
Participant: Jasmine Morales
HMIS ID: H-000042
Document date: 2026-01-15
Reporting period: Initial enrollment - January 2026
""")
            store.ingest(enrollment)
            store.ingest(initial)

            statuses = store.housing_schedule_status(as_of=date(2026, 4, 11))
            self.assertEqual([item["status"] for item in statuses], ["documented", "missing"])
            self.assertEqual(statuses[0]["standard_end_date"], "2028-01-10")
            self.assertFalse(any("due diligence" in item["requirement"].casefold() for item in statuses))
            self.assertTrue(any(row["category"] == "Scheduled Record Missing" for row in store.correction_findings()))

    def test_completed_copy_is_a_revision_proposal_not_a_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = HomesteaderStore(folder / "state.json")
            incomplete = folder / "incomplete.txt"
            incomplete.write_text("""INCOME VERIFICATION
Participant: Jasmine Morales
HMIS ID: H-000042
Document date: 2026-04-15
Reporting period: Quarterly recertification - April 2026
""")
            completed = folder / "completed.txt"
            completed.write_text("""INCOME VERIFICATION
Participant: Jasmine Morales
HMIS ID: H-000042
Program: TLS Adult SPA 2
Document date: 2026-04-15
Enrollment date: 2024-01-10
Reporting period: Quarterly recertification - April 2026
""")
            original = store.ingest(incomplete)
            revision = store.ingest(completed)
            review = next(item for item in store.pending_reviews() if item["id"] == revision["review_id"])
            self.assertEqual(review["category"], "revision_confirmation")
            self.assertIn("enrollment_date", review["revision_fields"])

            store.resolve_review(review["id"], "accept_revision")
            link = next(item for item in store.data["relationships"] if item["type"] == "supersedes_for_fields")
            self.assertEqual(link["from_document_id"], revision["document_id"])
            self.assertEqual(link["to_document_id"], original["document_id"])

    def test_quarterly_checkpoint_starts_a_forward_only_historical_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = HomesteaderStore(folder / "state.json")
            checkpoint = folder / "historical-quarterly.txt"
            checkpoint.write_text(f"""INCOME VERIFICATION
Participant: Jasmine Morales
HMIS ID: H-000042
Program: TLS Adult SPA 2
Enrollment date: 2025-01-10
Document date: {date.today().isoformat()}
Reporting period: Quarterly recertification
""")
            store.ingest(checkpoint)

            self.assertEqual(store.housing_schedule_status(as_of=date.today()), [])
            self.assertFalse(any(row["category"] == "Scheduled Record Missing" for row in store.correction_findings()))

    def test_exit_document_stops_future_program_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = HomesteaderStore(folder / "state.json")
            enrollment = folder / "enrollment.txt"
            enrollment.write_text("""PROGRAM ENROLLMENT
Participant: Jasmine Morales
HMIS number: H-000042
Program: TLS Adult SPA 2
Enrollment date: 2026-01-10
""")
            exit_record = folder / "exit.txt"
            exit_record.write_text("""HMIS EXIT SUMMARY
Participant: Jasmine Morales
HMIS number: H-000042
Program: TLS Adult SPA 2
Exit date: 2026-07-01
Document date: 2026-07-01
""")
            store.ingest(enrollment)
            result = store.ingest(exit_record)
            statuses = store.housing_schedule_status(as_of=date(2026, 10, 15))
            self.assertEqual(result["status"], "filed")
            self.assertTrue(all(item["due_date"] < "2026-07-01" for item in statuses))
