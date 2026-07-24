"""
Unit and integration tests for Operator Identity and Foreign-Document Set-Aside feature.
Verifies against clean test set documents #4 and #9.
"""

import pathlib
import tempfile
import unittest

from homesteader.core import HomesteaderStore

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFA_DIR = ROOT / "Homesteader Test Documents/CLEAN_TEST_SET/CFA"


class OperatorAndForeignDocsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = pathlib.Path(self.temp_dir.name) / "test_state.json"
        self.store = HomesteaderStore(self.state_file)
        # Seed canonical operator name and registered alias "Jessie Harper"
        self.store.set_operator_identity("Jesse Harper", aliases=["Jessie Harper"], confirmed=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_doc_4_operator_alias_jessie_harper_files_normally(self):
        doc4_path = CFA_DIR / "CFA_02-06-2026_H-TRAIN-0004_Jasmine_Morales.pdf"
        self.assertTrue(doc4_path.exists(), "Doc #4 fixture must exist")

        res = self.store.ingest(doc4_path)
        self.assertNotEqual(res.get("status"), "set_aside", "Doc #4 with operator alias 'Jessie Harper' must NOT be set aside")
        
        # Verify document was created in store data
        docs = [d for d in self.store.data["documents"] if d["original_name"] == doc4_path.name]
        self.assertEqual(len(docs), 1, "Doc #4 must be recorded in store documents")

        # Verify no set-aside log or events were written for Doc #4
        set_aside_dir = self.state_file.parent / "set_aside"
        set_aside_file = set_aside_dir / doc4_path.name
        self.assertFalse(set_aside_file.exists(), "Doc #4 must NOT be placed in set_aside/")

    def test_doc_9_stranger_caseworker_dana_cortez_is_set_aside_with_zero_entities(self):
        doc9_path = pathlib.Path(self.temp_dir.name) / "CFA_03-03-2026_H-TRAIN-0006_Casey_Reed.txt"
        doc9_path.write_text(
            "Client Financial Assistance Check Request Form\n"
            "Client Name: Casey Reed\n"
            "HMIS ID #: H-TRAIN-0006\n"
            "Submitted By:\n"
            "Dana Cortez, Caseworker Dana Cortez 03/03/2026\n"
        )

        initial_doc_count = len(self.store.data["documents"])
        initial_entity_count = len(self.store.data["entities"])
        initial_rel_count = len(self.store.data["relationships"])

        res = self.store.ingest(doc9_path)
        self.assertEqual(res.get("status"), "set_aside", "Doc #9 with stranger 'Dana Cortez' must be set aside")

        # 1. Verify set_aside/ folder and file existence
        set_aside_dir = self.state_file.parent / "set_aside"
        set_aside_file = set_aside_dir / doc9_path.name
        self.assertTrue(set_aside_file.exists(), "Foreign doc #9 must be in set_aside/")

        # 2. Verify _WHY_THESE_ARE_HERE.txt line
        why_log = set_aside_dir / "_WHY_THESE_ARE_HERE.txt"
        self.assertTrue(why_log.exists())
        log_text = why_log.read_text()
        self.assertIn(doc9_path.name, log_text)
        self.assertIn('caseworker on document is "Dana Cortez"', log_text)
        self.assertIn('operator is "Jesse Harper"', log_text)

        # 3. Verify exactly one ledger event foreign_document_set_aside
        events = [e for e in self.store.data["ledger_events"] if e.get("type") == "foreign_document_set_aside"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["details"]["doc_caseworker_name"], "Dana Cortez")
        self.assertEqual(events[0]["details"]["operator"], "Jesse Harper")

        # 4. Verify ZERO entities, relationships, or document records created for foreign doc
        self.assertEqual(len(self.store.data["documents"]), initial_doc_count, "Zero document records for foreign doc")
        self.assertEqual(len(self.store.data["entities"]), initial_entity_count, "Zero entities for foreign doc")
        self.assertEqual(len(self.store.data["relationships"]), initial_rel_count, "Zero relationships for foreign doc")

    def test_document_without_caseworker_files_normally(self):
        # Correctness Note 2: Docs without a caseworker field file normally (not set aside)
        doc_path = pathlib.Path(self.temp_dir.name) / "no_caseworker_doc.txt"
        doc_path.write_text("Tenant: Casey Reed\nHMIS ID #: H-TRAIN-0006\nRent: $1000")

        res = self.store.ingest(doc_path)
        self.assertNotEqual(res.get("status"), "set_aside", "Doc without caseworker field must NOT be set aside")

    def test_pulse_closure_records_removal_event(self):
        doc9_path = pathlib.Path(self.temp_dir.name) / "CFA_03-03-2026_H-TRAIN-0006_Casey_Reed.txt"
        doc9_path.write_text(
            "Client Financial Assistance Check Request Form\n"
            "Client Name: Casey Reed\n"
            "Submitted By:\n"
            "Dana Cortez, Caseworker Dana Cortez 03/03/2026\n"
        )
        self.store.ingest(doc9_path)

        set_aside_file = self.state_file.parent / "set_aside" / doc9_path.name
        self.assertTrue(set_aside_file.exists())

        # Human clears file from set_aside in Finder
        set_aside_file.unlink()

        # Pulse check detects removal
        removed_count = self.store.check_set_aside_cleared_pulse()
        self.assertEqual(removed_count, 1)

        removed_events = [e for e in self.store.data["ledger_events"] if e.get("type") == "foreign_document_removed"]
        self.assertEqual(len(removed_events), 1)
        self.assertEqual(removed_events[0]["details"]["filename"], doc9_path.name)


if __name__ == "__main__":
    unittest.main()
