import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
