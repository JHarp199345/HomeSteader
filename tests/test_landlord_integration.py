"""
Self-contained end-to-end unit tests for Landlord & Move-In packet ingestion integration.
Does not rely on external Homesteader Test Documents folders.
"""

import pathlib
import tempfile
import unittest
from homesteader.core import HomesteaderStore, ExtractedDocument

class LandlordIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = pathlib.Path(self.temp_dir.name) / "test_state.json"
        self.store = HomesteaderStore(self.state_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_landlord_move_in_packet_without_hard_identifier_goes_to_review_without_creating_entities(self):
        # 0. Seed an existing participant in store with HMIS ID
        self.store._new_entity("person", "Casey Reed", hmis_id="H-TRAIN-0006")
        
        doc_path = pathlib.Path(self.temp_dir.name) / "move_in_name_only.txt"
        doc_path.write_text("Move-In Assistance Request Form\nParticipant: Casey Reed\nLandlord/ Property Management Name: Horizon Training Housing LLC\nProperty Address: 73 Sample Street\nUnit #: 5A\nMonthly Rent: $1,450.00\nSecurity Deposit: $1,450.00\nMove In Date: 2026-02-01")
        
        res = self.store.ingest(doc_path)
        doc_id = res["document_id"]
        
        # 1. Assert result is routed to Needs Review due to name-only identity rule
        review = next((r for r in self.store.data["review_queue"] if r.get("document_id") == doc_id), None)
        self.assertIsNotNone(review, "Move-in packet with name only must generate a Needs Review item")
        self.assertEqual(review.get("status"), "needs_review")
        
        # 2. Assert NO landlord, property, or unit entities are created when in Needs Review
        landlords = [e for e in self.store.data["entities"] if e["kind"] == "landlord"]
        properties = [e for e in self.store.data["entities"] if e["kind"] == "property"]
        units = [e for e in self.store.data["entities"] if e["kind"] == "unit"]
        self.assertEqual(len(landlords), 0, "No landlord entity must be created for unconfirmed participant")
        self.assertEqual(len(properties), 0, "No property entity must be created for unconfirmed participant")
        self.assertEqual(len(units), 0, "No unit entity must be created for unconfirmed participant")

    def test_landlord_move_in_packet_with_hmis_id_files_relationships_and_creates_entities(self):
        # 0. Seed participant Casey Reed with HMIS ID H-TRAIN-0006
        casey = self.store._new_entity("person", "Casey Reed", hmis_id="H-TRAIN-0006")
        
        doc_path = pathlib.Path(self.temp_dir.name) / "move_in_with_hmis.txt"
        doc_path.write_text("Move-In Assistance Request Form\nParticipant: Casey Reed\nHMIS ID #: H-TRAIN-0006\nLandlord/ Property Management Name: Horizon Training Housing LLC\nProperty Address: 73 Sample Street\nUnit #: 5A\nMonthly Rent: $1,450.00\nSecurity Deposit: $1,450.00\nMove In Date: 2026-02-01")
        
        res = self.store.ingest(doc_path)
        doc_id = res["document_id"]
        
        # 1. Assert filing status is filed
        self.assertEqual(res.get("status"), "filed")
        review = next((r for r in self.store.data["review_queue"] if r.get("document_id") == doc_id), None)
        self.assertIsNone(review, "Move-in packet with HMIS ID must file without review error")
        
        # 2. Assert landlord, property, unit entities are created
        landlords = [e for e in self.store.data["entities"] if e["kind"] == "landlord"]
        properties = [e for e in self.store.data["entities"] if e["kind"] == "property"]
        units = [e for e in self.store.data["entities"] if e["kind"] == "unit"]
        
        self.assertEqual(len(landlords), 1)
        self.assertEqual(landlords[0]["name"], "Horizon Training Housing LLC")
        self.assertEqual(len(properties), 1)
        self.assertEqual(properties[0]["name"], "73 Sample Street")
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["name"], "73 Sample Street / 5A")
        
        # 3. Assert evidence relationships are created
        rels = self.store.data["relationships"]
        has_housing_rec = [r for r in rels if r["type"] == "has_housing_record" and r["from_entity_id"] == casey["id"]]
        involves_ll = [r for r in rels if r["type"] == "involves_landlord" and r["to_entity_id"] == landlords[0]["id"]]
        concerns_prop = [r for r in rels if r["type"] == "concerns_property" and r["to_entity_id"] == properties[0]["id"]]
        concerns_unit = [r for r in rels if r["type"] == "concerns_unit" and r["to_entity_id"] == units[0]["id"]]
        
        self.assertEqual(len(has_housing_rec), 1)
        self.assertEqual(len(involves_ll), 1)
        self.assertEqual(len(concerns_prop), 1)
        self.assertEqual(len(concerns_unit), 1)

if __name__ == "__main__":
    unittest.main()
