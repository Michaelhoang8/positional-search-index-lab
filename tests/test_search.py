"""Independent exhaustive document-scan and separately computed BM25 oracles."""

import math
import random
import re
import unittest
from searchlab.core import build_index, normalize, search, tokenize


class SearchTests(unittest.TestCase):
    def test_index_mappings_and_serialized_snapshot_are_defensive(self):
        source = {"a": "red red blue"}
        index = build_index(source)
        source["a"] = "changed"
        before = search(index, "red", "term")
        snapshot = index.as_dict()
        snapshot["postings"]["red"]["a"].clear()
        snapshot["documents"]["a"]["tokens"][0]["start"] = 99
        snapshot["documents"]["a"]["text"] = "changed again"
        self.assertEqual(search(index, "red", "term"), before)
        self.assertEqual(index.documents["a"].text, "red red blue")
        with self.assertRaises(TypeError):
            index.documents["b"] = index.documents["a"]
        with self.assertRaises(TypeError):
            index.postings["red"]["a"] = ()
        with self.assertRaises(TypeError):
            index.postings["new"] = {}

    def test_unicode_original_spans_and_normalization_expansion(self):
        text = "📦 Straße ﬃ A\u030angstro\u0308m İ ΟΣ ος 99.9 can't s3_bucket"
        tokens = tokenize(text)
        self.assertEqual(
            [t.term for t in tokens],
            [
                "strasse",
                "ffi",
                "ångström",
                "i\u0307",
                "οσ",
                "οσ",
                "99",
                "9",
                "can",
                "t",
                "s3",
                "bucket",
            ],
        )
        originals = [text[t.start : t.end] for t in tokens]
        self.assertEqual(originals[:4], ["Straße", "ﬃ", "A\u030angstro\u0308m", "İ"])
        self.assertEqual(tokens[0].start, 2)  # Non-BMP emoji occupies one code point.
        self.assertEqual(tokens[0].end - tokens[0].start, 6)
        self.assertEqual(len(tokens[0].term), 7)
        self.assertEqual(tokenize("\u0301a")[0].start, 1)
        self.assertEqual([t.term for t in tokenize("東京大学")], ["東京大学"])
        self.assertEqual(normalize("A\u030a"), normalize("Å"))

    def test_overlap_and_punctuation_phrase_spans(self):
        index = build_index(
            {"a": "echo echo echo", "b": "search-engine; search, engine"}
        )
        hit = search(index, "echo echo", "phrase").hits[0]
        self.assertEqual([m.positions for m in hit.matches], [(0, 1), (1, 2)])
        self.assertEqual([(m.start, m.end) for m in hit.matches], [(0, 9), (5, 14)])
        self.assertEqual(hit.highlights, ((0, 14),))
        punct = search(index, "search engine", "phrase").hits[0]
        self.assertEqual(
            [index.documents["b"].text[m.start : m.end] for m in punct.matches],
            ["search-engine", "search, engine"],
        )

    def test_seeded_boolean_and_phrase_against_exhaustive_scan(self):
        rng = random.Random(314159)
        comparisons = 0
        for _ in range(100):
            documents = {
                f"d{i}": "".join(
                    rng.choice(["a", "B", "c"]) + rng.choice([" ", ",", "-"])
                    for _ in range(rng.randrange(10))
                )
                for i in range(8)
            }
            index = build_index(documents)
            reference = {
                key: list(re.finditer(r"[A-Za-z]+", value))
                for key, value in documents.items()
            }
            for _ in range(10):
                terms = [
                    rng.choice(["a", "b", "c", "missing"])
                    for _ in range(rng.randrange(5))
                ]
                query = " ".join(terms)
                for mode in ["and", "or", "phrase"]:
                    expected = {}
                    for doc_id, matches in reference.items():
                        words = [m.group().lower() for m in matches]
                        if not terms:
                            continue
                        if mode == "phrase":
                            spans = [
                                (
                                    matches[start].start(),
                                    matches[start + len(terms) - 1].end(),
                                )
                                for start in range(len(words) - len(terms) + 1)
                                if words[start : start + len(terms)] == terms
                            ]
                        else:
                            include = (
                                all(term in words for term in terms)
                                if mode == "and"
                                else any(term in words for term in terms)
                            )
                            spans = (
                                [
                                    (m.start(), m.end())
                                    for m in matches
                                    if m.group().lower() in terms
                                ]
                                if include
                                else []
                            )
                        if spans:
                            expected[doc_id] = spans
                    actual = search(index, query, mode)
                    self.assertEqual(
                        {
                            h.doc_id: [(m.start, m.end) for m in h.matches]
                            for h in actual.hits
                        },
                        expected,
                    )
                    comparisons += 1
        self.assertEqual(comparisons, 3000)

    def test_bm25_against_independent_formula_and_stable_ties(self):
        rng = random.Random(271828)
        for _ in range(100):
            documents = {
                f"d{i}": " ".join(
                    rng.choice(["red", "blue", "green"])
                    for _ in range(rng.randrange(9))
                )
                for i in range(7)
            }
            terms = set(rng.choices(["red", "blue", "absent"], k=3))
            query = " ".join(sorted(terms))
            k1, b = rng.choice([0.2, 1.2, 3]), rng.choice([0, 0.75, 1])
            actual = search(build_index(documents), query, k1=k1, b=b)
            words = {key: text.split() for key, text in documents.items()}
            average = sum(map(len, words.values())) / len(words)
            expected = {}
            for doc_id, values in words.items():
                score = 0.0
                for term in sorted(terms):
                    frequency = values.count(term)
                    df = sum(term in w for w in words.values())
                    if frequency:
                        idf = math.log((2 * len(words) + 2) / (2 * df + 1))
                        score += (
                            idf
                            * (k1 + 1)
                            / (1 + k1 * (1 - b + b * len(values) / average) / frequency)
                        )
                if score > 0:
                    expected[doc_id] = score
            self.assertEqual({h.doc_id for h in actual.hits}, set(expected))
            for hit in actual.hits:
                self.assertAlmostEqual(hit.score, expected[hit.doc_id], places=12)
                self.assertAlmostEqual(
                    hit.score, sum(c.contribution for c in hit.explanation), places=12
                )
        tied = build_index({"z": "red blue", "a": "red blue", "empty": ""})
        first = search(tied, "red blue")
        self.assertEqual([h.doc_id for h in first.hits], ["a", "z"])
        self.assertEqual(first.hits, search(tied, "red red blue").hits)
        self.assertEqual(first.hits[0].explanation[0].document_count, 3)
        self.assertEqual(first.hits[0].explanation[0].average_length, 4 / 3)

    def test_empty_inputs_exact_terms_and_bounds(self):
        index = build_index(
            {"empty": "", "punctuation": "...", "word": "search searching"}
        )
        for mode in ("term", "and", "or", "phrase", "bm25"):
            self.assertFalse(search(index, "...", mode).hits)
            self.assertFalse(search(build_index({}), "term", mode).hits)
        self.assertFalse(search(index, "arch", "term").hits)
        self.assertEqual(len(search(index, "search", "term").hits[0].matches), 1)
        invalid_documents = [
            {"bad id": "ok"},
            {"a": "x" * 129},
            {"a": "\ud800"},
            {"a": "a " * 4097},
            {"a": " " * 20001},
            {str(i): "" for i in range(257)},
            {str(i): " " * 20000 for i in range(11)},
        ]
        for documents in invalid_documents:
            with self.assertRaises(ValueError):
                build_index(documents)
        for query in ["x" * 513, "a " * 33, "\ud800"]:
            with self.assertRaises(ValueError):
                search(index, query)
        with self.assertRaises(ValueError):
            search(index, "two words", "term")
        for k1, b in [
            (0, 0.75),
            (math.inf, 0.75),
            (1.2, math.nan),
            (True, 0.75),
            (1.2, 2),
        ]:
            with self.assertRaises(ValueError):
                search(index, "word", k1=k1, b=b)


if __name__ == "__main__":
    unittest.main()
