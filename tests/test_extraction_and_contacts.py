import tempfile
import unittest
from pathlib import Path

from homesteader.core import HomesteaderStore
from homesteader.extraction import extract_common_facts


ROOT = Path(__file__).resolve().parents[1]


class ExtractionProtocolTests(unittest.TestCase):
    def test_labeled_facts_include_source_evidence(self):
        facts = extract_common_facts((ROOT / "fixtures/contact_information_jasmine.txt").read_text())
        self.assertEqual(facts["participant"]["value"], "Jasmine Morales")
        self.assertEqual(facts["date_of_birth"]["evidence"], "Date of birth: January 15, 1990")


class ContactIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = HomesteaderStore(Path(self.temp.name) / "state.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_first_contact_sheet_creates_provisional_person_without_manual_profile(self):
        result = self.store.ingest(ROOT / "fixtures/contact_information_jasmine.txt")
        self.assertEqual(result["status"], "filed")
        self.assertEqual(result["association"], "hmis_identity_match")
        person = next(entity for entity in self.store.data["entities"] if entity["id"] == result["person_id"])
        self.assertEqual(person["attributes"]["date_of_birth"], "January 15, 1990")

    def test_two_indistinguishable_existing_people_require_review(self):
        self.store._new_entity("person", "Jasmine Morales", date_of_birth="January 15, 1990", hmis_id="H-000042")
        self.store._new_entity("person", "Jasmine Morales", date_of_birth="January 15, 1990", hmis_id="H-000042")
        result = self.store.ingest(ROOT / "fixtures/contact_information_jasmine.txt")
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(len(result["candidates"]), 2)


if __name__ == "__main__":
    unittest.main()
