import json
import tempfile
import unittest
from pathlib import Path

from itl.pack import grok_pack, load_jsonl, openai_pack, write_all


class PackTests(unittest.TestCase):
    def setUp(self):
        self.jsonl = Path(__file__).resolve().parents[1] / "samples" / "leads.jsonl"

    def test_load_sample(self):
        leads = load_jsonl(str(self.jsonl))
        self.assertEqual(len(leads), 3)
        self.assertEqual(leads[0].company, "Hughes Drywall")

    def test_grok_messages(self):
        leads = load_jsonl(str(self.jsonl))
        pack = grok_pack(leads, "drywall contractor chicago")
        self.assertEqual(pack["format"], "grok")
        self.assertEqual(pack["messages"][0]["role"], "system")
        self.assertIn("Do not invent", pack["messages"][0]["content"])

    def test_openai_request(self):
        leads = load_jsonl(str(self.jsonl))
        pack = openai_pack(leads, "drywall contractor chicago")
        self.assertIn("messages", pack["request"])

    def test_write_all(self):
        leads = load_jsonl(str(self.jsonl))
        with tempfile.TemporaryDirectory() as tmp:
            written = write_all(leads, tmp, profile="drywall contractor chicago")
            self.assertTrue(Path(written["grok"]).exists())
            self.assertTrue(Path(written["markdown"]).exists())
            data = json.loads(Path(written["grok"]).read_text())
            self.assertEqual(data["lead_count"], 3)


if __name__ == "__main__":
    unittest.main()
