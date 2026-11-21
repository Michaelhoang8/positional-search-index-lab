# Query execution and ranking

## Candidate documents

Term queries read one posting list. AND intersects the document IDs for the unique query terms. OR and BM25 take their union. Phrase queries intersect the term document sets, then use positional membership tests to verify every adjacent query term. A posting candidate is not necessarily a phrase hit: `a a` has eight candidate documents in this corpus, but only `d07` has the required adjacency.

Boolean and phrase results sort by ascending document ID. BM25 results sort by descending unrounded score, then ascending document ID for exact ties. Document IDs are case-sensitive ASCII identifiers. Posting positions and occurrence lists are sorted; no dictionary insertion order affects result ordering.

## Declared BM25 variant

The probabilistic relevance framework and BM25 are discussed by [Stephen Robertson and Hugo Zaragoza, *The Probabilistic Relevance Framework: BM25 and Beyond*](https://doi.org/10.1561/1500000019). This implementation uses the following explicit nonnegative IDF variant, which is also documented by [Lucene's BM25Similarity](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/BM25Similarity.html):

```text
IDF(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
length_factor = 1 - b + b * dl / avgdl
contribution(t,d) = IDF(t) * tf(t,d) * (k1 + 1)
                    / (tf(t,d) + k1 * length_factor)
score(d,q) = sum of contributions over unique normalized query terms
```

Defaults are `k1=1.2` and `b=0.75`. Supported parameters require finite `0 < k1 <= 10` and `0 <= b <= 1`; booleans are rejected. A missing term has `tf=0` and contributes zero. Explanations include `tf`, `df`, `N`, `dl`, `avgdl`, IDF, length factor, saturation and contribution for every unique query term, including missing ones.

`N` counts every indexed document, including empty documents. `avgdl` is the total token count divided by that same `N`, again including empties. This is an explicit study convention, not a claim to reproduce Lucene's field-level statistics or compressed norms. Exact token lengths and Python floating-point arithmetic are used. All-empty corpora have no matching candidates and do not divide by zero.

Query term frequency is deliberately not a boost: `cache cache latency` and `cache latency` produce identical hits and scores. This omits optional query-frequency weighting. Contributions use a deterministic sorted term order and `math.fsum`; displayed rounded values do not drive the ranking.

## Interpretation

The score combines term frequency saturation, corpus rarity and length normalization. It is a ranking weight, not a calibrated probability of relevance. The twelve synthetic documents have no human judgments; no precision, recall, MAP, NDCG, user satisfaction or universal retrieval-quality claim is derived from this study.

The independent BM25 test uses a separate document scan and the equivalent IDF expression `ln((2N+2)/(2df+1))`, with a rearranged term-frequency formula. It checks 100 generated corpora across several `k1` and `b` values. This validates implementation arithmetic for the declared formula, not the formula's suitability for a real corpus.
