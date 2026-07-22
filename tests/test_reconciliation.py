import tempfile
import unittest
from pathlib import Path

from homesteader.core import HomesteaderStore


class ReconciliationTests(unittest.TestCase):
    def test_hmis_confirmation_replaces_temporary_id_without_replacing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HomesteaderStore(Path(directory) / "state.json")
            temporary = store.create_temporary_file("Jasmine Morales")
            confirmed = store.confirm_hmis_identity(temporary["person_id"], "H-000042")
            self.assertEqual(confirmed["replaced_temporary_id"], "T-000001")
            self.assertEqual(confirmed["participant_ledger_id"], temporary["participant_ledger_id"])
            found = store.search_files("H-000042")
            self.assertEqual(found[0]["status"], "confirmed")
            self.assertIsNone(found[0]["temporary_id"])

    def test_name_search_returns_file_evidence_without_requiring_an_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HomesteaderStore(Path(directory) / "state.json")
            temporary = store.create_temporary_file("Jasmine Morales")
            ledger = temporary["participant_ledger_id"]
            store.data["documents"].append({
                "id": "contact-sheet", "original_name": "jasmine-contact.pdf",
                "extracted": {"document_type": "contact_information", "document_date": "2026-07-20"},
            })
            store._event("contact_information_recorded", ledger, {
                "document_id": "contact-sheet", "person_id": temporary["person_id"],
            })

            found = store.search_files("jasmine")

            self.assertEqual(found[0]["name"], "Jasmine Morales")
            self.assertEqual(found[0]["document_count"], 1)
            summary = store.participant_file(found[0]["person_id"])
            self.assertEqual(summary["documents"][0]["original_name"], "jasmine-contact.pdf")

    def test_participant_file_includes_a_relationship_neighborhood(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HomesteaderStore(Path(directory) / "state.json")
            participant = store.create_temporary_file("Jasmine Morales")
            lease = store._new_entity("lease", "Jasmine lease")
            property_entity = store._new_entity("property", "1415 Harbor View Avenue")
            store._relationship("tenant_under", participant["person_id"], lease["id"], "test")
            store._relationship("governs", lease["id"], property_entity["id"], "test")

            summary = store.participant_file(participant["person_id"])

            self.assertEqual([item["name"] for item in summary["related_entities"]], ["Jasmine lease", "1415 Harbor View Avenue"])

    def test_participant_index_filters_by_status_and_lease_relationship(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HomesteaderStore(Path(directory) / "state.json")
            confirmed = store.create_temporary_file("Jasmine Morales")
            store.confirm_hmis_identity(confirmed["person_id"], "H-000042")
            temporary = store.create_temporary_file("Luis Rivera")
            lease = store._new_entity("lease", "Jasmine lease")
            store._relationship("tenant_under", confirmed["person_id"], lease["id"], "test")

            confirmed_with_lease = store.participant_index(status="confirmed", has_lease=True)
            temporary_files = store.participant_index(status="temporary")

            self.assertEqual([row["name"] for row in confirmed_with_lease], ["Jasmine Morales"])
            self.assertEqual([row["name"] for row in temporary_files], ["Luis Rivera"])

    def test_participant_documents_grouped_by_date(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HomesteaderStore(Path(directory) / "state.json")
            temporary = store.create_temporary_file("Jasmine Morales")
            ledger = temporary["participant_ledger_id"]
            store.data["documents"].append({
                "id": "doc-1",
                "original_name": "income-verif.pdf",
                "ingested_at": "2026-07-21T10:00:00Z",
                "extracted": {"document_type": "income_verification", "document_date": "2026-07-20"},
            })
            store._event("income_verification_recorded", ledger, {
                "document_id": "doc-1", "person_id": temporary["person_id"],
            })

            groups = store.participant_documents_grouped_by_date(temporary["person_id"])
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["upload_date"], "2026-07-21")
            self.assertEqual(groups[0]["documents"][0]["original_name"], "income-verif.pdf")
            self.assertEqual(groups[0]["documents"][0]["status_code"], "active_export")

    def test_grouped_documents_mark_pending_review_from_the_actual_review_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HomesteaderStore(Path(directory) / "state.json")
            temporary = store.create_temporary_file("Jasmine Morales")
            ledger = temporary["participant_ledger_id"]
            store.data["documents"].append({
                "id": "doc-review", "original_name": "undated-income.pdf",
                "ingested_at": "2026-07-21T10:00:00Z",
                "extracted": {"document_type": "income_verification"},
            })
            store._event("income_verification_recorded", ledger, {
                "document_id": "doc-review", "person_id": temporary["person_id"],
            })
            store.data["review_queue"].append({
                "id": "review-1", "document_id": "doc-review", "status": "needs_review",
            })

            groups = store.participant_documents_grouped_by_date(temporary["person_id"])

            self.assertEqual(groups[0]["documents"][0]["status_code"], "needs_review")


if __name__ == "__main__":
    unittest.main()
