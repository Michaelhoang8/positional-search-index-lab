"""Bounded 256-document index-versus-retokenized-scan measurements."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from searchlab.core import build_index, search
from scan_reference import scan_search

SEED = 20261121
QUERIES = [
    {"id": "rare-term", "mode": "term", "query": "needle"},
    {"id": "common-term", "mode": "term", "query": "cache"},
    {"id": "rare-and", "mode": "and", "query": "needle cobalt"},
    {"id": "common-and", "mode": "and", "query": "cache index"},
    {"id": "rare-or", "mode": "or", "query": "needle absent"},
    {"id": "common-or", "mode": "or", "query": "cache query index"},
    {"id": "overlap-phrase", "mode": "phrase", "query": "echo echo"},
    {"id": "rare-phrase", "mode": "phrase", "query": "needle cobalt"},
    {"id": "common-phrase", "mode": "phrase", "query": "cache index"},
    {"id": "bm25", "mode": "bm25", "query": "cache latency"},
]


def corpus():
    rng = random.Random(SEED)
    vocabulary = "cache index query token graph node edge queue stream trace batch vector metric latency signal packet route worker commit journal reader writer lock page buffer storage codec frame clock window rank score term phrase search engine".split()
    result = {}
    for index in range(256):
        words = rng.choices(
            vocabulary,
            weights=[1 / (i + 1) for i in range(len(vocabulary))],
            k=rng.randint(40, 70),
        )
        if index % 16 == 0:
            words += ["needle", "cobalt", "index"]
        if index % 10 == 0:
            words += ["echo", "echo", "echo"]
        result[f"s{index:03d}"] = " ".join(words) if index % 31 else ""
    return result


def project_response(response):
    return [
        {
            "doc_id": hit.doc_id,
            "score": hit.score,
            "matches": [
                {
                    "positions": list(match.positions),
                    "start": match.start,
                    "end": match.end,
                }
                for match in hit.matches
            ],
        }
        for hit in response.hits
    ]


def reconcile(indexed, scanned):
    if [row["doc_id"] for row in indexed] != [row["doc_id"] for row in scanned]:
        raise AssertionError("Index/scan document ordering differs")
    for left, right in zip(indexed, scanned):
        if left["matches"] != right["matches"]:
            raise AssertionError("Index/scan positions or original spans differ")
        if (left["score"] is None) != (right["score"] is None):
            raise AssertionError("Index/scan score presence differs")
        if left["score"] is not None and not math.isclose(
            left["score"], right["score"], rel_tol=1e-12, abs_tol=1e-12
        ):
            raise AssertionError("Index/scan BM25 scores differ")


def write_json(path, value, compact=False):
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run(out):
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Choose a new empty scale directory")
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    sources = [
        "src/searchlab/core.py",
        "scripts/run_scale.py",
        "scripts/scan_reference.py",
    ]
    hashes = {
        name: hashlib.sha256(
            (ROOT / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        ).hexdigest()
        for name in sources
    }
    documents = corpus()
    write_json(out / "corpus.json", documents)
    documents = json.loads((out / "corpus.json").read_text(encoding="utf-8"))
    index = build_index(documents)
    timings, results, summary = [], [], []
    for repetition in range(7):
        begin = time.perf_counter_ns()
        build_index(documents)
        timings.append(
            {
                "query_id": "",
                "method": "build",
                "repetition": repetition,
                "order": 0,
                "elapsed_ns": time.perf_counter_ns() - begin,
            }
        )
    order_rng = random.Random(9182)
    for case in QUERIES:
        indexed = project_response(search(index, case["query"], case["mode"]))
        scanned = scan_search(documents, case["query"], case["mode"])
        reconcile(indexed, scanned)
        results.append({**case, "indexed": indexed, "scan": scanned})
        operations = {
            "indexed": lambda: project_response(
                search(index, case["query"], case["mode"])
            ),
            "scan": lambda: scan_search(documents, case["query"], case["mode"]),
        }
        for repetition in range(7):
            methods = list(operations)
            order_rng.shuffle(methods)
            for order, method in enumerate(methods):
                begin = time.perf_counter_ns()
                actual = operations[method]()
                elapsed = time.perf_counter_ns() - begin
                reconcile(indexed, actual)
                timings.append(
                    {
                        "query_id": case["id"],
                        "method": method,
                        "repetition": repetition,
                        "order": order,
                        "elapsed_ns": elapsed,
                    }
                )
        row = {
            **case,
            "documents": len(indexed),
            "occurrences": sum(len(r["matches"]) for r in indexed),
        }
        for method in operations:
            elapsed = [
                r["elapsed_ns"]
                for r in timings
                if r["query_id"] == case["id"] and r["method"] == method
            ]
            row[method + "_median_ns"] = statistics.median(elapsed)
            row[method + "_min_ns"] = min(elapsed)
            row[method + "_max_ns"] = max(elapsed)
        summary.append(row)
    write_json(out / "index.json", index.as_dict(), compact=True)
    write_json(out / "queries.json", QUERIES)
    write_json(out / "results.json", results, compact=True)
    for name, rows in [("measurements.csv", timings), ("summary.csv", summary)]:
        with (out / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=list(rows[0]), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
    write_json(
        out / "environment.json",
        {
            "started_utc": started,
            "completed_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "source_sha256_lf": hashes,
            "corpus_seed": SEED,
            "order_seed": 9182,
            "documents": len(documents),
            "characters": sum(map(len, documents.values())),
            "tokens": sum(len(d.tokens) for d in index.documents.values()),
            "unique_terms": len(index.postings),
            "queries": len(QUERIES),
            "timed_calls": len(timings),
            "corpus_json_bytes": (out / "corpus.json").stat().st_size,
            "index_json_bytes": (out / "index.json").stat().st_size,
            "scope": "Owned deterministic ASCII corpus. Indexed query includes production highlights/explanations and projection; baseline independently regex-tokenizes every original document per query and computes matching spans/scores. Build cost recorded separately, no file I/O or serialization in timers. Seven warmed repetitions, shuffled method order. Different internal work; no universal speedup or relevance-quality claim.",
        },
    )
    write_json(
        out / "manifest.json",
        [
            {
                "path": p.name,
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in sorted(out.iterdir())
            if p.is_file()
        ],
    )
    print(
        json.dumps(
            {
                "output": str(out),
                "documents": len(documents),
                "characters": sum(map(len, documents.values())),
                "timings": len(timings),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/scale-latest")
    run(parser.parse_args().out)
