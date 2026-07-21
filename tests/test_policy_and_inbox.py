import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from homesteader.core import HomesteaderStore
from homesteader.inbox import inspect_inbox
from homesteader.policy import DisclosureDenied, ProcessingPolicy, ProviderKind


class PolicyTests(unittest.TestCase):
    def test_local_processing_is_allowed(self):
        ProcessingPolicy().authorize(ProviderKind.LOCAL, "classify a document")

    def test_external_processing_is_denied_by_default(self):
        with self.assertRaises(DisclosureDenied):
            ProcessingPolicy().authorize(ProviderKind.EXTERNAL, "classify a document", "gemini-workspace")

    def test_configured_provider_is_authorized_without_adding_network_access(self):
        policy = ProcessingPolicy(configured_external_providers=frozenset({"gemini-workspace"}))
        self.assertIsNone(policy.authorize(ProviderKind.EXTERNAL, "classify a document", "gemini-workspace"))


class InboxTests(unittest.TestCase):
    def test_inspection_lists_local_files_without_moving_them(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory)
            source = inbox / "scan001.txt"
            source.write_text("fictional record")
            items = inspect_inbox(inbox)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].path, source)
            self.assertTrue(source.exists())

    def test_image_scan_is_archived_and_sent_to_review_after_local_ocr(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "phone-scan.heic"
            source.write_bytes(b"fictional image bytes")
            store = HomesteaderStore(Path(directory) / "state.json")
            with patch("homesteader.core.recognize_image_with_vision", return_value=("Participant: Jasmine Morales", None)):
                result = store.ingest(source)

            self.assertEqual(result["status"], "needs_review")
            document = store.data["documents"][0]
            self.assertEqual(document["source_format"], "heic")
            self.assertEqual(document["text_extraction"]["method"], "macos_vision_ocr")
            self.assertTrue((store.path.parent / document["stored_source_path"]).exists())

    def test_context_note_turns_an_ambiguous_photo_into_explicit_participant_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bedroom-wall.jpg"
            source.write_bytes(b"fictional image bytes")
            store = HomesteaderStore(Path(directory) / "state.json")
            participant = store.create_temporary_file("Jasmine Morales")
            property_entity = store._new_entity("property", "1415 Harbor View Avenue")
            unit = store._new_entity("unit", "1415 Harbor View Avenue / 1")
            store._relationship("unit_of", unit["id"], property_entity["id"], "test")
            with patch("homesteader.core.recognize_image_with_vision", return_value=("", "Local OCR completed but found no readable text.")):
                review = store.ingest(source)

            store.resolve_review(
                review["review_id"], "assign_existing", entity_id=participant["person_id"],
                context_note="Water damage on the bedroom wall in Unit 1 at 1415 Harbor View Avenue, reported by Jasmine Morales today.",
            )

            document = store.data["documents"][0]
            self.assertEqual(document["context_annotations"][0]["provenance"], "user_context_note")
            self.assertTrue(any(item["kind"] == "context_evidence" for item in store.data["entities"]))
            self.assertTrue(any(event["type"] == "context_evidence_linked" for event in store.data["ledger_events"]))
            self.assertTrue(any(item["type"] == "context_mentions_property" for item in store.data["relationships"]))
            self.assertTrue(any(item["type"] == "context_mentions_unit" for item in store.data["relationships"]))
            self.assertEqual([match["name"] for match in store.relationship_search("Harbor View")], ["Jasmine Morales"])


if __name__ == "__main__":
    unittest.main()
