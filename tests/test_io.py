import json
from pathlib import Path
import tempfile
import unittest
from searchlab.core import build_index, tokenize
from searchlab.io import read_corpus


class InputTests(unittest.TestCase):
    def test_bounded_json_duplicate_and_schema_failures(self):
        malformed = [
            b'[{"id":"a","text":"one","text":"two"}]',
            b'[{"id":"a","text":"x"},{"id":"a","text":"y"}]',
            b'{"id":"a","text":"x"}',
            b'[{"id":1,"text":"x"}]',
            b'[{"id":"a","text":"x","extra":true}]',
            b'[{"id":"a","text":"x","title":7}]',
            b"[" * 3000 + b"]" * 3000,
            b" " * (1024 * 1024 + 1),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "corpus.json"
            for data in malformed:
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    read_corpus(path)
            path.write_text(
                json.dumps([{"id": "a", "title": "Display only", "text": "Straße"}]),
                encoding="utf-8",
            )
            self.assertEqual(read_corpus(path), {"a": "Straße"})

    def test_exact_token_limits_and_combining_mark_policy(self):
        self.assertEqual(len(tokenize("ß" * 128)[0].term), 256)
        self.assertEqual(len(tokenize("ﬃ" * 85)[0].term), 255)
        with self.assertRaises(ValueError):
            tokenize("ﬃ" * 86)
        self.assertEqual(len(tokenize("a " * 4096)), 4096)
        self.assertEqual(tokenize("\u0301\u0308"), ())
        token = tokenize("a\u0301\u0308")[0]
        self.assertEqual((token.start, token.end), (0, 3))
        self.assertEqual(build_index({"empty": ""}).average_length, 0)


if __name__ == "__main__":
    unittest.main()
