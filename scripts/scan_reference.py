"""Independent ASCII document-scan baseline for the bounded scale fixture only."""

import math
import re


def scan_search(documents, query, mode):
    # Deliberately retokenize original ASCII text on every query. This models
    # an unindexed scan, not a second index with cached token positions.
    matches = {
        key: list(re.finditer(r"[A-Za-z]+", text)) for key, text in documents.items()
    }
    words = {
        key: [m.group().lower() for m in values] for key, values in matches.items()
    }
    terms = [m.group().lower() for m in re.finditer(r"[A-Za-z]+", query)]
    unique = sorted(set(terms))
    if not terms:
        return []
    n = len(words)
    average = sum(len(value) for value in words.values()) / n
    frequencies = {
        term: sum(term in value for value in words.values()) for term in unique
    }
    result = []
    for doc_id in sorted(words):
        sequence, locations = words[doc_id], matches[doc_id]
        occurrences = []
        if mode == "phrase":
            for start in range(len(sequence) - len(terms) + 1):
                if sequence[start : start + len(terms)] == terms:
                    end = start + len(terms) - 1
                    occurrences.append(
                        {
                            "positions": list(range(start, end + 1)),
                            "start": locations[start].start(),
                            "end": locations[end].end(),
                        }
                    )
        else:
            include = (
                all(term in sequence for term in unique)
                if mode in ("and", "term")
                else any(term in sequence for term in unique)
            )
            if include:
                occurrences = [
                    {
                        "positions": [position],
                        "start": match.start(),
                        "end": match.end(),
                    }
                    for position, match in enumerate(locations)
                    if sequence[position] in unique
                ]
        if not occurrences:
            continue
        score = None
        if mode == "bm25":
            values = []
            for term in unique:
                tf = sequence.count(term)
                if tf:
                    idf = math.log((2 * n + 2) / (2 * frequencies[term] + 1))
                    values.append(
                        idf
                        * 2.2
                        / (1 + 1.2 * (0.25 + 0.75 * len(sequence) / average) / tf)
                    )
            score = math.fsum(values)
        result.append({"doc_id": doc_id, "score": score, "matches": occurrences})
    if mode == "bm25":
        result.sort(key=lambda row: (-row["score"], row["doc_id"]))
    return result
