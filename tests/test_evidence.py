import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import unittest

from searchlab.core import build_index, normalize, search
from searchlab.io import read_corpus

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/published"


def load(name):
    return json.loads((RUN / name).read_text(encoding="utf-8"))


def assert_nested_close(test, actual, expected):
    """Keep structural evidence exact, allowing platform libm final-bit changes."""
    if isinstance(expected, float):
        test.assertTrue(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12))
    elif isinstance(expected, dict):
        test.assertEqual(actual.keys(), expected.keys())
        for key in expected:
            assert_nested_close(test, actual[key], expected[key])
    elif isinstance(expected, list):
        test.assertEqual(len(actual), len(expected))
        for left, right in zip(actual, expected):
            assert_nested_close(test, left, right)
    else:
        test.assertEqual(actual, expected)


class EvidenceTests(unittest.TestCase):
    def test_postings_original_spans_queries_and_timings_reconcile(self):
        index = build_index(read_corpus(RUN / "corpus.json"))
        self.assertEqual(json.loads(json.dumps(index.as_dict())), load("index.json"))
        for document in index.documents.values():
            for token in document.tokens:
                self.assertEqual(
                    normalize(document.text[token.start : token.end]), token.term
                )
                self.assertIn(
                    token.position, index.postings[token.term][document.doc_id]
                )
        with (RUN / "postings.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(
            len(rows), sum(len(d.tokens) for d in index.documents.values())
        )
        for row in rows:
            token = index.documents[row["doc_id"]].tokens[int(row["position"])]
            self.assertEqual(
                (row["term"], int(row["start"]), int(row["end"])),
                (token.term, token.start, token.end),
            )
        with (RUN / "summary.csv").open(encoding="utf-8", newline="") as stream:
            summary = {row["query_id"]: row for row in csv.DictReader(stream)}
        with (RUN / "measurements.csv").open(encoding="utf-8", newline="") as stream:
            timing = list(csv.DictReader(stream))
        self.assertEqual(len(timing), 112)
        self.assertEqual(len([t for t in timing if t["operation"] == "build"]), 7)
        self.assertTrue(all(int(row["elapsed_ns"]) > 0 for row in timing))
        stored = {r["id"]: r for r in load("results.json")}
        for case in load("queries.json"):
            response = search(index, case["query"], case["mode"])
            observed = {"id": case["id"], **json.loads(json.dumps(response.as_dict()))}
            assert_nested_close(self, observed, stored[case["id"]])
            row = summary[case["id"]]
            self.assertEqual(int(row["matched_documents"]), len(response.hits))
            self.assertEqual(
                int(row["candidate_documents"]), len(response.candidate_ids)
            )
            self.assertEqual(
                int(row["match_occurrences"]),
                sum(len(h.matches) for h in response.hits),
            )
            self.assertEqual(
                row["ranked_ids"], "|".join(h.doc_id for h in response.hits)
            )
            elapsed = [
                int(t["elapsed_ns"]) for t in timing if t["query_id"] == case["id"]
            ]
            self.assertEqual(len(elapsed), 7)
            self.assertEqual(float(row["median_ns"]), statistics.median(elapsed))
            self.assertEqual(int(row["min_ns"]), min(elapsed))
            self.assertEqual(int(row["max_ns"]), max(elapsed))
        env = load("environment.json")
        self.assertEqual(env["corpus_json_bytes"], (RUN / "corpus.json").stat().st_size)
        self.assertEqual(env["index_json_bytes"], (RUN / "index.json").stat().st_size)

    def test_source_artifact_and_visual_provenance(self):
        for row in load("manifest.json"):
            data = (RUN / row["path"]).read_bytes()
            self.assertEqual(len(data), row["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])
            self.assertNotIn(b"\r", data)
        for name, expected in load("environment.json")["source_sha256_lf"].items():
            data = (
                (ROOT / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            )
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
        visual = json.loads(
            (ROOT / "docs/assets/provenance.json").read_text(encoding="utf-8")
        )
        for group in ("inputs", "outputs"):
            for name, expected in visual[group].items():
                data = (ROOT / name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
                self.assertNotIn(b"\r", data)
        script = (
            (ROOT / "scripts/build_report.py")
            .read_bytes()
            .replace(b"\r\n", b"\n")
            .replace(b"\r", b"\n")
        )
        self.assertEqual(hashlib.sha256(script).hexdigest(), visual["source_sha256_lf"])

    def test_cli_exact_queries_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "results.json"
            command = [
                sys.executable,
                "-m",
                "searchlab",
                "query",
                str(RUN / "corpus.json"),
                "--query",
                "echo echo",
                "--mode",
                "phrase",
                "--output",
                str(output),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = output.read_bytes()
            parsed = json.loads(original)
            self.assertEqual(parsed["hits"][0]["highlights"], [[0, 14]])
            self.assertEqual(
                subprocess.run(command, capture_output=True, timeout=15).returncode, 2
            )
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
