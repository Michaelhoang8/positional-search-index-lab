"""Construct the index and preserve actual queries, postings, spans and timings."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from searchlab.core import build_index, search
from searchlab.io import read_corpus
from fixtures import CORPUS, QUERIES


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path, rows, columns):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(out):
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(
            "Choose a new empty directory; published evidence is preserved"
        )
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    sources = [
        "src/searchlab/core.py",
        "src/searchlab/io.py",
        "scripts/fixtures.py",
        "scripts/run_study.py",
    ]
    hashes = {
        name: hashlib.sha256(
            (ROOT / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        ).hexdigest()
        for name in sources
    }
    write_json(out / "corpus.json", CORPUS)
    write_json(out / "queries.json", QUERIES)
    documents = read_corpus(out / "corpus.json")
    index = build_index(documents)  # Warmup and the preserved index.
    timings = []
    for repetition in range(7):
        begin = time.perf_counter_ns()
        build_index(documents)
        timings.append(
            {
                "operation": "build",
                "query_id": "",
                "repetition": repetition,
                "elapsed_ns": time.perf_counter_ns() - begin,
            }
        )
    results, summary = [], []
    for case in QUERIES:
        response = search(index, case["query"], case["mode"])
        results.append({"id": case["id"], **response.as_dict()})
        elapsed = []
        for repetition in range(7):
            begin = time.perf_counter_ns()
            search(index, case["query"], case["mode"])
            duration = time.perf_counter_ns() - begin
            elapsed.append(duration)
            timings.append(
                {
                    "operation": "query",
                    "query_id": case["id"],
                    "repetition": repetition,
                    "elapsed_ns": duration,
                }
            )
        summary.append(
            {
                "query_id": case["id"],
                "mode": case["mode"],
                "query": case["query"],
                "candidate_documents": len(response.candidate_ids),
                "matched_documents": len(response.hits),
                "match_occurrences": sum(len(hit.matches) for hit in response.hits),
                "ranked_ids": "|".join(hit.doc_id for hit in response.hits),
                "median_ns": statistics.median(elapsed),
                "min_ns": min(elapsed),
                "max_ns": max(elapsed),
            }
        )
    write_json(out / "index.json", index.as_dict())
    write_json(out / "results.json", results)
    postings = [
        {
            "term": term,
            "doc_id": doc_id,
            "position": position,
            "start": index.documents[doc_id].tokens[position].start,
            "end": index.documents[doc_id].tokens[position].end,
        }
        for term, docs in index.postings.items()
        for doc_id, positions in docs.items()
        for position in positions
    ]
    write_csv(
        out / "postings.csv", postings, ["term", "doc_id", "position", "start", "end"]
    )
    write_csv(out / "summary.csv", summary, list(summary[0]))
    write_csv(out / "measurements.csv", timings, list(timings[0]))
    write_json(
        out / "environment.json",
        {
            "started_utc": started,
            "completed_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "unicode_database": unicodedata.unidata_version,
            "platform": platform.platform(),
            "source_sha256_lf": hashes,
            "documents": len(index.documents),
            "tokens": sum(len(doc.tokens) for doc in index.documents.values()),
            "unique_terms": len(index.postings),
            "average_document_length": index.average_length,
            "corpus_json_bytes": (out / "corpus.json").stat().st_size,
            "index_json_bytes": (out / "index.json").stat().st_size,
            "timed_calls": len(timings),
            "timing_scope": "Seven warmed in-memory builds and seven queries per case; query calls include tokenization, candidate selection, scores/explanations and highlights. File I/O and JSON serialization excluded. Fixed case order.",
            "provenance": "Owned synthetic text and predetermined queries; no human relevance judgments, retrieval-quality evaluation or external corpus",
            "seeds": "No random input generation in published study",
        },
    )
    write_json(
        out / "manifest.json",
        [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in sorted(out.iterdir())
            if path.is_file()
        ],
    )
    print(
        json.dumps(
            {
                "output": str(out),
                "documents": len(index.documents),
                "queries": len(QUERIES),
                "timed_calls": len(timings),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/latest")
    run(parser.parse_args().out)
