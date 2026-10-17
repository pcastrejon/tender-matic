import json
import unittest
from collections.abc import Callable
from typing import Any

from tender_matic.analysis import (
    AnalysisWarning,
    Requirement,
    RequirementAnalysis,
    TenderSourceReference,
)
from tender_matic.corpus import EvidenceMatch, LocalCitation
from tender_matic.matching import (
    MATCHING_SYSTEM_PROMPT,
    EvidenceMatcher,
    EvidenceMatchingError,
)
from tender_matic.privacy import LocalDeidentifier, PrivacyGateError


class FakeMatchingModel:
    def __init__(self, response_factory: Callable[[dict[str, Any]], str]) -> None:
        self._response_factory = response_factory
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_content: str) -> str:
        self.calls.append((system_prompt, user_content))
        return self._response_factory(json.loads(user_content))


class EvidenceMatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requirement = Requirement(
            requirement_id="req_001",
            text="The system must support multi-factor authentication.",
            source_ids=("tender_src_01",),
            extraction_confidence=0.93,
            warnings=(),
        )
        self.tender_source = TenderSourceReference(
            document_id="tender_doc_01",
            relative_path="tender/synthetic.txt",
            passage_id="tender_passage_01",
            source_location="line:12",
        )
        self.analysis = RequirementAnalysis(
            requirements=(self.requirement,),
            source_references={"tender_src_01": self.tender_source},
            warnings=(),
        )
        self.evidence = EvidenceMatch(
            evidence_id="evidence_01",
            text="The proposed service supports multi-factor authentication.",
            score=0.91,
        )
        self.citation = LocalCitation(
            relative_path="proposals/synthetic-one.md",
            source_location="section:Security",
            proposal_date="2020-01-01",
            language="en",
        )

    @staticmethod
    def response(
        payload: dict[str, Any],
        *,
        status: str,
        evidence_ids: list[str],
        rationale: str = "Synthetic evidence assessment.",
        questions: list[dict[str, Any]] | None = None,
        risks: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
    ) -> str:
        return json.dumps(
            {
                "assessments": [
                    {
                        "requirement_id": payload["requirements"][0]["requirement_id"],
                        "status": status,
                        "evidence_ids": evidence_ids,
                        "rationale": rationale,
                        "questions": questions or [],
                        "risks": risks or [],
                    }
                ],
                "warnings": warnings or [],
            }
        )

    def run_matcher(
        self,
        response_factory: Callable[[dict[str, Any]], str],
        evidence: tuple[EvidenceMatch, ...] | None = None,
        citations: dict[str, LocalCitation] | None = None,
        reviewer: Callable[..., bool] | None = None,
        analysis: RequirementAnalysis | None = None,
        assessment_reviewer: Callable[..., bool] | None = None,
    ):
        model = FakeMatchingModel(response_factory)
        review_calls: list[tuple[Any, Any]] = []

        def approved(context, result) -> bool:
            review_calls.append((context, result))
            return True if reviewer is None else reviewer(context, result)

        matcher = EvidenceMatcher(
            model,
            LocalDeidentifier({}),
            approved,
            assessment_reviewer or (lambda _context: True),
        )
        evidence_map = (
            {"req_001": evidence}
            if evidence is not None
            else {"req_001": (self.evidence,)}
        )
        citation_map = (
            citations
            if citations is not None
            else {self.evidence.evidence_id: self.citation}
        )
        result = matcher.analyze(
            analysis or self.analysis,
            evidence_map,
            citation_map,
        )
        return result, model, review_calls

    def test_exact_evidence_is_supported_and_citation_stays_local(self) -> None:
        result, model, reviews = self.run_matcher(
            lambda payload: self.response(
                payload,
                status="supported",
                evidence_ids=["evidence_01"],
            )
        )

        self.assertEqual(result.assessments[0].status, "supported")
        self.assertEqual(result.assessments[0].evidence_ids, ("evidence_01",))
        self.assertEqual(result.evidence_sources["evidence_01"], self.citation)
        self.assertEqual(len(reviews), 2)
        sent_content = model.calls[0][1]
        self.assertNotIn("proposals/synthetic-one.md", sent_content)
        self.assertNotIn("section:Security", sent_content)
        self.assertNotIn("2020-01-01", sent_content)
        self.assertNotIn('"score"', sent_content)
        self.assertEqual(model.calls[0][0], MATCHING_SYSTEM_PROMPT)

    def test_partial_evidence_is_not_promoted_to_full_support(self) -> None:
        result, _, _ = self.run_matcher(
            lambda payload: self.response(
                payload,
                status="partial",
                evidence_ids=["evidence_01"],
                rationale="The passage supports authentication but not every tender detail.",
            )
        )

        self.assertEqual(result.assessments[0].status, "partial")

    def test_no_retrieved_evidence_is_a_gap_and_warned(self) -> None:
        result, _, _ = self.run_matcher(
            lambda payload: self.response(
                payload,
                status="gap",
                evidence_ids=[],
                rationale="No proposal evidence was supplied.",
                questions=[{"text": "Can this requirement be clarified?", "evidence_ids": []}],
            ),
            evidence=(),
            citations={},
        )

        self.assertEqual(result.assessments[0].status, "gap")
        self.assertEqual(result.assessments[0].evidence_ids, ())
        self.assertIn("no_proposal_evidence", {item.code for item in result.warnings})

    def test_rejects_supported_claim_when_no_evidence_was_retrieved(self) -> None:
        model = FakeMatchingModel(
            lambda payload: self.response(
                payload,
                status="supported",
                evidence_ids=[],
            )
        )
        matcher = EvidenceMatcher(
            model, LocalDeidentifier({}), lambda *_: True, lambda _context: True
        )

        with self.assertRaisesRegex(EvidenceMatchingError, "must cite proposal evidence"):
            matcher.analyze(self.analysis, {"req_001": ()}, {})

    def test_ambiguous_requirement_question_and_extraction_warning_are_kept(self) -> None:
        warned_analysis = RequirementAnalysis(
            requirements=(
                Requirement(
                    requirement_id="req_001",
                    text="The system should be resilient.",
                    source_ids=("tender_src_01",),
                    extraction_confidence=0.51,
                    warnings=("The required resilience target is unclear.",),
                ),
            ),
            source_references={"tender_src_01": self.tender_source},
            warnings=(
                AnalysisWarning(
                    "low_confidence",
                    "Synthetic extraction needs review.",
                    document_id="tender_doc_01",
                ),
            ),
        )
        result, _, _ = self.run_matcher(
            lambda payload: self.response(
                payload,
                status="partial",
                evidence_ids=["evidence_01"],
                questions=[
                    {
                        "text": "What availability target and recovery time are required?",
                        "evidence_ids": [],
                    }
                ],
            ),
            analysis=warned_analysis,
        )

        self.assertEqual(len(result.assessments[0].questions), 1)
        self.assertTrue(
            any("resilience target is unclear" in warning.message for warning in result.warnings)
        )
        self.assertTrue(
            any(warning.code == "low_confidence" for warning in result.warnings)
        )

    def test_conflicting_proposals_are_surfaced_without_recency_preference(self) -> None:
        second_match = EvidenceMatch(
            "evidence_02",
            "The proposed service does not support multi-factor authentication.",
            0.88,
        )
        second_citation = LocalCitation(
            "proposals/synthetic-two.md",
            "section:Identity",
            proposal_date="2025-01-01",
            language="en",
        )
        result, model, _ = self.run_matcher(
            lambda payload: self.response(
                payload,
                status="conflict",
                evidence_ids=["evidence_01", "evidence_02"],
                rationale="The two proposal sources make contradictory statements.",
                questions=[
                    {
                        "text": "Which proposed approach should be treated as applicable?",
                        "evidence_ids": ["evidence_01", "evidence_02"],
                    }
                ],
            ),
            evidence=(self.evidence, second_match),
            citations={
                "evidence_01": self.citation,
                "evidence_02": second_citation,
            },
        )

        self.assertEqual(result.assessments[0].status, "conflict")
        self.assertEqual(set(result.assessments[0].evidence_ids), {"evidence_01", "evidence_02"})
        sent_content = model.calls[0][1]
        self.assertNotIn("2020-01-01", sent_content)
        self.assertNotIn("2025-01-01", sent_content)

    def test_conflict_requires_distinct_sources_and_question(self) -> None:
        model = FakeMatchingModel(
            lambda payload: self.response(
                payload,
                status="conflict",
                evidence_ids=["evidence_01"],
            )
        )
        matcher = EvidenceMatcher(
            model, LocalDeidentifier({}), lambda *_: True, lambda _context: True
        )

        with self.assertRaisesRegex(EvidenceMatchingError, "distinct proposals"):
            matcher.analyze(
                self.analysis,
                {"req_001": (self.evidence,)},
                {"evidence_01": self.citation},
            )

    def test_unrelated_retrieved_passage_is_not_inferred_as_support(self) -> None:
        unrelated = EvidenceMatch(
            "evidence_01",
            "The proposal describes an administrative dashboard.",
            0.99,
        )
        result, _, _ = self.run_matcher(
            lambda payload: self.response(
                payload,
                status="gap",
                evidence_ids=["evidence_01"],
                rationale="The retrieved passage does not establish multi-factor authentication.",
                questions=[
                    {
                        "text": "Is multi-factor authentication mandatory?",
                        "evidence_ids": [],
                    }
                ],
            ),
            evidence=(unrelated,),
        )

        self.assertEqual(result.assessments[0].status, "gap")

    def test_semantically_unverified_model_claim_is_not_returned(self) -> None:
        unrelated = EvidenceMatch(
            "evidence_01",
            "The proposal describes an administrative dashboard.",
            0.99,
        )

        with self.assertRaisesRegex(EvidenceMatchingError, "human must confirm"):
            self.run_matcher(
                lambda payload: self.response(
                    payload,
                    status="supported",
                    evidence_ids=["evidence_01"],
                    rationale="The dashboard proves multi-factor authentication.",
                ),
                evidence=(unrelated,),
                assessment_reviewer=lambda _context: False,
            )

    def test_review_denial_blocks_model_call(self) -> None:
        model = FakeMatchingModel(
            lambda payload: self.response(payload, status="gap", evidence_ids=[])
        )
        matcher = EvidenceMatcher(
            model,
            LocalDeidentifier({}),
            lambda *_: False,
            lambda _context: True,
        )

        with self.assertRaises(PrivacyGateError):
            matcher.analyze(
                self.analysis,
                {"req_001": (self.evidence,)},
                {"evidence_01": self.citation},
            )

        self.assertEqual(model.calls, [])

    def test_deidentifies_both_requirement_and_proposal_before_model_call(self) -> None:
        requirement = Requirement(
            "req_001",
            "Example Customer requires multi-factor authentication.",
            ("tender_src_01",),
            0.9,
            (),
        )
        analysis = RequirementAnalysis(
            (requirement,),
            {"tender_src_01": self.tender_source},
            (),
        )
        evidence = EvidenceMatch(
            "evidence_01",
            "Example Customer proposal supports multi-factor authentication.",
            0.9,
        )
        model = FakeMatchingModel(
            lambda payload: self.response(
                payload, status="supported", evidence_ids=["evidence_01"]
            )
        )
        matcher = EvidenceMatcher(
            model,
            LocalDeidentifier({"Example Customer": "CUSTOMER_NAME"}),
            lambda *_: True,
            lambda _context: True,
        )

        matcher.analyze(analysis, {"req_001": (evidence,)}, {"evidence_01": self.citation})

        self.assertNotIn("Example Customer", model.calls[0][1])

    def test_rejects_unknown_evidence_reference(self) -> None:
        model = FakeMatchingModel(
            lambda payload: self.response(
                payload,
                status="supported",
                evidence_ids=["invented_evidence"],
            )
        )
        matcher = EvidenceMatcher(
            model, LocalDeidentifier({}), lambda *_: True, lambda _context: True
        )

        with self.assertRaisesRegex(EvidenceMatchingError, "known evidence IDs"):
            matcher.analyze(
                self.analysis,
                {"req_001": (self.evidence,)},
                {"evidence_01": self.citation},
            )

    def test_rejects_evidence_from_another_requirements_candidate_set(self) -> None:
        another_requirement = Requirement(
            "req_002", "A different synthetic requirement.", ("tender_src_01",), 0.8, ()
        )
        analysis = RequirementAnalysis(
            (self.requirement, another_requirement),
            {"tender_src_01": self.tender_source},
            (),
        )
        model = FakeMatchingModel(
            lambda payload: json.dumps(
                {
                    "assessments": [
                        {
                            "requirement_id": payload["requirements"][0]["requirement_id"],
                            "status": "supported",
                            "evidence_ids": ["evidence_01"],
                            "rationale": "Synthetic.",
                            "questions": [],
                            "risks": [],
                        },
                        {
                            "requirement_id": payload["requirements"][1]["requirement_id"],
                            "status": "supported",
                            "evidence_ids": ["evidence_01"],
                            "rationale": "Synthetic.",
                            "questions": [],
                            "risks": [],
                        },
                    ],
                    "warnings": [],
                }
            )
        )
        matcher = EvidenceMatcher(
            model, LocalDeidentifier({}), lambda *_: True, lambda _context: True
        )

        with self.assertRaisesRegex(EvidenceMatchingError, "not retrieved for this requirement"):
            matcher.analyze(
                analysis,
                {"req_001": (self.evidence,), "req_002": ()},
                {"evidence_01": self.citation},
            )

    def test_risks_must_cite_proposal_evidence(self) -> None:
        model = FakeMatchingModel(
            lambda payload: self.response(
                payload,
                status="partial",
                evidence_ids=["evidence_01"],
                risks=[{"text": "An unsupported risk claim.", "evidence_ids": []}],
            )
        )
        matcher = EvidenceMatcher(
            model, LocalDeidentifier({}), lambda *_: True, lambda _context: True
        )

        with self.assertRaisesRegex(EvidenceMatchingError, "Every risk must cite"):
            matcher.analyze(
                self.analysis,
                {"req_001": (self.evidence,)},
                {"evidence_01": self.citation},
            )


if __name__ == "__main__":
    unittest.main()
