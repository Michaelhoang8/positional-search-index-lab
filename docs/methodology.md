# Study and provenance

## Corpus and queries

All twelve documents and fifteen queries are fixed, owned synthetic examples. They intentionally exercise repeated words, mixed punctuation, empty text, Unicode composition/expansion, identical-score documents and an emoji before a matched token. Display titles are not indexed. These inspection examples are literal fixtures. The separate scale corpus described below is seeded synthetic data; test seeds generate further independent corpora.

The study writes `corpus.json`, reads those original strings through the bounded corpus loader, builds the index and preserves its complete token and posting representation. Every query result includes the normalized query terms, posting candidate IDs, final hit order, individual occurrences, merged highlights and BM25 explanations where applicable.

## Measurements and byte counts

One untimed build warms the construction path and supplies the preserved index. Seven fresh in-memory builds are timed. Each recorded query runs once before seven timed repetitions. This produces 112 actual `perf_counter_ns` observations: seven builds plus 105 queries.

Build timing includes tokenization, normalization, posting creation and document storage. Query timing includes query tokenization, candidate selection, occurrence construction, BM25 scoring/explanations and merged highlights. File I/O and JSON serialization are outside the timer. Query case order is fixed, and the corpus is tiny. The reported medians and observed ranges are descriptive, with no timing confidence interval, latency percentile, comparative speedup or production throughput claim.

The corpus JSON occupies 1,860 bytes and the exported index JSON 26,708 bytes. The latter deliberately duplicates original text and records verbose token metadata alongside postings. These actual UTF-8 file sizes are not RAM usage or a compressed-index evaluation. The study does not implement a persistent binary index, an index loader or incremental updates.

## Bounded scale workload

`results/scale` preserves a separate 256-document corpus generated with Python `random.Random(20261121)`. There are 84,484 original code points, 13,791 tokens and 39 distinct ASCII terms. Zipf-like vocabulary weights, periodic rare tokens, repeated phrases and nine empty documents create selective and common queries. The generator is an owned synthetic fixture, not a sample of real search traffic. The report explorer remains the smaller twelve-document corpus.

The independent scanner in `scripts/scan_reference.py` uses its own `[A-Za-z]+` regex, lowercasing and full document scans. That tokenizer agrees with production on this ASCII alphabet only; Unicode validation uses separate hand vectors. Phrase matches use consecutive token slices. BM25 is independently rearranged using `log((2*N + 2)/(2*df + 1))` and a divided saturation expression. Matching document order, every occurrence position/span and scores are reconciled outside the timer after every timed query. Floating scores permit 1e-12 relative and absolute tolerance for arithmetic/libm differences.

Both methods run once untimed for each query. Seven repetitions then execute each method once, shuffling their order with independent seed 9182. Seven fresh index builds are timed separately, for 147 total observations. The indexed timer includes the full production response (including highlights and per-term score explanations) plus projection to shared match fields. The scanner re-tokenizes the entire original corpus on every call and constructs positions/scores but no merged highlights or contribution objects. Neither timer includes file I/O or JSON serialization. This asymmetry is explicit: the experiment compares reuse of a built index with an unindexed scan; it is not a pure data-structure microbenchmark or an optimized scan-engine comparison.

Every original document, index posting, indexed/scan match projection and raw repetition remains inspectable. Corpus JSON is 88,071 bytes; compact index JSON is 903,960 bytes. Compact serialization is used only for larger files; the richer twelve-document snapshot uses indentation, so their file-size ratios should not be compared as an index scaling law. Neither size measures Python object memory. Build costs must be paid before indexed queries; query timings do not include their amortization. Seven warmed observations and a 39-term artificial corpus support descriptive medians/ranges only, not percentiles, confidence intervals, production throughput or universal speedups.

## Bounds

| Input | Limit |
|---|---:|
| Corpus JSON file | 1 MiB |
| Documents | 256 |
| Total original document code points | 200,000 |
| Original code points per document | 20,000 |
| Tokens per document | 4,096 |
| Raw token length | 128 code points |
| Normalized token length | 256 code points |
| Query length | 512 code points |
| Query tokens | 32 |
| Document ID | 1–64 permitted ASCII characters |

The loader reads at most its byte limit plus one, rejects duplicate object keys and document IDs, and requires an array of document objects with `id`, `text` and optional bounded `title`. Excessive JSON nesting becomes a clear input error. There is no query-language evaluation: an explicit mode and a plain query string select the operation. Parentheses and operator-looking words have no special syntax; punctuation remains a delimiter.

`build_index` copies the caller’s document mapping and returns read-only outer and nested mappings, frozen documents/tokens and tuple positions. `Index.as_dict()` returns a detached mutable serialization snapshot; changing it cannot change the live index. Direct `Index(...)` construction is a low-level dataclass operation that does not validate, copy or freeze supplied mappings. Callers who bypass `build_index` own those invariants and must not mutate their supplied state; the supported checked construction path is `build_index`. Concurrent mutation and updates are outside scope. All matching operations are bounded by the corpus and query limits rather than a streaming or unbounded-service design.

## Verification and reproducibility

The test suite performs 3,000 independent exhaustive document-scan comparisons for Boolean and phrase behavior, including original span locations. Separately computed BM25 scores cover 100 generated corpora. Known Unicode cases and exact phrase-overlap assertions complement the ASCII randomized oracle, whose regex tokenization is independent of production code.

Evidence tests rebuild the index from original strings, reconcile every query and posting row, check every original token slice, reconcile timing summaries, and verify raw file and normalized-source hashes. Unicode behavior is tied to the recorded interpreter/database; Python 3.13 is used in CI to reproduce the published Unicode 15.1.0 environment.

Source hashes are captured before the measured run with CRLF/CR normalized to LF. Generated JSON, CSV, HTML and SVG use LF before exact-byte hashing. The report provenance binds every run artifact, renderer source and output. Browser evidence is kept outside measured-source hashes. Fresh runs refuse a nonempty destination and preserve the published run; deterministic result artifacts are compared while new timings/timestamps remain distinct.
