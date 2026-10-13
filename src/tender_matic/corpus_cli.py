"""Command-line tools for the local historical proposal corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tender_matic.corpus import (
    DEFAULT_EMBEDDING_MODEL,
    CorpusIndex,
    FastEmbedTextEmbedder,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Index and search a local proposal corpus.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Index phase 1 normalized proposals")
    index_parser.add_argument("--documents", required=True, type=Path)
    index_parser.add_argument("--database", required=True, type=Path)
    index_parser.add_argument("--metadata", type=Path, help="Optional local JSON metadata map")
    index_parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)

    search_parser = subparsers.add_parser("search", help="Search local proposal evidence")
    search_parser.add_argument("--database", required=True, type=Path)
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.add_argument("--language")
    search_parser.add_argument("--proposal-date-from")
    search_parser.add_argument("--proposal-date-to")
    search_parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)

    arguments = parser.parse_args()
    try:
        embedder = FastEmbedTextEmbedder(arguments.model)
        with CorpusIndex(arguments.database, embedder) as corpus:
            if arguments.command == "index":
                metadata = None
                if arguments.metadata:
                    metadata_document = json.loads(
                        arguments.metadata.read_text(encoding="utf-8")
                    )
                    if not isinstance(metadata_document, dict):
                        raise ValueError("Metadata file must contain a JSON object")
                    metadata = metadata_document.get("documents", metadata_document)
                    if not isinstance(metadata, dict):
                        raise ValueError("Metadata 'documents' field must be a JSON object")
                summary = corpus.index_normalized_directory(arguments.documents, metadata)
                print(json.dumps({
                    "indexed_documents": summary.indexed_documents,
                    "indexed_passages": summary.indexed_passages,
                    "skipped_documents": summary.skipped_documents,
                    "warnings": list(summary.warnings),
                }, indent=2, sort_keys=True))
                return 1 if summary.skipped_documents else 0

            matches = corpus.search(
                arguments.query,
                limit=arguments.limit,
                language=arguments.language,
                proposal_date_from=arguments.proposal_date_from,
                proposal_date_to=arguments.proposal_date_to,
            )
            rendered = []
            for match in matches:
                citation = corpus.resolve_citation(match.evidence_id)
                rendered.append({
                    "evidence_id": match.evidence_id,
                    "text": match.text,
                    "score": match.score,
                    "local_citation": {
                        "source": citation.relative_path,
                        "location": citation.source_location,
                        "proposal_date": citation.proposal_date,
                        "language": citation.language,
                    },
                })
            print(json.dumps(rendered, ensure_ascii=False, indent=2))
            return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())