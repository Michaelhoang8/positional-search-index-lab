"""Bounded original-corpus JSON input, with explicit duplicate rejection."""

import json
from pathlib import Path

MAX_JSON_BYTES = 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def read_corpus(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("Corpus JSON exceeds 1 MiB")
    try:
        rows = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
    except RecursionError as error:
        raise ValueError("Corpus JSON exceeds the decoder nesting limit") from error
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError("Corpus must be an array of at most 256 document objects")
    result = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) - {"id", "text", "title"}
            or not {"id", "text"} <= set(row)
        ):
            raise ValueError("Each document needs id/text and optional title")
        doc_id, text = row["id"], row["text"]
        if not isinstance(doc_id, str) or not isinstance(text, str):
            raise ValueError("Document id and text must be strings")
        if doc_id in result:
            raise ValueError("Duplicate document ID")
        if "title" in row and (
            not isinstance(row["title"], str) or len(row["title"]) > 200
        ):
            raise ValueError(
                "Optional title must be a string of at most 200 code points"
            )
        result[doc_id] = text
    return result
