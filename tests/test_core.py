import tempfile
import unittest
from pathlib import Path

from homesteader.core import HomesteaderStore


ROOT = Path(__file__).resolve().parents[1]


class LeaseLinkingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = HomesteaderStore(Path(self.temp.name) / "state.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_addendum_links_to_its_lease(self):
        first = self.store.ingest(ROOT / "fixtures/lease_elena_ramirez.txt")
        second = self.store.ingest(ROOT / "fixtures/pet_addendum_elena_ramirez.txt")
        self.assertEqual(first["status"], "filed")
        self.assertEqual(second["status"], "filed")
        self.assertEqual(len(self.store.data["relationships"]), 1)
        relationship = self.store.data["relationships"][0]
        self.assertEqual(relationship["type"], "modifies")
        self.assertEqual(relationship["confidence"], 1.0)
        self.assertEqual(len(self.store.data["ledger_events"]), 2)

    def test_ambiguous_addendum_goes_to_review(self):
        self.store.ingest(ROOT / "fixtures/lease_elena_ramirez.txt")
        result = self.store.ingest(ROOT / "fixtures/ambiguous_pet_addendum.txt")
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(len(self.store.data["relationships"]), 0)
        self.assertEqual(len(self.store.data["review_queue"]), 1)

    def test_blank_consent_form_is_cataloged_in_the_form_bank(self):
        result = self.store.ingest(ROOT / "fixtures/blank_consent_to_share_information.txt")
        self.assertEqual(result["status"], "filed")
        self.assertEqual(result["destination"], "form_bank")
        self.assertEqual(self.store.data["entities"][0]["kind"], "form_template")

    def test_exact_duplicate_is_not_stored_twice(self):
        source = ROOT / "fixtures/blank_consent_to_share_information.txt"
        self.store.ingest(source)
        duplicate = self.store.ingest(source)
        self.assertEqual(duplicate["status"], "needs_review")
        self.assertEqual(len(self.store.data["documents"]), 1)
        self.assertEqual(len(self.store.data["intake_occurrences"]), 2)
        self.assertEqual(self.store.data["ledger_events"][-1]["type"], "duplicate_candidate_detected")

    def test_rescan_formatting_variation_is_held_as_a_near_duplicate(self):
        self.store.ingest(ROOT / "fixtures/blank_consent_to_share_information.txt")
        result = self.store.ingest(ROOT / "fixtures/blank_consent_to_share_information_rescan.txt")
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("possible_duplicate_of", result)
        self.assertEqual(len(self.store.data["documents"]), 2)
        self.assertEqual(self.store.data["ledger_events"][-1]["type"], "possible_duplicate_detected")

    def test_recurring_income_declarations_create_separate_chronological_events(self):
        january = self.store.ingest(ROOT / "fixtures/income_declaration_jasmine_january.txt")
        february = self.store.ingest(ROOT / "fixtures/income_declaration_jasmine_february.txt")
        self.assertEqual(january["status"], "filed")
        self.assertEqual(february["status"], "filed")
        self.assertNotEqual(january["document_id"], february["document_id"])
        self.assertEqual(january["income_ledger_id"], february["income_ledger_id"])
        periods = [event["details"]["reporting_period"] for event in self.store.data["ledger_events"] if event["type"] == "income_declaration_recorded"]
        self.assertEqual(periods, ["January 2026", "February 2026"])

    def test_undated_income_declaration_is_kept_for_review_without_inventing_a_date(self):
        result = self.store.ingest(ROOT / "fixtures/income_declaration_undated.txt")
        self.assertEqual(result["status"], "needs_review")
        document = self.store.data["documents"][0]
        self.assertIsNone(document["extracted"]["document_date"])
        self.assertIsNone(document["extracted"]["reporting_period"])

    def test_enrollment_and_consent_share_a_case_ledger(self):
        enrollment = self.store.ingest(ROOT / "fixtures/program_enrollment_jasmine.txt")
        consent = self.store.ingest(ROOT / "fixtures/completed_consent_jasmine.txt")
        self.assertEqual(enrollment["status"], "filed")
        self.assertEqual(consent["status"], "filed")
        self.assertEqual(enrollment["case_ledger_id"], consent["case_ledger_id"])
        event_types = [event["type"] for event in self.store.data["ledger_events"]]
        self.assertIn("program_enrollment_recorded", event_types)
        self.assertIn("consent_recorded", event_types)

    def test_completed_consent_without_participant_is_held_for_review(self):
        result = self.store.ingest(ROOT / "fixtures/completed_consent_missing_participant.txt")
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("participant", result["reason"])


if __name__ == "__main__":
    unittest.main()
