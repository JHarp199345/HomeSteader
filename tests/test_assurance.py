import unittest

from homesteader.assurance import Decision, assess_relationship


class AssuranceTests(unittest.TestCase):
    REQUIRED_LEASE_IDENTIFIERS = {"tenant", "property", "unit", "lease_date"}

    def test_high_ai_confidence_without_identity_evidence_still_requires_review(self):
        assessment = assess_relationship(
            required_hard_matches=self.REQUIRED_LEASE_IDENTIFIERS,
            observed_hard_matches={"tenant"},
            conflicting_identifiers=set(),
            ai_confidence=0.99,
        )
        self.assertEqual(assessment.decision, Decision.REVIEW)
        self.assertIn("cannot establish identity", assessment.reasons[1])

    def test_conflicting_identifier_requires_review_even_when_everything_else_matches(self):
        assessment = assess_relationship(
            required_hard_matches=self.REQUIRED_LEASE_IDENTIFIERS,
            observed_hard_matches=self.REQUIRED_LEASE_IDENTIFIERS,
            conflicting_identifiers={"unit"},
            ai_confidence=1.0,
        )
        self.assertEqual(assessment.decision, Decision.REVIEW)

    def test_complete_hard_match_can_be_accepted(self):
        assessment = assess_relationship(
            required_hard_matches=self.REQUIRED_LEASE_IDENTIFIERS,
            observed_hard_matches=self.REQUIRED_LEASE_IDENTIFIERS,
            conflicting_identifiers=set(),
            ai_confidence=0.78,
        )
        self.assertEqual(assessment.decision, Decision.ACCEPT)


if __name__ == "__main__":
    unittest.main()
