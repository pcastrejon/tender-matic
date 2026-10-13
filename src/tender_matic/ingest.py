"""Command-line entry point for local phase 1 ingestion."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tender_matic.ingestion import ingest_directory, write_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse local tender documents without model calls.")
    parser.add_argument("--input", required=True, type=Path, help="Directory containing source documents")
    parser.add_argument("--output", required=True, type=Path, help="Separate directory for JSON artifacts")
    arguments = parser.parse_args()

    try:
        result = ingest_directory(arguments.input)
        write_artifacts(result, arguments.output)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    summary = {
        "files": len(result.manifest),
        "documents": len(result.documents),
        "statuses": {
            status: sum(entry.status == status for entry in result.manifest)
            for status in ("parsed", "partial", "unsupported", "failed")
        },
        "output": str(arguments.output.resolve()),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())