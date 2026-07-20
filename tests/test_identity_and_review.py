import tempfile
import unittest
from pathlib import Path

from homesteader.core import HomesteaderStore
from homesteader.entity_resolution import IdentityDecision, PersonCandidate, resolve_person


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


if __name__ == "__main__":
    unittest.main()
