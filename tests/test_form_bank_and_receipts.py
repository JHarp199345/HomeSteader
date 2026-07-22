import tempfile
import unittest
from pathlib import Path

from homesteader.core import HomesteaderStore


class FormBankTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp_dir.name) / "homesteader.json"
        self.store = HomesteaderStore(self.state_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_form_bank_precedence_printed_date_wins(self):
        # Create 2 documents for the same blank form
        doc1 = {
            "id": "doc-1",
            "original_name": "Consent_Form.pdf",
            "source_text": "Consent to Share Information. Effective: 2025-01-01",
            "sha256": "hash1",
            "ingested_at": "2026-05-01T10:00:00"
        }
        doc2 = {
            "id": "doc-2",
            "original_name": "Consent_Form.pdf",
            "source_text": "Consent to Share Information. Effective: 2026-08-01",
            "sha256": "hash2",
            "ingested_at": "2026-04-01T10:00:00" # Uploaded earlier, but effective date is LATER
        }
        self.store.data["documents"].extend([doc1, doc2])

        res1 = self.store.add_form_template("doc-1")
        res2 = self.store.add_form_template("doc-2")

        family = res2["family"]
        versions = family["attributes"]["versions"]
        self.assertEqual(len(versions), 2)
        
        # doc-2 has effective date 2026-08-01 which is newer than 2025-01-01
        v2 = next(v for v in versions if v["document_id"] == "doc-2")
        v1 = next(v for v in versions if v["document_id"] == "doc-1")
        self.assertTrue(v2["is_current"])
        self.assertFalse(v1["is_current"])

    def test_form_bank_newest_upload_wins_when_no_printed_version_date(self):
        self.store.data["documents"].extend([
            {
                "id": "doc-older", "original_name": "W9.pdf", "source_text": "Form W-9\nRequest for Taxpayer ID",
                "sha256": "hash-older", "ingested_at": "2026-01-01T10:00:00",
            },
            {
                "id": "doc-newer", "original_name": "W9.pdf", "source_text": "Form W-9\nRequest for Taxpayer ID",
                "sha256": "hash-newer", "ingested_at": "2026-06-01T10:00:00",
            },
        ])

        self.store.add_form_template("doc-older")
        result = self.store.add_form_template("doc-newer")

        versions = result["family"]["attributes"]["versions"]
        self.assertTrue(next(version for version in versions if version["document_id"] == "doc-newer")["is_current"])
        self.assertFalse(next(version for version in versions if version["document_id"] == "doc-older")["is_current"])

    def test_form_bank_exact_sha256_duplicate_counter(self):
        doc1 = {
            "id": "doc-1",
            "original_name": "W9_Blank.pdf",
            "source_text": "Form W-9 Request for Taxpayer ID",
            "sha256": "same-exact-hash",
            "ingested_at": "2026-07-01T10:00:00"
        }
        doc2 = {
            "id": "doc-2",
            "original_name": "W9_Blank.pdf",
            "source_text": "Form W-9 Request for Taxpayer ID",
            "sha256": "same-exact-hash",
            "ingested_at": "2026-07-02T10:00:00"
        }
        self.store.data["documents"].extend([doc1, doc2])

        res1 = self.store.add_form_template("doc-1")
        res2 = self.store.add_form_template("doc-2")

        self.assertEqual(res2["action"], "exact_duplicate")
        self.assertEqual(res2["family"]["attributes"]["exact_duplicate_count"], 1)
        self.assertEqual(len(res2["family"]["attributes"]["versions"]), 1)

    def test_explicit_form_bank_intake_keeps_blank_source_out_of_participant_files(self):
        source = Path(self.temp_dir.name) / "blank-consent.txt"
        source.write_text("CONSENT TO SHARE PROTECTED PERSONAL INFORMATION\nBlank reusable form\n")

        result = self.store.ingest(source, form_bank=True)

        self.assertEqual(result["status"], "filed")
        document = self.store.data["documents"][0]
        self.assertEqual(document["staging_disposition"]["kind"], "form_template")
        self.assertFalse([entity for entity in self.store.data["entities"] if entity["kind"] == "person"])
        families = self.store.form_bank_families()
        self.assertEqual(len(families), 1)
        self.assertEqual(families[0]["attributes"]["versions"][0]["document_id"], document["id"])

    def test_repeated_explicit_form_upload_is_counted_without_storing_a_second_source(self):
        source = Path(self.temp_dir.name) / "blank-consent.txt"
        source.write_text("CONSENT TO SHARE PROTECTED PERSONAL INFORMATION\nBlank reusable form\n")

        self.store.ingest(source, form_bank=True)
        result = self.store.ingest(source, form_bank=True)

        self.assertEqual(result["status"], "form_bank_duplicate")
        self.assertEqual(len(self.store.data["documents"]), 1)
        family = self.store.form_bank_families()[0]
        self.assertEqual(family["attributes"]["exact_duplicate_count"], 1)

    def test_legacy_form_catalog_event_migrates_to_form_bank_version(self):
        self.store.data["documents"].append({
            "id": "doc-legacy", "original_name": "TLS Intake Packet.pdf", "source_text": "TLS Intake Packet",
            "sha256": "legacy-hash", "ingested_at": "2026-01-01T10:00:00",
        })
        family = self.store._entity("form_template", "TLS Intake Packet")
        self.store._event("form_cataloged", family["id"], {"document_id": "doc-legacy"})

        families = self.store.form_bank_families()

        self.assertEqual(len(families[0]["attributes"]["versions"]), 1)
        self.assertTrue(families[0]["attributes"]["versions"][0]["is_current"])

if __name__ == "__main__":
    unittest.main()
