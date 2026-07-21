"""Fictional end-to-end TLS workload: mixed records, not a form-by-form demo."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from homesteader.core import HomesteaderStore


ROOT = Path(__file__).resolve().parents[1]


class TlsStressWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = HomesteaderStore(Path(self.temp.name) / "state.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_mixed_tls_intake_preserves_relationships_without_upload_order(self):
        # An unrelated blank form is cataloged rather than placed in a client file.
        blank = self.store.ingest(ROOT / "fixtures/blank_consent_to_share_information.txt")
        self.assertEqual(blank["destination"], "form_bank")

        # The participant anchor can arrive before or after periodic records.
        jasmine_a = self.store.ingest(ROOT / "fixtures/tls_participant_identification_jasmine_a.txt")
        self.assertEqual(jasmine_a["status"], "filed")
        initial = self.store.ingest(ROOT / "fixtures/tls_income_eligibility_jasmine_initial.txt")
        quarter_two = self.store.ingest(ROOT / "fixtures/tls_income_eligibility_jasmine_q2.txt")
        self.assertEqual(initial["income_ledger_id"], quarter_two["income_ledger_id"])

        # Lease and move-in material build the landlord/property graph.
        self.store.ingest(ROOT / "fixtures/tls_lease_jasmine_harbor_view.txt")
        self.store.ingest(ROOT / "fixtures/tls_move_in_assistance_jasmine_harbor_view.txt")
        self.assertEqual([item["hmis_id"] for item in self.store.relationship_search("Avery Collins")], ["H-TLS-000042"])

        # A different Jasmine makes name-only landlord communication ambiguous.
        self.store.ingest(ROOT / "fixtures/tls_participant_identification_jasmine_b.txt")
        notice = self.store.ingest(ROOT / "fixtures/tls_landlord_notice_jasmine_harbor_view.txt")
        self.assertEqual(notice["status"], "needs_review")
        self.store.resolve_review(
            notice["review_id"], "assign_existing", entity_id=jasmine_a["person_id"],
            note="Verified against the TLS file.",
        )

        # A photo has no meaningful OCR but gains explicit user context.
        photo = Path(self.temp.name) / "water-damage.heic"
        photo.write_bytes(b"fictional photo bytes")
        with patch("homesteader.core.recognize_image_with_vision", return_value=("", "Local OCR completed but found no readable text.")):
            photo_review = self.store.ingest(photo)
        self.store.resolve_review(
            photo_review["review_id"], "assign_existing", entity_id=jasmine_a["person_id"],
            context_note="Water damage in Unit 2A at 1415 Harbor View Avenue, reported by Jasmine Morales.",
        )

        # An exact repeat is never silently added as a new quarterly event.
        duplicate = self.store.ingest(ROOT / "fixtures/tls_income_eligibility_jasmine_q2.txt")
        self.assertEqual(duplicate["status"], "needs_review")
        self.assertIn("Exact content match", duplicate["reason"])

        jasmine_file = self.store.participant_file(jasmine_a["person_id"])
        self.assertTrue(any(item["kind"] == "property" and item["name"] == "1415 Harbor View Avenue" for item in jasmine_file["related_entities"]))
        self.assertTrue(any(event["type"] == "income_verification_recorded" for event in jasmine_file["events"]))
        self.assertTrue(any(event["type"] == "context_evidence_linked" for event in self.store.data["ledger_events"]))
        self.assertEqual(len([entity for entity in self.store.data["entities"] if entity["kind"] == "person" and entity["name"] == "Jasmine Morales"]), 2)
