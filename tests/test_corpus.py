import json
import tempfile
import unittest
from pathlib import Path
from typing import Sequence

from tender_matic.corpus import CorpusIndex, CorpusIndexError


class FakeEmbedder:
    """Small deterministic semantic fixture; no model downloads or network use."""

    def __init__(self) -> None:
        self._topic_vectors = {
            "identity": [1.0, 0.0, 0.0],
            "payments": [0.0, 1.0, 0.0],
            "security": [0.0, 0.0, 1.0],
        }

    def _vector(self, text: str) -> list[float]:
        normalized = text.casefold()
        if any(term in normalized for term in ("identity", "authentication", "login")):
            return self._topic_vectors["identity"]
        if any(term in normalized for term in ("payment", "invoice", "billing")):
            return self._topic_vectors["payments"]
        if any(term in normalized for term in ("security", "encryption", "secure")):
            return self._topic_vectors["security"]
        return [1.0, 1.0, 1.0]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class DifferentFakeEmbedder(FakeEmbedder):
    pass


def normalized_document(
    source_document_id: str,
    relative_path: str,
    passages: list[tuple[str, str, str]],
    *,
    status: str = "parsed",
) -> dict:
    return {
        "document_id": source_document_id,
        "relative_path": relative_path,
        "format": "docx",
        "status": status,
        "passages": [
            {"passage_id": passage_id, "text": text, "source_location": location}
            for passage_id, text, location in passages
        ],
    }


class CorpusIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "corpus.sqlite3"
        self.index = CorpusIndex(self.database_path, FakeEmbedder())

    def tearDown(self) -> None:
        self.index.close()
        self.temporary_directory.cleanup()

    def test_indexes_proposal_and_returns_opaque_evidence_id(self) -> None:
        document = normalized_document(
            "normalized-doc-1",
            "Secret Client/Proposal 2024.docx",
            [("passage-1", "The platform supports user authentication.", "page:4")],
        )

        indexed_count = self.index.add_normalized_document(
            document,
            proposal_date="2024-05-01",
            language="en",
        )
        matches = self.index.search("login capability", limit=3)

        self.assertEqual(indexed_count, 1)
        self.assertEqual(len(matches), 1)
        self.assertNotIn("Secret Client", matches[0].evidence_id)
        self.assertEqual(matches[0].text, "The platform supports user authentication.")
        self.assertNotIn("relative_path", matches[0].__dict__)

    def test_resolves_source_citation_locally(self) -> None:
        self.index.add_normalized_document(
            normalized_document(
                "normalized-doc-citation",
                "Customer X/proposal.docx",
                [("passage-citation", "Identity management capability.", "table:2:row:1")],
            ),
            proposal_date="2023-11-12",
            language="es",
        )

        match = self.index.search("authentication", limit=1)[0]
        citation = self.index.resolve_citation(match.evidence_id)

        self.assertEqual(citation.relative_path, "Customer X/proposal.docx")
        self.assertEqual(citation.source_location, "table:2:row:1")
        self.assertEqual(citation.proposal_date, "2023-11-12")
        self.assertEqual(citation.language, "es")

    def test_hybrid_retrieval_finds_lexical_and_semantic_matches(self) -> None:
        self.index.add_normalized_document(
            normalized_document(
                "doc-lexical",
                "proposal-a.docx",
                [("p-1", "Payment processing and invoice management.", "page:1")],
            )
        )
        self.index.add_normalized_document(
            normalized_document(
                "doc-semantic",
                "proposal-b.docx",
                [("p-2", "User authentication is available.", "page:2")],
            )
        )

        lexical_match = self.index.search("invoice", limit=2)
        semantic_match = self.index.search("login", limit=2)

        self.assertEqual(lexical_match[0].text, "Payment processing and invoice management.")
        self.assertEqual(semantic_match[0].text, "User authentication is available.")

    def test_proposal_recency_does_not_override_relevance(self) -> None:
        relevant_old_count = self.index.add_normalized_document(
            normalized_document(
                "doc-relevant-old",
                "relevant-old-proposal.docx",
                [("p-old", "Secure encryption at rest.", "page:1")],
            ),
            proposal_date="2018-01-01",
        )
        irrelevant_new_count = self.index.add_normalized_document(
            normalized_document(
                "doc-irrelevant-new",
                "irrelevant-new-proposal.docx",
                [("p-new", "Payment invoice settlement.", "page:1")],
            ),
            proposal_date="2025-01-01",
        )

        results = self.index.search("security", limit=2)

        self.assertEqual(relevant_old_count, 1)
        self.assertEqual(irrelevant_new_count, 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].text, "Secure encryption at rest.")

    def test_language_and_date_filters_limit_candidates_without_reweighting(self) -> None:
        self.index.add_normalized_document(
            normalized_document(
                "metadata-en-2020",
                "english-proposal.docx",
                [("metadata-p1", "User authentication capabilities.", "page:1")],
            ),
            proposal_date="2020-06-01",
            language="en",
        )
        self.index.add_normalized_document(
            normalized_document(
                "metadata-es-2024",
                "spanish-proposal.docx",
                [("metadata-p2", "User authentication capabilities.", "page:2")],
            ),
            proposal_date="2024-06-01",
            language="es",
        )

        filtered = self.index.search(
            "authentication",
            limit=5,
            language="ES",
            proposal_date_from="2024-01-01",
            proposal_date_to="2024-12-31",
        )

        self.assertEqual(len(filtered), 1)
        citation = self.index.resolve_citation(filtered[0].evidence_id)
        self.assertEqual(citation.language, "es")
        self.assertEqual(citation.proposal_date, "2024-06-01")

    def test_metadata_filters_reject_invalid_dates_and_ranges(self) -> None:
        with self.assertRaises(ValueError):
            self.index.search("security", proposal_date_from="2024-13-01")
        with self.assertRaises(ValueError):
            self.index.search(
                "security",
                proposal_date_from="2025-01-01",
                proposal_date_to="2024-01-01",
            )

    def test_duplicate_ingestion_is_idempotent(self) -> None:
        document = normalized_document(
            "same-source-document",
            "proposal.docx",
            [("same-source-passage", "Invoice reconciliation.", "page:1")],
        )

        first_count = self.index.add_normalized_document(document)
        second_count = self.index.add_normalized_document(document)

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)
        self.assertEqual(self.index.passage_count(), 1)

    def test_rejects_reopening_corpus_with_a_different_embedding_model(self) -> None:
        self.index.add_normalized_document(
            normalized_document(
                "model-bound-doc",
                "model-bound.docx",
                [("model-bound-passage", "Authentication is available.", "page:1")],
            )
        )

        with self.assertRaisesRegex(CorpusIndexError, "does not match"):
            CorpusIndex(self.database_path, DifferentFakeEmbedder())

    def test_partial_document_is_not_indexed_as_capability_evidence(self) -> None:
        with self.assertRaises(CorpusIndexError):
            self.index.add_normalized_document(
                normalized_document(
                    "partial-source",
                    "partial.docx",
                    [("partial-passage", "Some extracted content.", "page:1")],
                    status="partial",
                )
            )

        self.assertEqual(self.index.passage_count(), 0)

    def test_index_directory_reports_skips_and_indexes_valid_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            documents_directory = Path(directory)
            good_document = normalized_document(
                "valid-doc",
                "valid.docx",
                [("valid-passage", "Account billing.", "page:1")],
            )
            partial_document = normalized_document(
                "partial-doc",
                "partial.docx",
                [("partial-passage", "Incomplete extract.", "page:1")],
                status="partial",
            )
            (documents_directory / "a-valid.json").write_text(
                json.dumps(good_document), encoding="utf-8"
            )
            (documents_directory / "b-partial.json").write_text(
                json.dumps(partial_document), encoding="utf-8"
            )

            summary = self.index.index_normalized_directory(documents_directory)

            self.assertEqual(summary.indexed_documents, 1)
            self.assertEqual(summary.indexed_passages, 1)
            self.assertEqual(summary.skipped_documents, 1)
            self.assertIn("fully parsed", summary.warnings[0])

    def test_index_directory_applies_sidecar_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            documents_directory = Path(directory)
            document = normalized_document(
                "metadata-source-doc",
                "proposal.docx",
                [("metadata-source-passage", "Secure data exchange.", "page:5")],
            )
            (documents_directory / "document.json").write_text(
                json.dumps(document), encoding="utf-8"
            )

            summary = self.index.index_normalized_directory(
                documents_directory,
                {
                    "metadata-source-doc": {
                        "proposal_date": "2024-02-20",
                        "language": "en",
                    }
                },
            )

            self.assertEqual(summary.indexed_documents, 1)
            result = self.index.search("secure", language="en")
            self.assertEqual(len(result), 1)
            citation = self.index.resolve_citation(result[0].evidence_id)
            self.assertEqual(citation.proposal_date, "2024-02-20")

    def test_search_rejects_empty_query_and_invalid_limit(self) -> None:
        with self.assertRaises(ValueError):
            self.index.search("   ")
        with self.assertRaises(ValueError):
            self.index.search("security", limit=0)


if __name__ == "__main__":
    unittest.main()