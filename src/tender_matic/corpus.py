"""Company-local historical proposal index and hybrid evidence retrieval."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import struct
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol, Sequence


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


class TextEmbedder(Protocol):
    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedTextEmbedder:
    """Generate local multilingual E5 embeddings with fastembed."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as error:
            raise RuntimeError(
                "Local semantic retrieval requires the 'retrieval' extra: "
                "pip install -e '.[retrieval]'"
            ) from error

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [
            [float(value) for value in vector]
            for vector in self._model.embed(texts)
        ]

    def embed_query(self, text: str) -> list[float]:
        vector = next(self._model.query_embed(text), None)
        if vector is None:
            raise RuntimeError("The local embedding model returned no query vector")
        return [float(value) for value in vector]


class CorpusIndexError(ValueError):
    """Raised when a normalized proposal cannot safely enter the local corpus."""


@dataclass(frozen=True)
class IndexSummary:
    indexed_documents: int
    indexed_passages: int
    skipped_documents: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceMatch:
    """Local retrieval result; deliberately excludes source paths and client metadata."""

    evidence_id: str
    text: str
    score: float


@dataclass(frozen=True)
class LocalCitation:
    """Citation details resolved locally and never included in model context by default."""

    relative_path: str
    source_location: str
    proposal_date: str | None
    language: str | None


class CorpusIndex:
    """SQLite FTS5 plus a local vector table for a prototype-sized proposal corpus."""

    def __init__(self, database_path: Path, embedder: TextEmbedder) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._embedder = embedder
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        try:
            self._create_schema()
            self._ensure_model_identity()
        except Exception:
            self._connection.close()
            raise

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> CorpusIndex:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                source_document_id TEXT NOT NULL UNIQUE,
                relative_path TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status = 'parsed'),
                proposal_date TEXT,
                language TEXT
            );
            CREATE TABLE IF NOT EXISTS passages (
                row_id INTEGER PRIMARY KEY,
                evidence_id TEXT NOT NULL UNIQUE,
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                source_passage_id TEXT NOT NULL,
                source_location TEXT NOT NULL,
                text TEXT NOT NULL,
                vector BLOB NOT NULL,
                UNIQUE (document_id, source_passage_id)
            );
            CREATE TABLE IF NOT EXISTS corpus_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS documents_language_date
                ON documents(language, proposal_date);
            CREATE VIRTUAL TABLE IF NOT EXISTS passage_fts USING fts5(
                evidence_id UNINDEXED,
                text,
                tokenize = 'unicode61'
            );
            """
        )
        self._connection.commit()

    @property
    def _model_identity(self) -> str:
        configured_name = getattr(self._embedder, "model_name", None)
        if isinstance(configured_name, str) and configured_name:
            return configured_name
        embedder_type = type(self._embedder)
        return f"{embedder_type.__module__}.{embedder_type.__qualname__}"

    def _ensure_model_identity(self) -> None:
        row = self._connection.execute(
            "SELECT value FROM corpus_metadata WHERE key = 'embedding_model'"
        ).fetchone()
        if row is None:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO corpus_metadata(key, value) VALUES ('embedding_model', ?)",
                    (self._model_identity,),
                )
            return
        if row["value"] == self._model_identity:
            return
        passage_count = self.passage_count()
        if passage_count:
            raise CorpusIndexError(
                "Embedding model does not match this corpus; create a separate index "
                "or re-embed the corpus explicitly"
            )
        with self._connection:
            self._connection.execute(
                "UPDATE corpus_metadata SET value = ? WHERE key = 'embedding_model'",
                (self._model_identity,),
            )

    def _ensure_vector_dimensions(self, vectors: Sequence[Sequence[float]]) -> None:
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1 or not dimensions or next(iter(dimensions)) == 0:
            raise CorpusIndexError("Embedding provider returned inconsistent vector dimensions")
        current_dimension = str(next(iter(dimensions)))
        row = self._connection.execute(
            "SELECT value FROM corpus_metadata WHERE key = 'embedding_dimensions'"
        ).fetchone()
        if row is None:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO corpus_metadata(key, value) VALUES ('embedding_dimensions', ?)",
                    (current_dimension,),
                )
            return
        if row["value"] != current_dimension:
            raise CorpusIndexError("Embedding dimensions do not match the existing corpus index")

    def add_normalized_document(
        self,
        document: dict[str, Any],
        *,
        proposal_date: str | None = None,
        language: str | None = None,
    ) -> int:
        """Index one fully parsed normalized proposal. Return inserted passage count."""
        source_document_id = document.get("document_id")
        relative_path = document.get("relative_path")
        passages = document.get("passages")
        if not isinstance(source_document_id, str) or not source_document_id:
            raise CorpusIndexError("Normalized document is missing document_id")
        if not isinstance(relative_path, str) or not relative_path:
            raise CorpusIndexError("Normalized document is missing relative_path")
        if document.get("status") != "parsed":
            raise CorpusIndexError("Only fully parsed proposal documents may be indexed")
        if not isinstance(passages, list) or not passages:
            raise CorpusIndexError("Normalized proposal has no passages")
        if proposal_date is not None and not isinstance(proposal_date, str):
            raise CorpusIndexError("Proposal date metadata must be a YYYY-MM-DD string")
        if language is not None and not isinstance(language, str):
            raise CorpusIndexError("Language metadata must be a string")
        if proposal_date is not None:
            try:
                _validate_iso_date(proposal_date)
            except ValueError as error:
                raise CorpusIndexError(str(error)) from error
        if language is not None and not language.strip():
            raise CorpusIndexError("Language metadata must not be empty")

        existing = self._connection.execute(
            "SELECT id FROM documents WHERE source_document_id = ?",
            (source_document_id,),
        ).fetchone()
        if existing:
            return 0

        normalized_passages: list[tuple[str, str, str]] = []
        for passage in passages:
            if not isinstance(passage, dict):
                raise CorpusIndexError("Normalized passage must be an object")
            passage_id = passage.get("passage_id")
            text = passage.get("text")
            source_location = passage.get("source_location")
            if not all(isinstance(value, str) and value for value in
                       (passage_id, text, source_location)):
                raise CorpusIndexError("Normalized passage is missing required fields")
            normalized_passages.append((passage_id, text, source_location))

        vectors = self._embedder.embed_passages([item[1] for item in normalized_passages])
        if len(vectors) != len(normalized_passages):
            raise CorpusIndexError("Embedding provider returned an unexpected vector count")
        self._ensure_vector_dimensions(vectors)
        packed_vectors = [_pack_vector(vector) for vector in vectors]

        local_document_id = uuid.uuid4().hex
        with self._connection:
            self._connection.execute(
                """INSERT INTO documents
                   (id, source_document_id, relative_path, status, proposal_date, language)
                   VALUES (?, ?, ?, 'parsed', ?, ?)""",
                (local_document_id, source_document_id, relative_path, proposal_date, language),
            )
            for (source_passage_id, text, source_location), vector in zip(
                normalized_passages, packed_vectors, strict=True
            ):
                evidence_id = uuid.uuid4().hex
                cursor = self._connection.execute(
                    """INSERT INTO passages
                       (evidence_id, document_id, source_passage_id, source_location, text, vector)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        evidence_id,
                        local_document_id,
                        source_passage_id,
                        source_location,
                        text,
                        vector,
                    ),
                )
                self._connection.execute(
                    "INSERT INTO passage_fts(rowid, evidence_id, text) VALUES (?, ?, ?)",
                    (cursor.lastrowid, evidence_id, text),
                )
        return len(normalized_passages)

    def index_normalized_directory(
        self,
        documents_directory: Path,
        metadata: dict[str, dict[str, str | None]] | None = None,
    ) -> IndexSummary:
        """Index JSON artifacts emitted by phase 1; reject partial documents explicitly."""
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("Metadata must be a document-ID-to-metadata mapping")
        resolved_directory = documents_directory.resolve(strict=True)
        if not resolved_directory.is_dir():
            raise NotADirectoryError(f"Not a documents directory: {documents_directory}")

        indexed_documents = 0
        indexed_passages = 0
        skipped_documents = 0
        warnings: list[str] = []
        for path in sorted(resolved_directory.glob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(document, dict):
                    raise CorpusIndexError("Document artifact must be a JSON object")
                source_document_id = document.get("document_id")
                if not isinstance(source_document_id, str) or not source_document_id:
                    raise CorpusIndexError("Normalized document is missing document_id")
                document_metadata = (metadata or {}).get(source_document_id, {})
                if not isinstance(document_metadata, dict):
                    raise CorpusIndexError("Document metadata must be an object")
                unknown_metadata = set(document_metadata) - {"proposal_date", "language"}
                if unknown_metadata:
                    raise CorpusIndexError("Document metadata contains unsupported fields")
                if not all(
                    value is None or isinstance(value, str)
                    for value in document_metadata.values()
                ):
                    raise CorpusIndexError("Document metadata values must be strings or null")
                inserted = self.add_normalized_document(
                    document,
                    proposal_date=document_metadata.get("proposal_date"),
                    language=document_metadata.get("language"),
                )
            except (OSError, UnicodeError, json.JSONDecodeError, CorpusIndexError) as error:
                skipped_documents += 1
                warnings.append(f"{path.name}: {error}")
                continue
            if inserted:
                indexed_documents += 1
                indexed_passages += inserted

        return IndexSummary(indexed_documents, indexed_passages, skipped_documents, tuple(warnings))

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        lexical_weight: float = 0.5,
        semantic_weight: float = 0.5,
        rrf_constant: int = 60,
        language: str | None = None,
        proposal_date_from: str | None = None,
        proposal_date_to: str | None = None,
    ) -> list[EvidenceMatch]:
        """Return a reciprocal-rank fusion of local FTS5 and local vector results."""
        query = query.strip()
        if not query:
            raise ValueError("Search query must not be empty")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if lexical_weight < 0 or semantic_weight < 0 or lexical_weight + semantic_weight == 0:
            raise ValueError("At least one non-negative retrieval weight must be positive")
        metadata_sql, metadata_parameters = _metadata_filter_sql(
            language=language,
            proposal_date_from=proposal_date_from,
            proposal_date_to=proposal_date_to,
        )

        terms = _TOKEN_PATTERN.findall(query)
        if not terms:
            raise ValueError("Search query contains no searchable terms")
        fts_query = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
        candidate_limit = max(limit * 10, 50)
        lexical_rows = self._connection.execute(
            """SELECT p.evidence_id, p.text, bm25(passage_fts) AS rank
               FROM passage_fts
               JOIN passages AS p ON p.row_id = passage_fts.rowid
                    JOIN documents AS d ON d.id = p.document_id
                    WHERE passage_fts MATCH ?""" + metadata_sql + """
               ORDER BY rank ASC
               LIMIT ?""",
                (fts_query, *metadata_parameters, candidate_limit),
        ).fetchall()

        query_vector = self._embedder.embed_query(query)
        query_vector = _normalize_vector(query_vector)
        vector_rows = self._connection.execute(
                """SELECT p.evidence_id, p.text, p.vector
                    FROM passages AS p
                    JOIN documents AS d ON d.id = p.document_id""" + metadata_sql,
                metadata_parameters,
        ).fetchall()
        semantic_scores = [
            (row["evidence_id"], row["text"], _cosine_similarity(
                query_vector, _unpack_vector(row["vector"])
            ))
            for row in vector_rows
        ]
        semantic_rows = sorted(semantic_scores, key=lambda item: (-item[2], item[0]))[
            :candidate_limit
        ]

        combined: dict[str, tuple[str, float]] = {}
        for rank, row in enumerate(lexical_rows, start=1):
            score = lexical_weight / (rrf_constant + rank)
            combined[row["evidence_id"]] = (row["text"], score)
        for rank, (evidence_id, text, _) in enumerate(semantic_rows, start=1):
            score = semantic_weight / (rrf_constant + rank)
            previous_text, previous_score = combined.get(evidence_id, (text, 0.0))
            combined[evidence_id] = (previous_text, previous_score + score)

        ordered = sorted(combined.items(), key=lambda item: (-item[1][1], item[0]))[:limit]
        return [EvidenceMatch(evidence_id, text, score) for evidence_id, (text, score) in ordered]

    def resolve_citation(self, evidence_id: str) -> LocalCitation:
        """Resolve an opaque evidence ID to source metadata for local display only."""
        row = self._connection.execute(
            """SELECT d.relative_path, p.source_location, d.proposal_date, d.language
               FROM passages AS p
               JOIN documents AS d ON d.id = p.document_id
               WHERE p.evidence_id = ?""",
            (evidence_id,),
        ).fetchone()
        if row is None:
            raise KeyError("Unknown evidence ID")
        return LocalCitation(
            relative_path=row["relative_path"],
            source_location=row["source_location"],
            proposal_date=row["proposal_date"],
            language=row["language"],
        )

    def passage_count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS count FROM passages").fetchone()
        return int(row["count"])


def _normalize_vector(vector: Sequence[float]) -> list[float]:
    values = [float(value) for value in vector]
    if not values or any(not math.isfinite(value) for value in values):
        raise CorpusIndexError("Embedding vector must contain finite values")
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude == 0:
        raise CorpusIndexError("Embedding vector must not be all zeroes")
    return [value / magnitude for value in values]


def _pack_vector(vector: Sequence[float]) -> bytes:
    normalized = _normalize_vector(vector)
    return struct.pack(f"<{len(normalized)}f", *normalized)


def _unpack_vector(vector_bytes: bytes) -> list[float]:
    if len(vector_bytes) % 4:
        raise CorpusIndexError("Stored embedding has an invalid byte length")
    size = len(vector_bytes) // 4
    if size == 0:
        raise CorpusIndexError("Stored embedding is empty")
    return list(struct.unpack(f"<{size}f", vector_bytes))


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise CorpusIndexError("Embedding dimensions do not match")
    return sum(a * b for a, b in zip(left, right, strict=True))


def _validate_iso_date(value: str) -> None:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Proposal dates and date filters must use YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ValueError("Proposal dates and date filters must use YYYY-MM-DD")


def _metadata_filter_sql(
    *,
    language: str | None,
    proposal_date_from: str | None,
    proposal_date_to: str | None,
) -> tuple[str, tuple[str, ...]]:
    conditions: list[str] = []
    parameters: list[str] = []
    if language is not None:
        normalized_language = language.strip()
        if not normalized_language:
            raise ValueError("Language filter must not be empty")
        conditions.append("LOWER(d.language) = LOWER(?)")
        parameters.append(normalized_language)
    if proposal_date_from is not None:
        _validate_iso_date(proposal_date_from)
        conditions.append("d.proposal_date >= ?")
        parameters.append(proposal_date_from)
    if proposal_date_to is not None:
        _validate_iso_date(proposal_date_to)
        conditions.append("d.proposal_date <= ?")
        parameters.append(proposal_date_to)
    if proposal_date_from and proposal_date_to and proposal_date_from > proposal_date_to:
        raise ValueError("proposal_date_from must not be later than proposal_date_to")
    if not conditions:
        return "", ()
    return " AND " + " AND ".join(conditions), tuple(parameters)