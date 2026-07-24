"""
Unit tests for preserved revision behavior and missing-HMIS follow-up safety.
"""

import json
import pathlib
import tempfile
import unittest
from homesteader.core import HomesteaderStore, ExtractedDocument

class RevisionBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = pathlib.Path(self.temp_dir.name) / "test_state.json"
        self.store = HomesteaderStore(self.state_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_devin_cross_incomplete_followed_by_complete_document_preserves_incomplete_original(self):
        # 0. Seed existing participant Devin Cross with HMIS ID in store
        devin_person = self.store._new_entity("person", "Devin Cross", hmis_id="H-TRAIN-0007")

        # 1. First ingest incomplete recertification document (missing HMIS ID, name only)
        doc1_path = pathlib.Path(self.temp_dir.name) / "incomplete_recertification_devin.txt"
        doc1_path.write_text("Recertification Form\nParticipant: Devin Cross\nEnrollment date: 2026-01-15\nDocument date: 2026-03-08\nProgram: TLS")
        
        doc1_res = self.store.ingest(doc1_path)
        doc1_id = doc1_res.get("document_id")
        doc1_record = next(d for d in self.store.data["documents"] if d["id"] == doc1_id)
        
        # Verify incomplete record routes to Needs Review and is not auto-assigned
        review1 = next((r for r in self.store.data["review_queue"] if r.get("document_id") == doc1_id), None)
        self.assertIsNotNone(review1, "Incomplete name-only document must generate a Needs Review item")
        self.assertIsNone(doc1_record.get("participant_id"), "Incomplete document must remain unassigned to participant")

        # 2. Ingest later completed recertification document (with HMIS ID)
        doc2_path = pathlib.Path(self.temp_dir.name) / "completed_recertification_devin.txt"
        doc2_path.write_text("Recertification Form\nParticipant: Devin Cross\nHMIS ID: H-TRAIN-0007\nEnrollment date: 2026-01-15\nDocument date: 2026-03-08\nProgram: TLS")
        
        doc2_res = self.store.ingest(doc2_path)
        doc2_id = doc2_res.get("document_id")
        
        # Verify completed document files independently and links to Devin Cross in participant_file
        review2 = next((r for r in self.store.data["review_queue"] if r.get("document_id") == doc2_id), None)
        self.assertIsNone(review2, "Completed document with HMIS ID must auto-file without review error")
        
        pf = self.store.participant_file(devin_person["id"])
        pf_doc_ids = [d["id"] for d in pf.get("documents", [])]
        self.assertIn(doc2_id, pf_doc_ids, "Completed document must be present in participant file")

        # 3. SAFETY INVARIANT VERIFICATION:
        # Incomplete original's review queue item must NOT be automatically resolved or deleted
        reviews = [r for r in self.store.data["review_queue"] if r.get("document_id") == doc1_id]
        self.assertEqual(len(reviews), 1, "Incomplete document review item must remain in review_queue")
        self.assertEqual(reviews[0]["id"], review1["id"])

        # Incomplete original document must NOT be automatically marked as superseded or altered
        stored_doc1 = next(d for d in self.store.data["documents"] if d["id"] == doc1_id)
        self.assertNotIn("accepted_revision_of_document_id", stored_doc1, "Incomplete original must not be marked superseded automatically")

if __name__ == "__main__":
    unittest.main()
