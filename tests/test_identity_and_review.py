import tempfile
import unittest
from pathlib import Path

from homesteader.core import HomesteaderStore
from homesteader.entity_resolution import IdentityDecision, PersonCandidate, resolve_person


ROOT = Path(__file__).resolve().parents[1]


class IdentityResolutionTests(unittest.TestCase):
    def test_same_name_with_conflicting_birthdate_creates_new_provisional_identity(self):
        match = resolve_person(
            name="Jasmine Morales", date_of_birth="1990-01-01",
            candidates=[PersonCandidate("existing", "Jasmine Morales", date_of_birth="1985-05-05")],
        )
        self.assertEqual(match.decision, IdentityDecision.CREATE_PROVISIONAL)

    def test_multiple_same_name_candidates_without_birthdate_go_to_review(self):
        match = resolve_person(
            name="Jasmine Morales", date_of_birth=None,
            candidates=[PersonCandidate("one", "Jasmine Morales"), PersonCandidate("two", "Jasmine Morales")],
        )
        self.assertEqual(match.decision, IdentityDecision.REVIEW)


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = HomesteaderStore(Path(self.temp.name) / "state.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_human_can_create_a_new_person_from_review(self):
        document = {"id": "document-1"}
        review = self.store._review(document, "Multiple Jasmine Morales candidates.", [{"entity_id": "one"}, {"entity_id": "two"}])
        resolved = self.store.resolve_review(review["review_id"], "create_person", new_person_name="Jasmine Morales", note="Different date of birth.")
        self.assertEqual(resolved["status"], "resolved")
        person = next(entity for entity in self.store.data["entities"] if entity["id"] == resolved["resolution"]["entity_id"])
        self.assertTrue(person["provisional"])
        self.assertEqual(len(self.store.pending_reviews()), 0)

    def test_human_can_catalog_an_unclassified_blank_document_in_the_form_bank(self):
        document = {"id": "document-blank", "original_name": "blank-release.txt", "source_text": "Blank Release Authorization\nComplete before use."}
        self.store.data["documents"].append(document)
        review = self.store._review(document, "Document type is not supported by the v0 prototype.")

        resolved = self.store.resolve_review(review["review_id"], "catalog_form")

        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["resolution"]["action"], "catalog_form")
        self.assertTrue(any(entity["kind"] == "form_template" for entity in self.store.data["entities"]))

    def test_packet_proposes_a_later_identity_anchor_for_an_earlier_unidentified_document(self):
        result = self.store.ingest_packet([
            ROOT / "fixtures/completed_consent_missing_participant.txt",
            ROOT / "fixtures/contact_information_jasmine.txt",
        ], label="Jasmine intake packet")
        person = next(entity for entity in self.store.data["entities"] if entity["kind"] == "person")
        review = self.store.pending_reviews()[0]
        self.assertEqual(result["proposed_person_id"], person["id"])
        self.assertEqual(review["proposed_person_id"], person["id"])
        self.assertEqual(review["candidates"][0]["entity_id"], person["id"])
        self.assertEqual(review["packet_id"], result["packet_id"])

        resolved = self.store.resolve_review(review["id"], "assign_existing", entity_id=person["id"])
        self.assertEqual(resolved["status"], "resolved")
        assignment = self.store.data["ledger_events"][-1]
        self.assertEqual(assignment["type"], "document_manually_assigned")
        self.assertEqual(assignment["details"]["participant_id"], person["id"])

    def test_open_packet_can_be_completed_in_separate_scanning_sessions(self):
        packet = self.store.start_intake_packet("Jasmine open packet")
        first = self.store.add_to_intake_packet(packet["id"], [ROOT / "fixtures/completed_consent_missing_participant.txt"])
        self.assertIsNone(first["proposed_person_id"])
        self.assertEqual(len(self.store.open_intake_packets()), 1)

        second = self.store.add_to_intake_packet(packet["id"], [ROOT / "fixtures/contact_information_jasmine.txt"])
        review = self.store.pending_reviews()[0]
        self.assertEqual(second["proposed_person_id"], review["proposed_person_id"])
        closed = self.store.close_intake_packet(packet["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(self.store.open_intake_packets(), [])

    def test_detached_document_can_join_an_open_packet_later(self):
        detached = self.store.ingest(ROOT / "fixtures/completed_consent_missing_participant.txt")
        packet = self.store.start_intake_packet("Jasmine detached scans")
        self.store.attach_document_to_intake_packet(packet["id"], detached["document_id"])
        self.store.add_to_intake_packet(packet["id"], [ROOT / "fixtures/contact_information_jasmine.txt"])
        review = self.store.pending_reviews()[0]
        self.assertEqual(review["packet_id"], packet["id"])
        self.assertTrue(review["proposed_person_id"])

    def test_inbox_ignores_an_already_processed_source_file(self):
        inbox = Path(self.temp.name) / "inbox"
        inbox.mkdir()
        source = inbox / "contact.txt"
        source.write_text((ROOT / "fixtures/contact_information_jasmine.txt").read_text())
        packet = self.store.start_intake_packet("Jasmine folder")
        first = self.store.ingest_inbox(inbox, packet_id=packet["id"])
        second = self.store.ingest_inbox(inbox, packet_id=packet["id"])
        self.assertEqual(len(first["processed"]), 1)
        self.assertEqual(second["processed"], [])
        self.assertEqual(second["skipped"][0]["reason"], "Already processed source file.")


if __name__ == "__main__":
    unittest.main()
