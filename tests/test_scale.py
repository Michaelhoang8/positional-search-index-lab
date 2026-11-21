"""Reconcile the full bounded workload, independent scan results and raw timings."""

import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
import unittest

from searchlab.core import build_index, search

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_scale import QUERIES, corpus, project_response, reconcile
from scan_reference import scan_search

RUN = ROOT / "results/scale"


def load(name):
    return json.loads((RUN / name).read_text(encoding="utf-8"))


class ScaleEvidenceTests(unittest.TestCase):
    def test_original_corpus_postings_independent_results_and_timing_summaries(self):
        documents = load("corpus.json")
        self.assertEqual(documents, corpus())
        self.assertEqual(len(documents), 256)
        self.assertLessEqual(sum(map(len, documents.values())), 200_000)
        self.assertEqual(load("queries.json"), QUERIES)
        index = build_index(documents)
        self.assertEqual(json.loads(json.dumps(index.as_dict())), load("index.json"))
        with (RUN / "measurements.csv").open(encoding="utf-8", newline="") as stream:
            timing = list(csv.DictReader(stream))
        with (RUN / "summary.csv").open(encoding="utf-8", newline="") as stream:
            summary = {r["id"]: r for r in csv.DictReader(stream)}
        self.assertEqual(len(timing), 147)
        self.assertEqual(len([r for r in timing if r["method"] == "build"]), 7)
        self.assertTrue(all(int(r["elapsed_ns"]) > 0 for r in timing))
        records = load("results.json")
        self.assertEqual(len(records), len(QUERIES))
        for saved, case in zip(records, QUERIES):
            self.assertEqual({k: saved[k] for k in case}, case)
            actual = project_response(search(index, case["query"], case["mode"]))
            oracle = scan_search(documents, case["query"], case["mode"])
            for comparison in (oracle, saved["indexed"], saved["scan"]):
                reconcile(actual, comparison)
            row = summary[case["id"]]
            self.assertEqual(int(row["documents"]), len(actual))
            self.assertEqual(
                int(row["occurrences"]), sum(len(r["matches"]) for r in actual)
            )
            for method in ("indexed", "scan"):
                group = [
                    r
                    for r in timing
                    if r["query_id"] == case["id"] and r["method"] == method
                ]
                self.assertEqual(
                    sorted(int(r["repetition"]) for r in group), list(range(7))
                )
                elapsed = [int(r["elapsed_ns"]) for r in group]
                self.assertEqual(
                    float(row[method + "_median_ns"]), statistics.median(elapsed)
                )
                self.assertEqual(int(row[method + "_min_ns"]), min(elapsed))
                self.assertEqual(int(row[method + "_max_ns"]), max(elapsed))
            for repetition in range(7):
                group = [
                    r
                    for r in timing
                    if r["query_id"] == case["id"]
                    and int(r["repetition"]) == repetition
                ]
                self.assertEqual(sorted(int(r["order"]) for r in group), [0, 1])
        env = load("environment.json")
        self.assertEqual(env["documents"], len(documents))
        self.assertEqual(env["characters"], sum(map(len, documents.values())))
        self.assertEqual(
            env["tokens"], sum(len(d.tokens) for d in index.documents.values())
        )
        self.assertEqual(env["unique_terms"], len(index.postings))
        self.assertEqual(env["timed_calls"], len(timing))
        for name in ("corpus", "index"):
            self.assertEqual(
                env[name + "_json_bytes"], (RUN / (name + ".json")).stat().st_size
            )

    def test_exact_artifacts_and_measurement_source_hashes(self):
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


if __name__ == "__main__":
    unittest.main()
