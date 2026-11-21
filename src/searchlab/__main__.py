import argparse
import json
from pathlib import Path
from .core import MODES, build_index, search
from .io import read_corpus


def main():
    parser = argparse.ArgumentParser(
        description="Build or query a bounded original-document corpus"
    )
    parser.add_argument("operation", choices=["build", "query"])
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--query", default="")
    parser.add_argument("--mode", choices=MODES, default="bm25")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        index = build_index(read_corpus(args.corpus))
        result = (
            index.as_dict()
            if args.operation == "build"
            else search(index, args.query, args.mode).as_dict()
        )
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
        else:
            print(text, end="")
    except (ValueError, TypeError, OSError, RecursionError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
