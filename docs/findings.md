# Findings

The preserved run contains twelve owned synthetic documents, 152 tokens, 97 distinct normalized terms and fifteen recorded queries. It demonstrates index behavior under the declared rules; it does not evaluate general retrieval quality.

## Boolean candidates and phrase evidence

`cache` appears in four documents. AND query `cache latency` intersects that set with the latency postings and returns `d01`, `d09` and `d10`. BM25's OR-style candidate union contains five documents, adding `d03` and `d11`. The index diagram displays their actual token positions.

For phrase `a a`, eight documents contain `a`, but only `d07` contains adjacent repeated tokens. It has three overlapping occurrences. The phrase `echo echo` has two occurrences at original spans `[0,9)` and `[5,14)`, merged into `[0,14)` only for display. The phrase `search engine` matches three occurrences across two documents, including hyphen and comma separators.

## Ranking and ties

BM25 query `cache latency` returns `d09, d10, d01, d11, d03`. The first two documents are identical two-token strings and therefore have equal contributions and exact scores. Ascending IDs resolve the tie. The longer cache document has more cache occurrences, but its length normalization differs; this illustrates the declared formula rather than a human preference judgment.

Repeating `cache` in the query leaves results identical because ranking uses unique query terms. The empty document remains in the corpus statistics, producing `avgdl = 152/12`. These choices are exposed in every explanation and matter when comparing with other engines.

## Unicode and highlights

`strasse` matches both original `Straße` and `STRASSE`. `ffi` matches the single ligature `ﬃ`. A composed query for `ångström units` matches decomposed source characters without losing their original span. Greek sigma forms match under case folding. Emoji before a token do not shift highlights because spans and browser slicing use code points consistently.

These fixtures do not imply language-aware tokenization: punctuation splits words, accents are retained, and a contiguous CJK run remains one token. Exact term `arch` does not match inside `search`.

## Measured 256-document workload

The separate seeded corpus has 256 documents, nine of them empty, with 84,484 original code points, 13,791 tokens and 39 terms. All ten predetermined queries produce the same ordered document IDs and every occurrence/span in the independent scan and indexed paths. BM25 scores agree within 1e-12 relative and absolute tolerance. There are 147 raw observations; these are measured timings, not projected performance.

For rare term `needle`, 15 documents match and the indexed median is 0.0549 ms versus 3.0361 ms for the scanner. The common OR query `cache query index` returns 247 documents with 6,062 occurrences: the indexed median is 5.2601 ms, slightly slower than the scanner's 4.9585 ms. The common phrase `cache index` returns 193 documents and 389 occurrences, with medians 1.7155 ms and 4.4939 ms respectively. These cases show why selectivity and result construction matter within this implementation; no one method wins by the same factor across queries.

The recorded median build cost is 20.4081 ms (observed range 19.3169–27.0417 ms), excluded from query times. The independent scan re-tokenizes all documents per call, while the index uses retained postings and also constructs merged highlights and explanations. Those different workloads, the low-vocabulary artificial corpus and just seven warmed repetitions limit interpretation. This comparison does not measure an optimized pre-tokenized scanner, real traffic, concurrent throughput, RAM or search quality. [Every observed timing range](../results/scale/summary.csv) and [raw repetitions](../results/scale/measurements.csv) remain available.

## Scope

The index JSON is larger than the tiny corpus because it preserves original text, explicit positions and verbose metadata. The timings include rich evidence construction and are too small and narrow to support production performance claims. There are no external documents, relevance judgments, browsing history, user studies, compressed-index comparisons or universal search-quality conclusions.
