"""Bounded Unicode positional indexing, Boolean/phrase queries and BM25."""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
import math
import re
from types import MappingProxyType
import unicodedata

MAX_DOCUMENTS = 256
MAX_DOCUMENT_CHARS = 20_000
MAX_CORPUS_CHARS = 200_000
MAX_DOCUMENT_TOKENS = 4096
MAX_QUERY_CHARS = 512
MAX_QUERY_TOKENS = 32
MODES = ("term", "and", "or", "phrase", "bm25")


@dataclass(frozen=True)
class Token:
    term: str
    position: int
    start: int
    end: int


def normalize(raw):
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", raw).casefold())


def tokenize(text, *, max_chars=MAX_DOCUMENT_CHARS, max_tokens=MAX_DOCUMENT_TOKENS):
    """Scan original code points first; normalize each token after recording spans.

    A token starts with isalnum(); following alphanumeric or Unicode category-M
    marks continue it. Underscores, apostrophes and punctuation are delimiters.
    Offsets are half-open Python Unicode-code-point indices, never UTF-16 units.
    """
    if not isinstance(text, str):
        raise TypeError("Text must be a string")
    if len(text) > max_chars:
        raise ValueError("Text exceeds the character limit")
    if any(unicodedata.category(c) == "Cs" for c in text):
        raise ValueError("Unpaired surrogate code points are not supported")
    tokens = []
    cursor = 0
    while cursor < len(text):
        if not text[cursor].isalnum():
            cursor += 1
            continue
        start = cursor
        cursor += 1
        while cursor < len(text) and (
            text[cursor].isalnum() or unicodedata.category(text[cursor]).startswith("M")
        ):
            cursor += 1
        if cursor - start > 128:
            raise ValueError("Original token exceeds 128 code points")
        term = normalize(text[start:cursor])
        if len(term) > 256:
            raise ValueError("Normalized token exceeds 256 code points")
        if len(tokens) >= max_tokens:
            raise ValueError("Token count exceeds the limit")
        tokens.append(Token(term, len(tokens), start, cursor))
    return tuple(tokens)


@dataclass(frozen=True)
class Document:
    doc_id: str
    text: str
    tokens: tuple[Token, ...]


@dataclass(frozen=True)
class Index:
    """Read-only state produced by build_index; as_dict returns detached data.

    Direct construction is a low-level operation: it does not validate or copy
    caller-owned mappings. Use build_index for checked, immutable snapshots.
    """

    documents: Mapping[str, Document]
    postings: Mapping[str, Mapping[str, tuple[int, ...]]]
    average_length: float

    def as_dict(self):
        return {
            "format_version": 1,
            "unicode_version": unicodedata.unidata_version,
            "normalization": "NFC(casefold(NFC(original token)))",
            "span_unit": "Unicode code points; half-open [start,end)",
            "document_count": len(self.documents),
            "average_length": self.average_length,
            "documents": {key: asdict(value) for key, value in self.documents.items()},
            "postings": {
                term: {doc_id: list(positions) for doc_id, positions in docs.items()}
                for term, docs in self.postings.items()
            },
        }


def build_index(documents):
    """Validate original strings and return independent, read-only nested state."""
    if not isinstance(documents, Mapping):
        raise TypeError("Documents must be a mapping of ID to original text")
    if len(documents) > MAX_DOCUMENTS:
        raise ValueError("Corpus exceeds 256 documents")
    if any(
        not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", key)
        for key in documents
    ):
        raise ValueError(
            "Document IDs require 1..64 ASCII letters, digits, dots, underscores or hyphens"
        )
    if any(not isinstance(value, str) for value in documents.values()):
        raise TypeError("Document values must be original text strings")
    if sum(len(value) for value in documents.values()) > MAX_CORPUS_CHARS:
        raise ValueError("Corpus exceeds 200000 code points")
    stored = {}
    collected = defaultdict(lambda: defaultdict(list))
    total = 0
    for doc_id, text in sorted(documents.items()):
        tokens = tokenize(text)
        stored[doc_id] = Document(doc_id, text, tokens)
        total += len(tokens)
        for token in tokens:
            collected[token.term][doc_id].append(token.position)
    postings = {
        term: {doc_id: tuple(positions) for doc_id, positions in sorted(docs.items())}
        for term, docs in sorted(collected.items())
    }
    return Index(
        MappingProxyType(stored),
        MappingProxyType(
            {term: MappingProxyType(docs) for term, docs in postings.items()}
        ),
        total / len(stored) if stored else 0.0,
    )


@dataclass(frozen=True)
class Match:
    positions: tuple[int, ...]
    start: int
    end: int


@dataclass(frozen=True)
class Contribution:
    term: str
    tf: int
    df: int
    document_count: int
    document_length: int
    average_length: float
    idf: float
    length_normalization: float
    saturation: float
    contribution: float


@dataclass(frozen=True)
class Hit:
    doc_id: str
    score: float | None
    matches: tuple[Match, ...]
    highlights: tuple[tuple[int, int], ...]
    explanation: tuple[Contribution, ...]


@dataclass(frozen=True)
class Response:
    mode: str
    query: str
    terms: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    hits: tuple[Hit, ...]
    k1: float
    b: float

    def as_dict(self):
        return asdict(self)


def merge_highlights(matches):
    intervals = []
    for start, end in sorted((match.start, match.end) for match in matches):
        if intervals and start <= intervals[-1][1]:
            intervals[-1] = (intervals[-1][0], max(end, intervals[-1][1]))
        else:
            intervals.append((start, end))
    return tuple(intervals)


def search(index, query, mode="bm25", *, k1=1.2, b=0.75):
    if mode not in MODES:
        raise ValueError("Mode must be term, and, or, phrase or bm25")
    for value, name, lower, upper in [(k1, "k1", 0.0, 10.0), (b, "b", 0.0, 1.0)]:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not lower <= value <= upper
        ):
            raise ValueError(f"{name} is outside the supported finite range")
    if k1 == 0:
        raise ValueError("k1 must be positive")
    terms = tuple(
        token.term
        for token in tokenize(
            query, max_chars=MAX_QUERY_CHARS, max_tokens=MAX_QUERY_TOKENS
        )
    )
    if mode == "term" and len(terms) > 1:
        raise ValueError("Term mode requires zero or one normalized token")
    if not terms:
        return Response(mode, query, terms, (), (), float(k1), float(b))
    unique = tuple(sorted(set(terms)))
    doc_sets = [set(index.postings.get(term, {})) for term in unique]
    candidates = (
        set.intersection(*doc_sets)
        if mode in ("term", "and", "phrase")
        else set.union(*doc_sets)
    )
    hits = []
    for doc_id in sorted(candidates):
        document = index.documents[doc_id]
        tokens = document.tokens
        matches = []
        if mode == "phrase":
            positions = {term: set(index.postings[term][doc_id]) for term in unique}
            for start in index.postings[terms[0]][doc_id]:
                if all(start + i in positions[term] for i, term in enumerate(terms)):
                    end = start + len(terms) - 1
                    matches.append(
                        Match(
                            tuple(range(start, end + 1)),
                            tokens[start].start,
                            tokens[end].end,
                        )
                    )
            if not matches:
                continue
        else:
            matched_positions = sorted(
                position
                for term in unique
                for position in index.postings.get(term, {}).get(doc_id, ())
            )
            matches = [
                Match((position,), tokens[position].start, tokens[position].end)
                for position in matched_positions
            ]
        score, explanation = None, []
        if mode == "bm25":
            n, dl, average = len(index.documents), len(tokens), index.average_length
            norm = 1 - b + b * dl / average
            for term in unique:
                posting = index.postings.get(term, {})
                df, tf = len(posting), len(posting.get(doc_id, ()))
                idf = math.log1p((n - df + 0.5) / (df + 0.5))
                saturation = tf * (k1 + 1) / (tf + k1 * norm) if tf else 0.0
                explanation.append(
                    Contribution(
                        term,
                        tf,
                        df,
                        n,
                        dl,
                        average,
                        idf,
                        norm,
                        saturation,
                        idf * saturation,
                    )
                )
            score = math.fsum(item.contribution for item in explanation)
        hits.append(
            Hit(
                doc_id,
                score,
                tuple(matches),
                merge_highlights(matches),
                tuple(explanation),
            )
        )
    if mode == "bm25":
        hits.sort(key=lambda hit: (-hit.score, hit.doc_id))
    return Response(
        mode, query, terms, tuple(sorted(candidates)), tuple(hits), float(k1), float(b)
    )
