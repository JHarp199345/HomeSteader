from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from homesteader.exporting import export_logical_parts
from homesteader.packet_layouts import logical_document_parts
from homesteader.core import HomesteaderStore


class LogicalDocumentPartTests(unittest.TestCase):
    def test_tls_intake_layout_respects_multpage_policy_as_one_logical_record(self):
        structure = logical_document_parts(
            "TLS TAB 1 intake checklist ... TLS TAB 6 ... grievance policy ... housing search plan",
            47,
        )

        self.assertEqual(structure["layout_id"], "tls_intake_packet_v1")
        grievance = next(part for part in structure["parts"] if part["id"] == "grievance_policy")
        self.assertEqual((grievance["start_page"], grievance["end_page"]), (18, 26))
        self.assertEqual(len(structure["parts"]), 13)

    def test_selected_export_writes_only_requested_page_groups_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "intake.pdf"
            writer = PdfWriter()
            for _ in range(47):
                writer.add_blank_page(width=612, height=792)
            with source.open("wb") as handle:
                writer.write(handle)
            structure = logical_document_parts(
                "TLS TAB 1 intake checklist ... TLS TAB 6 ... grievance policy ... housing search plan",
                47,
            )
            document = {"stored_source_path": str(source), "logical_document_structure": structure}

            outputs = export_logical_parts(document, ["grievance_policy", "hmis_consent"], root / "export")

            self.assertEqual([path.name for path in outputs], [
                "05_HMIS consent to share protected personal information.pdf",
                "06_Grievance and ADA grievance policy_ forms_ and acknowledgement.pdf",
            ])
            self.assertEqual(len(PdfReader(outputs[0]).pages), 3)
            self.assertEqual(len(PdfReader(outputs[1]).pages), 9)

    def test_local_packet_definition_is_created_once_and_can_be_adjusted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HomesteaderStore(Path(directory) / "state.json")
            rules_path = store.initialize_logical_layouts()
            self.assertTrue(rules_path.exists())
            layouts = store.logical_layouts
            layouts[0]["parts"][0]["title"] = "Local packet index"
            store.save_logical_layouts(layouts)

            reloaded = HomesteaderStore(Path(directory) / "state.json")
            self.assertEqual(reloaded.logical_layouts[0]["parts"][0]["title"], "Local packet index")

    def test_closed_tls_intake_reports_only_missing_mapped_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HomesteaderStore(Path(directory) / "state.json")
            packet = store.start_intake_packet("TLS intake — fictional test")
            structure = logical_document_parts(
                "TLS TAB 1 intake checklist ... TLS TAB 6 ... grievance policy ... housing search plan",
                47,
                store.logical_layouts,
            )
            structure["parts"] = [part for part in structure["parts"] if part["id"] != "hmis_consent"]
            store.data["documents"].append({"id": "source-1", "logical_document_structure": structure})
            packet["document_ids"].append("source-1")
            store.close_intake_packet(packet["id"])

            status = store.packet_completeness(packet["id"])

            self.assertEqual(status["status"], "incomplete")
            self.assertEqual([part["id"] for part in status["missing"]], ["hmis_consent"])


if __name__ == "__main__":
    unittest.main()
