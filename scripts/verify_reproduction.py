"""Compare fresh deterministic evidence while preserving measured run metadata."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def compare(actual, expected):
    if isinstance(expected, float):
        assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
    elif isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            compare(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for left, right in zip(actual, expected):
            compare(left, right)
    else:
        assert actual == expected


def verify(fresh, saved):
    for name in ("corpus.json", "queries.json", "index.json"):
        assert (fresh / name).read_bytes() == (saved / name).read_bytes(), name
    if (saved / "postings.csv").exists():
        assert (fresh / "postings.csv").read_bytes() == (
            saved / "postings.csv"
        ).read_bytes()
    compare(
        json.loads((fresh / "results.json").read_text(encoding="utf-8")),
        json.loads((saved / "results.json").read_text(encoding="utf-8")),
    )
    for row in json.loads((fresh / "manifest.json").read_text(encoding="utf-8")):
        data = (fresh / row["path"]).read_bytes()
        assert len(data) == row["bytes"]
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
    print(f"Reconciled deterministic evidence: {fresh} against {saved}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fresh", type=Path)
    parser.add_argument("saved", type=Path)
    args = parser.parse_args()
    verify(args.fresh, args.saved)
