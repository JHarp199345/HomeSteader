"""
Unit tests for Landlord & Move-In packet layout geometry extraction.
"""

import glob
import pathlib
import unittest
from homesteader.core import extract_pdf_layout_facts

class LandlordExtractionTests(unittest.TestCase):
    def test_move_in_landlord_packet_geometry_extraction(self):
        files = glob.glob("Homesteader Test Documents/HATEFUL_EIGHT_FICTIONAL_TRAINING_V3_MAPPED/01_FULL_MIXED_UPLOAD/*Move_In*.pdf")
        self.assertTrue(len(files) > 0, "Move-In test PDF files should be present in fictional training corpus")
        
        target_file = pathlib.Path(files[0])
        facts = extract_pdf_layout_facts(target_file)
        
        self.assertEqual(facts.get("document_type"), "move_in_packet")
        self.assertIn("participant", facts)
        self.assertIn("landlord", facts)
        self.assertIn("property_address", facts)
        self.assertIn("unit", facts)
        self.assertIn("monthly_rent", facts)
        self.assertIn("security_deposit", facts)
        self.assertIn("move_in_date", facts)
        
        # Provenance & value integrity checks
        self.assertTrue(facts["monthly_rent"].startswith("$"))
        self.assertTrue(facts["security_deposit"].startswith("$"))

if __name__ == "__main__":
    unittest.main()
