# Tokenization and original spans

## Exact rule

Scan the original Python string by Unicode code-point index. A token begins at a character for which `str.isalnum()` is true. It continues while characters are alphanumeric or have Unicode general category beginning with `M` (combining marks). Leading marks that are not attached to an alphanumeric start are delimiters. Underscores, apostrophes, hyphens, periods, emoji and other nonqualifying characters separate tokens.

This deliberately simple rule is not Unicode word-boundary segmentation, grapheme segmentation or language-aware tokenization. A contiguous CJK run is one token. `can't` becomes `can`, `t`; `99.9` becomes `99`, `9`; `s3_bucket` becomes `s3`, `bucket`. There is no stopword removal, stemming, accent removal or transliteration.

Only after recording the original `[start,end)` span is each raw token transformed by:

```text
normalized = NFC(casefold(NFC(original[start:end])))
```

The Python operations are specified in the [Python 3.13 string documentation](https://docs.python.org/3.13/library/stdtypes.html#str.casefold) and [Unicode normalization documentation](https://docs.python.org/3.13/library/unicodedata.html). The measured interpreter's Unicode database is 15.1.0. A different Unicode database can change tokenization or normalization of some inputs; its version is stored in the index and environment.

## Expansion and composition

`Straße` has six original code points and normalizes to seven letters in `strasse`. The single ligature `ﬃ` case-folds to `ffi`. Decomposed `A` plus a ring composes to `å` after case folding, while its original span still contains both code points. `İ` folds to `i` plus a combining dot; the dot is not stripped. Greek capital sigma and final sigma normalize consistently under case folding.

The stored spans always index the original text. They are not offsets into a normalized copy, UTF-8 byte offsets or UTF-16 code units. The report uses `Array.from(originalText)` to slice by code point in JavaScript, including after non-BMP emoji. Highlight strings are inserted as text nodes; original text is not interpreted as HTML.

## Positions and phrases

Each token also has a zero-based position, independent of its character length. A phrase of normalized tokens `q[0..m)` matches at position `p` when every `q[i]` occurs at `p+i`. All punctuation and spacing between those original tokens are included in the phrase's original character span. Therefore `search engine` can match `search-engine` and `search, engine`.

Repeated phrase terms retain multiplicity and order. In `echo echo echo`, query `echo echo` matches positions `[0,1]` and `[1,2]`. Both occurrences are returned. Only display highlights merge overlapping or touching intervals; occurrence evidence is not discarded.

Empty or punctuation-only queries return no hits in every mode. AND's empty-query behavior is an explicit search convention, rather than the mathematical universal-set identity. Term mode accepts at most one normalized token. AND, OR and BM25 use unique query terms; phrases retain repetitions.

## Input limits

Unpaired surrogate code points are rejected. Raw tokens may contain at most 128 code points and normalized tokens at most 256. Both limits are checked because case folding can expand a token. Documents may contain at most 4,096 tokens; queries at most 32. Document titles are display metadata and are not indexed.
