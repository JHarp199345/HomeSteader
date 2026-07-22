import tempfile
import unittest
from pathlib import Path

from homesteader.core import HomesteaderStore, browse_kind_from_query


ROOT = Path(__file__).resolve().parents[1]


class LeaseLinkingTests(unittest.TestCase):

    def test_workplace_search_terms_select_a_category_without_identity_matching(self):
        self.assertEqual(browse_kind_from_query("PTC"), "person")
        self.assertEqual(browse_kind_from_query("tenant"), "person")
        self.assertEqual(browse_kind_from_query("property owner"), "landlord")
        self.assertEqual(browse_kind_from_query("apartment complex"), "property")
        self.assertIsNone(browse_kind_from_query("Jasmine Morales"))

    def test_intake_jobs_are_persistent_and_claimed_one_at_a_time(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = HomesteaderStore(folder / "state.json")
            packet = store.start_intake_packet("Queue test")
            source = folder / "scan.txt"
            source.write_text("Example scan")
            jobs = store.queue_intake_sources(packet["id"], [source])
            self.assertEqual(store.intake_job_counts()["waiting"], 1)
            self.assertEqual(store.queue_intake_sources(packet["id"], [source]), [])
            job = store.claim_next_intake_job()
            self.assertEqual(job["status"], "processing")
            self.assertIsNone(store.claim_next_intake_job())
            store.finish_intake_job(job["id"], result={"status": "filed"})
            self.assertEqual(store.intake_job_counts()["completed"], 1)

    def test_interrupted_processing_job_returns_to_waiting_on_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "state.json"
            store = HomesteaderStore(path)
            packet = store.start_intake_packet("Queue test")
            source = folder / "scan.txt"
            source.write_text("Example scan")
            store.queue_intake_sources(packet["id"], [source])
            store.claim_next_intake_job()
            store.save()
            restarted = HomesteaderStore(path)
            self.assertEqual(restarted.intake_job_counts()["waiting"], 1)

    def test_confirmed_entity_alias_supports_reverse_search_without_merging_owner_and_property(self):
        participant = self.store._new_entity("person", "Jasmine Morales", hmis_id="H-000042")
        property_entity = self.store._entity("property", "Harbor View Apartments")
        owner = self.store._entity("landlord", "Harbor View LLC")
        self.store._relationship("program_documented_for", participant["id"], property_entity["id"], "test")
        self.store._relationship("landlord_for", owner["id"], property_entity["id"], "test")
        self.store.add_entity_alias(property_entity["id"], "Harbor View Apts.")

        directory = self.store.entity_directory_search("Harbor View Apts")
        reverse = self.store.relationship_search("Harbor View Apts")
        self.assertEqual(directory[0]["entity_id"], property_entity["id"])
        self.assertEqual(reverse[0]["person_id"], participant["id"])
        self.assertNotEqual(property_entity["id"], owner["id"])

    def test_universal_search_connects_landlord_property_and_participant_without_merging_them(self):
        participant = self.store._new_entity("person", "Jasmine Morales", hmis_id="H-000042")
        property_entity = self.store._entity("property", "Harbor View Apartments")
        owner = self.store._entity("landlord", "Harbor View LLC")
        self.store._relationship("occupies", participant["id"], property_entity["id"], "test")
        self.store._relationship("landlord_for", owner["id"], property_entity["id"], "test")

        result = self.store.universal_search("Harbor View LLC")

        self.assertEqual(result["entities"][0]["entity_id"], owner["id"])
        self.assertIn(property_entity["id"], {item["entity_id"] for item in result["related_entities"]})
        self.assertIn(participant["id"], {item["entity_id"] for item in result["related_entities"]})
        self.assertEqual([item["person_id"] for item in result["participant_files"]], [participant["id"]])
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
        self.assertTrue(any(event["type"] == "lease_created" for event in self.store.data["ledger_events"]))
        self.assertTrue(any(event["type"] == "move_in_workflow_opened" for event in self.store.data["ledger_events"]))

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

    def test_move_in_records_open_one_workflow_and_track_missing_core_evidence(self):
        request = self.store.ingest(ROOT / "fixtures/tls_move_in_assistance_jasmine_harbor_view.txt")
        lease = self.store.ingest(ROOT / "fixtures/tls_lease_jasmine_harbor_view.txt")

        self.assertEqual(request["status"], "filed")
        self.assertEqual(lease["status"], "filed")
        self.assertEqual(request["move_in_workflow_id"], lease["move_in_workflow_id"])
        workflow = self.store.move_in_workflow_status(request["move_in_workflow_id"])[0]
        self.assertEqual(workflow["status"], "in_progress")
        self.assertIn("move_in_assistance_request", workflow["present_record_types"])
        self.assertIn("lease", workflow["present_record_types"])
        self.assertIn("w9", workflow["missing_record_types"])
        self.assertIn("ownership_verification", workflow["missing_record_types"])

    def test_move_in_rules_are_copied_locally_without_overwriting_a_local_policy(self):
        path = self.store.initialize_move_in_rules()
        self.assertTrue(path.exists())
        original = path.read_text()
        path.write_text('{"workflow_key":"custom"}')
        self.store.initialize_move_in_rules()
        self.assertEqual(path.read_text(), '{"workflow_key":"custom"}')

    def test_completed_fictional_move_in_packet_reaches_local_review_after_contextual_attachment(self):
        request = self.store.ingest(ROOT / "fixtures/move_in_request_jasmine_complete.txt")
        for name in [
            "move_in_lease_jasmine_complete.txt",
            "move_in_landlord_acknowledgement_jasmine_complete.txt",
            "move_in_unit_owner_certification_jasmine_complete.txt",
        ]:
            self.assertEqual(self.store.ingest(ROOT / "fixtures" / name)["status"], "filed")

        person_id = request["participant_id"]
        for name in [
            "move_in_w9_harbor_view_complete.txt",
            "move_in_ownership_verification_harbor_view_complete.txt",
            "move_in_habitability_harbor_view_complete.txt",
        ]:
            result = self.store.ingest(ROOT / "fixtures" / name)
            self.assertEqual(result["status"], "needs_review")
            self.store.resolve_review(result["review_id"], "assign_existing", entity_id=person_id, note="Verified against the active fictional move-in packet.")

        workflow = self.store.move_in_workflow_status()[0]
        self.assertEqual(workflow["status"], "complete_for_local_review")
        self.assertEqual(workflow["missing_record_types"], [])
        self.assertEqual(workflow["conflicts"], [])

    def test_conflicting_move_in_rent_stays_visible_for_review(self):
        self.store.ingest(ROOT / "fixtures/move_in_request_jasmine_complete.txt")
        conflict = Path(self.temp.name) / "conflicting-lease.txt"
        conflict.write_text((ROOT / "fixtures/move_in_lease_jasmine_complete.txt").read_text().replace("$1,850", "$1,900"))
        self.store.ingest(conflict)

        workflow = self.store.move_in_workflow_status()[0]
        self.assertEqual(workflow["status"], "needs_review")
        self.assertEqual(workflow["conflicts"][0]["field"], "monthly_rent")
        self.assertTrue(any(row["category"] == "Move In Fact Conflict" for row in self.store.correction_findings()))

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

    def test_entity_directory_lists_everything_recorded_by_kind(self):
        self.store.ingest(ROOT / "fixtures/lease_elena_ramirez.txt")

        landlords = self.store.entity_directory("landlord")
        properties = self.store.entity_directory("property")
        people = self.store.entity_directory("person")

        self.assertEqual(len(landlords), 1)
        self.assertEqual(len(properties), 1)
        self.assertEqual([person["name"] for person in people], ["Elena Ramirez"])
        self.assertGreater(landlords[0]["relationship_count"], 0)
        everything = self.store.entity_directory()
        self.assertIn("lease", {row["kind"] for row in everything})
        self.assertNotIn("participant_ledger", {row["kind"] for row in everything})

    def test_entity_network_supports_reverse_lookup_from_landlord_and_property(self):
        self.store.ingest(ROOT / "fixtures/lease_elena_ramirez.txt")
        landlord = next(row for row in self.store.entity_directory("landlord"))
        property_row = next(row for row in self.store.entity_directory("property"))

        landlord_network = self.store.entity_network(landlord["entity_id"])
        property_network = self.store.entity_network(property_row["entity_id"])

        self.assertIn("Elena Ramirez", [item["name"] for item in landlord_network["connected"].get("person", [])])
        self.assertIn(property_row["name"], [item["name"] for item in landlord_network["connected"].get("property", [])])
        self.assertIn("Elena Ramirez", [item["name"] for item in property_network["connected"].get("person", [])])
        self.assertIn(landlord["name"], [item["name"] for item in property_network["connected"].get("landlord", [])])
        self.assertTrue(landlord_network["documents"], "the lease naming the landlord should be listed")
        with self.assertRaises(ValueError):
            self.store.entity_network("missing-entity-id")

    def test_entity_network_surfaces_evidence_through_a_recorded_relationship(self):
        """A network cannot hide stored evidence merely because it sits on a connected participant."""
        participant = self.store.create_temporary_file("Devin Cross")
        landlord = self.store._new_entity("landlord", "Example Terrace Housing LLC")
        property_entity = self.store._new_entity("property", "220 Example Terrace, Unit 7B")
        self.store.data["documents"].append({
            "id": "move-in-proof", "original_name": "devin-move-in.pdf",
            "extracted": {"document_type": "move_in_assistance_request"},
        })
        self.store._event("housing_document_recorded", participant["participant_ledger_id"], {
            "document_id": "move-in-proof", "participant_id": participant["person_id"],
        })
        self.store._relationship("leases_from", participant["person_id"], landlord["id"], "test")
        self.store._relationship("owns_property", landlord["id"], property_entity["id"], "test")

        landlord_network = self.store.entity_network(landlord["id"])
        property_network = self.store.entity_network(property_entity["id"])

        self.assertEqual(landlord_network["documents"][0]["document_id"], "move-in-proof")
        self.assertEqual(landlord_network["documents"][0]["evidence_scope"], "related")
        self.assertEqual(property_network["documents"][0]["document_id"], "move-in-proof")


if __name__ == "__main__":
    unittest.main()
