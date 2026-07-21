import tempfile
import unittest
from pathlib import Path

from homesteader.core import HomesteaderStore


ROOT = Path(__file__).resolve().parents[1]


class AIProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = HomesteaderStore(Path(self.temp.name) / "state.json")
        self.document_id = self.store.ingest(ROOT / "fixtures/tls_participant_identification_jasmine_a.txt")["document_id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_evidence_backed_ai_proposal_is_queued_for_human_review(self):
        result = self.store.submit_ai_proposal({
            "document_id": self.document_id,
            "provider_id": "gemini-workspace",
            "document_type": "contact_information",
            "overall_confidence": 0.97,
            "facts": [{
                "field": "hmis_id", "value": "H-TLS-000042",
                "evidence": "HMIS ID #: H-TLS-000042", "confidence": 0.99,
            }],
            "uncertainties": [],
        })
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(len(self.store.data["ai_proposals"]), 1)
        self.assertFalse(any(event["type"] == "ai_proposal_applied" for event in self.store.data["ledger_events"]))

    def test_unsupported_ai_evidence_is_rejected(self):
        result = self.store.submit_ai_proposal({
            "document_id": self.document_id,
            "provider_id": "gemini-workspace",
            "document_type": "contact_information",
            "overall_confidence": 0.99,
            "facts": [{
                "field": "landlord", "value": "Imaginary Landlord",
                "evidence": "Landlord: Imaginary Landlord", "confidence": 0.99,
            }],
            "uncertainties": [],
        })
        self.assertEqual(result["status"], "rejected")
        self.assertIn("quoted evidence is not present", result["validation_errors"][0])

    def test_visual_evidence_for_an_image_remains_review_only(self):
        document = self.store.ingest(ROOT / "fixtures/completed_consent_jasmine.txt")
        stored = next(item for item in self.store.data["documents"] if item["id"] == document["document_id"])
        stored["source_format"] = "png"
        result = self.store.submit_ai_proposal({
            "document_id": stored["id"], "provider_id": "local-vision-test", "document_type": "consent_to_share",
            "overall_confidence": 0.72, "transcription": "Handwritten HMIS number H-000042",
            "facts": [{"field": "hmis_id", "value": "H-000042", "evidence": "Handwritten HMIS field reads H-000042", "evidence_type": "visual_evidence", "confidence": 0.72}],
            "uncertainties": ["Signature is hard to read"],
        })
        self.assertEqual(result["status"], "needs_review")
