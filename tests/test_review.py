"""Hand-checked code-point spans, normalization and overlapping phrase limits."""
import unittest

from searchlab.core import build_index, search, tokenize


class ReviewTests(unittest.TestCase):
    def test_expansion_combining_marks_and_overlapping_phrases_keep_original_spans(self):
        text = '\U0001f6f0\ufe0f Straße, STRASSE — a\u030a a\u030a a\u030a!'
        index = build_index({'sample': text, 'empty': ''})
        word = search(index, 'strasse', 'term').hits[0]
        self.assertEqual([(m.start, m.end) for m in word.matches], [(3, 9), (11, 18)])
        self.assertEqual([text[m.start:m.end] for m in word.matches], ['Straße', 'STRASSE'])
        phrase = search(index, 'straße strasse', 'phrase').hits[0]
        self.assertEqual(phrase.matches[0].positions, (0, 1))
        self.assertEqual((phrase.matches[0].start, phrase.matches[0].end), (3, 18))
        overlap = search(index, 'Å å', 'phrase').hits[0]
        self.assertEqual([match.positions for match in overlap.matches], [(2, 3), (3, 4)])
        self.assertEqual([(m.start, m.end) for m in overlap.matches], [(21, 26), (24, 29)])
        self.assertEqual(overlap.highlights, ((21, 29),))
        self.assertEqual(text[21:29], 'a\u030a a\u030a a\u030a')

    def test_original_and_normalized_token_length_bounds_are_inclusive(self):
        original = 'ß' * 128
        token = tokenize(original)[0]
        self.assertEqual((token.start, token.end), (0, 128))
        self.assertEqual(token.term, 'ss' * 128)
        index = build_index({'maximum': original})
        self.assertEqual([hit.doc_id for hit in search(index, original, 'term').hits], ['maximum'])
        with self.assertRaises(ValueError):
            build_index({'too_long': 'ß' * 129})
        with self.assertRaises(ValueError):
            search(index, 'ß' * 129, 'term')


if __name__ == '__main__':
    unittest.main()
