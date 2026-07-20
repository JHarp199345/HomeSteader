import tempfile
import unittest
from pathlib import Path

from homesteader.core import HomesteaderStore


class ReconciliationTests(unittest.TestCase):
    def test_hmis_confirmation_replaces_temporary_id_without_replacing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HomesteaderStore(Path(directory) / "state.json")
            temporary = store.create_temporary_file("Jasmine Morales")
            confirmed = store.confirm_hmis_identity(temporary["person_id"], "H-000042")
            self.assertEqual(confirmed["replaced_temporary_id"], "T-000001")
            self.assertEqual(confirmed["participant_ledger_id"], temporary["participant_ledger_id"])
            found = store.search_files("H-000042")
            self.assertEqual(found[0]["status"], "confirmed")
            self.assertIsNone(found[0]["temporary_id"])


if __name__ == "__main__":
    unittest.main()
