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
        relationship = next(item for item in self.store.data["relationships"] if item["type"] == "modifies")
        self.assertEqual(relationship["type"], "modifies")
        self.assertEqual(relationship["confidence"], 1.0)
        self.assertEqual(len(self.store.data["ledger_events"]), 2)

    def test_lease_connects_existing_participant_landlord_and_property_for_reverse_search(self):
        participant = self.store.ingest(ROOT / "fixtures/tls_participant_identification_jasmine_a.txt")
        lease = self.store.ingest(ROOT / "fixtures/tls_lease_jasmine_harbor_view.txt")

        self.assertEqual(lease["status"], "filed")
        self.assertEqual(lease["participant_id"], participant["person_id"])
        landlord_matches = self.store.relationship_search("Avery Collins")
        property_matches = self.store.relationship_search("Harbor View")
        self.assertEqual([match["name"] for match in landlord_matches], ["Jasmine Morales"])
        self.assertEqual([match["name"] for match in property_matches], ["Jasmine Morales"])

    def test_lease_with_multiple_same_name_participants_goes_to_review(self):
        first = self.store.ingest(ROOT / "fixtures/tls_participant_identification_jasmine_a.txt")
        self.store.ingest(ROOT / "fixtures/tls_participant_identification_jasmine_b.txt")

        lease = self.store.ingest(ROOT / "fixtures/tls_lease_jasmine_harbor_view.txt")

        self.assertEqual(lease["status"], "needs_review")
        self.assertEqual(len(lease["candidates"]), 2)
        self.store.resolve_review(lease["review_id"], "assign_existing", entity_id=first["person_id"], note="Verified against the physical file.")
        matches = self.store.relationship_search("Avery Collins")
        self.assertEqual([match["hmis_id"] for match in matches], ["H-TLS-000042"])
        self.assertTrue(any(event["type"] == "lease_relationship_confirmed" for event in self.store.data["ledger_events"]))

    def test_housing_record_links_participant_landlord_and_property_without_a_lease(self):
        participant = self.store.ingest(ROOT / "fixtures/tls_participant_identification_jasmine_a.txt")
        result = self.store.ingest(ROOT / "fixtures/tls_move_in_assistance_jasmine_harbor_view.txt")

        self.assertEqual(result["status"], "filed")
        self.assertEqual(result["participant_id"], participant["person_id"])
        self.assertEqual([match["name"] for match in self.store.relationship_search("Avery Collins")], ["Jasmine Morales"])
        self.assertEqual([match["name"] for match in self.store.relationship_search("Harbor View")], ["Jasmine Morales"])

    def test_ambiguous_addendum_goes_to_review(self):
        self.store.ingest(ROOT / "fixtures/lease_elena_ramirez.txt")
        result = self.store.ingest(ROOT / "fixtures/ambiguous_pet_addendum.txt")
        self.assertEqual(result["status"], "needs_review")
        self.assertFalse(any(item["type"] == "modifies" for item in self.store.data["relationships"]))
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
        self.assertEqual(self.store.pending_reviews()[0]["category"], "duplicate_check")

    def test_source_is_archived_locally_without_moving_the_intake_copy(self):
        source = ROOT / "fixtures/contact_information_jasmine.txt"
        result = self.store.ingest(source)
        document = next(item for item in self.store.data["documents"] if item["id"] == result["document_id"])

        archived = self.store.path.parent / document["stored_source_path"]

        self.assertTrue(source.exists())
        self.assertTrue(archived.exists())
        self.assertEqual(archived.read_bytes(), source.read_bytes())
        self.assertEqual(archived.name, f"{document['sha256']}.txt")

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

    def test_tls_initial_and_quarterly_income_verifications_append_to_one_ledger(self):
        initial = self.store.ingest(ROOT / "fixtures/tls_income_eligibility_jasmine_initial.txt")
        quarter_two = self.store.ingest(ROOT / "fixtures/tls_income_eligibility_jasmine_q2.txt")
        quarter_three = self.store.ingest(ROOT / "fixtures/tls_income_eligibility_jasmine_q3.txt")

        self.assertEqual(initial["status"], "filed")
        self.assertEqual(quarter_two["status"], "filed")
        self.assertEqual(quarter_three["status"], "filed")
        self.assertEqual(initial["income_ledger_id"], quarter_two["income_ledger_id"])
        self.assertEqual(quarter_two["income_ledger_id"], quarter_three["income_ledger_id"])
        events = [event for event in self.store.data["ledger_events"] if event["type"] == "income_verification_recorded"]
        self.assertEqual(
            [event["details"]["reporting_period"] for event in events],
            [
                "Initial enrollment - January 2026",
                "Quarterly recertification - April 2026",
                "Quarterly recertification - July 2026",
            ],
        )

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
