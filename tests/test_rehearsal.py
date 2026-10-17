import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tender_matic.analysis import ReviewContext
from tender_matic.corpus import CorpusIndex, TextEmbedder
from tender_matic.privacy import DeidentificationResult, LocalDeidentifier, PrivacyGateError
from tender_matic.rehearsal import LocalRehearsal, RehearsalError


class DeterministicEmbedder(TextEmbedder):
    model_name = "synthetic-rehearsal-embedder"

    def embed_passages(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


class FakeRequirementModel:
    def __init__(self):
        self.calls = []

    def complete(self, system_prompt: str, user_content: str) -> str:
        payload = json.loads(user_content)
        self.calls.append((system_prompt, payload))
        source_id = payload["sources"][0]["source_id"]
        return json.dumps(
            {
                "requirements": [
                    {
                        "text": "Support multi-factor authentication.",
                        "source_ids": [source_id],
                        "confidence": 0.95,
                        "warnings": [],
                    }
                ],
                "warnings": [],
            }
        )


class FakeMatchingModel:
    def __init__(self):
        self.calls = []

    def complete(self, system_prompt: str, user_content: str) -> str:
        payload = json.loads(user_content)
        self.calls.append((system_prompt, payload))
        assessments = []
        for item in payload["evidence_by_requirement"]:
            evidence_ids = [entry["evidence_id"] for entry in item["evidence"]]
            assessments.append(
                {
                    "requirement_id": item["requirement_id"],
                    "status": "supported" if evidence_ids else "gap",
                    "evidence_ids": evidence_ids[:1],
                    "rationale": (
                        "The synthetic proposal describes multi-factor authentication."
                        if evidence_ids
                        else "No proposal evidence was retrieved."
                    ),
                    "questions": [],
                    "risks": [],
                }
            )
        return json.dumps({"assessments": assessments, "warnings": []})


class LocalRehearsalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.tender_root = self.root / "tender"
        self.artifacts_root = self.root / "artifacts"
        self.draft_root = self.root / "drafts"
        self.tender_root.mkdir()
        (self.tender_root / "requirements.txt").write_text(
            "Synthetic Customer requires multi-factor authentication.\n",
            encoding="utf-8",
        )
        (self.tender_root / "unsupported.doc").write_bytes(b"synthetic unsupported fixture")
        self.corpus = CorpusIndex(self.root / "corpus.sqlite3", DeterministicEmbedder())
        self.corpus.add_normalized_document(
            {
                "document_id": "synthetic-proposal-01",
                "relative_path": "proposals/synthetic.md",
                "status": "parsed",
                "passages": [
                    {
                        "passage_id": "proposal-passage-01",
                        "text": "The proposed service supports multi-factor authentication.",
                        "source_location": "section:Security",
                    }
                ],
            }
        )

    def tearDown(self) -> None:
        self.corpus.close()
        self.temporary_directory.cleanup()

    def make_rehearsal(self, *, approve: bool = True):
        requirement_model = FakeRequirementModel()
        matching_model = FakeMatchingModel()
        reviewed: list[tuple[ReviewContext, DeidentificationResult]] = []
        accepted_assessments: list[Any] = []

        def excerpt_reviewer(context, result) -> bool:
            reviewed.append((context, result))
            self.assertNotIn("Synthetic Customer", result.sanitized_text)
            return approve

        def matching_reviewer(context, result) -> bool:
            reviewed.append((context, result))
            self.assertNotIn("Synthetic Customer", result.sanitized_text)
            return approve

        def assessment_reviewer(context) -> bool:
            accepted_assessments.append(context)
            return approve

        workflow = LocalRehearsal(
            corpus=self.corpus,
            requirement_model=requirement_model,
            matching_model=matching_model,
            deidentifier=LocalDeidentifier(
                {"Synthetic Customer": "CUSTOMER_NAME"}
            ),
            excerpt_reviewer=excerpt_reviewer,
            matching_reviewer=matching_reviewer,
            assessment_reviewer=assessment_reviewer,
        )
        return workflow, requirement_model, matching_model, reviewed, accepted_assessments

    def test_complete_synthetic_replay_preserves_gates_artifacts_and_traceability(self):
        workflow, req_model, match_model, reviewed, assessments = self.make_rehearsal()

        result = workflow.run(
            tender_directory=self.tender_root,
            artifacts_root=self.artifacts_root,
            draft_root=self.draft_root,
            draft_relative_path="synthetic-run.md",
        )

        self.assertEqual(result.report.status, "completed_with_warnings")
        self.assertEqual(result.report.tender_file_count, 2)
        self.assertEqual(result.report.parsed_document_count, 1)
        self.assertEqual(result.report.unsupported_or_failed_file_count, 1)
        self.assertEqual(result.report.requirement_count, 1)
        self.assertEqual(result.report.assessment_count, 1)
        self.assertGreater(result.report.retrieved_evidence_count, 0)
        self.assertGreaterEqual(result.report.duration_seconds, 0)
        self.assertTrue(result.draft_path.is_file())
        self.assertTrue(
            (result.artifacts_directory / "parsed" / "manifest.json").is_file()
        )
        requirement_data = json.loads(
            (result.artifacts_directory / "requirement-analysis.json").read_text(
                encoding="utf-8"
            )
        )
        evidence_data = json.loads(
            (result.artifacts_directory / "evidence-matrix.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(requirement_data["schema_version"], "1")
        self.assertEqual(evidence_data["schema_version"], "1")
        report_data = json.loads(
            (result.artifacts_directory / "rehearsal-report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report_data["schema_version"], "1")
        self.assertEqual(report_data["status"], "completed_with_warnings")
        self.assertEqual(len(req_model.calls), 1)
        self.assertEqual(len(match_model.calls), 1)
        self.assertNotIn("Synthetic Customer", json.dumps(req_model.calls[0][1]))
        self.assertNotIn("Synthetic Customer", json.dumps(match_model.calls[0][1]))
        self.assertEqual(len(reviewed), 3)
        self.assertEqual(len(assessments), 1)
        self.assertIn("Requirement and Evidence Matrix", result.draft.markdown)
        self.assertIn("Local Source References", result.draft.markdown)
        self.assertIn("section:Security", result.draft.markdown)

    def test_review_denial_fails_closed_before_requirement_model_call(self):
        workflow, req_model, _match_model, _reviewed, _assessments = self.make_rehearsal(
            approve=False
        )

        with self.assertRaises(PrivacyGateError):
            workflow.run(
                tender_directory=self.tender_root,
                artifacts_root=self.artifacts_root,
                draft_root=self.draft_root,
                draft_relative_path="blocked.md",
            )

        self.assertEqual(req_model.calls, [])
        self.assertFalse((self.draft_root / "blocked.md").exists())

    def test_incomplete_extraction_is_preserved_and_reported(self):
        (self.tender_root / "requirements.txt").write_text(
            "   \n", encoding="utf-8"
        )
        workflow, req_model, _match_model, _reviewed, _assessments = self.make_rehearsal()

        with self.assertRaisesRegex(RehearsalError, "No tender passages"):
            workflow.run(
                tender_directory=self.tender_root,
                artifacts_root=self.artifacts_root,
                draft_root=self.draft_root,
                draft_relative_path="incomplete.md",
            )

        self.assertEqual(req_model.calls, [])
        self.assertFalse((self.draft_root / "incomplete.md").exists())
        run_directories = list(self.artifacts_root.iterdir())
        self.assertEqual(len(run_directories), 1)
        manifest = json.loads(
            (run_directories[0] / "parsed" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(
            any(
                warning["code"] == "no_text_extracted"
                for entry in manifest["files"]
                for warning in entry["warnings"]
            )
        )

    def test_rejects_output_directory_overlapping_tender_input(self):
        workflow, *_ = self.make_rehearsal()

        with self.assertRaisesRegex(RehearsalError, "separate"):
            workflow.run(
                tender_directory=self.tender_root,
                artifacts_root=self.artifacts_root,
                draft_root=self.tender_root / "output",
                draft_relative_path="blocked.md",
            )

    def test_empty_proposal_corpus_produces_explicit_gap(self):
        self.corpus.close()
        empty_corpus = CorpusIndex(
            self.root / "empty-corpus.sqlite3", DeterministicEmbedder()
        )
        try:
            workflow, _req_model, _match_model, _reviewed, _assessments = (
                self.make_rehearsal_with_corpus(empty_corpus)
            )

            result = workflow.run(
                tender_directory=self.tender_root,
                artifacts_root=self.root / "empty-artifacts",
                draft_root=self.root / "empty-drafts",
                draft_relative_path="gap.md",
            )

            self.assertEqual(result.evidence_matrix.assessments[0].status, "gap")
            self.assertIn("No proposal evidence", result.draft.markdown)
        finally:
            empty_corpus.close()
            self.corpus = CorpusIndex(
                self.root / "corpus.sqlite3", DeterministicEmbedder()
            )

    def make_rehearsal_with_corpus(self, corpus):
        requirement_model = FakeRequirementModel()
        matching_model = FakeMatchingModel()
        workflow = LocalRehearsal(
            corpus=corpus,
            requirement_model=requirement_model,
            matching_model=matching_model,
            deidentifier=LocalDeidentifier(
                {"Synthetic Customer": "CUSTOMER_NAME"}
            ),
            excerpt_reviewer=lambda _context, _result: True,
            matching_reviewer=lambda _context, _result: True,
            assessment_reviewer=lambda _context: True,
        )
        return workflow, requirement_model, matching_model, [], []


if __name__ == "__main__":
    unittest.main()
