"""Evidence-grounded requirement matching for phase 5."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence

from tender_matic.analysis import Requirement, RequirementAnalysis, TenderSourceReference
from tender_matic.corpus import EvidenceMatch, LocalCitation
from tender_matic.privacy import (
    DeidentificationResult,
    LocalDeidentifier,
    OutboundExcerpt,
    PrivacyGateError,
)


MATCHING_SYSTEM_PROMPT = """\
Compare each tender requirement only with the proposal evidence supplied for it.
Do not infer capabilities, combine unrelated passages, or treat retrieval rank
as proof. Historical proposals have equal evidentiary weight; dates and recency
do not determine applicability or truth. A proposal shows only that a capability
was previously proposed, not that it is currently available or delivered.

Return only one JSON object matching this exact schema:
{
  "assessments": [
    {
      "requirement_id": "an input requirement_id",
      "status": "supported | partial | gap | conflict",
      "evidence_ids": ["input evidence IDs relevant to this assessment"],
      "rationale": "brief explanation limited to the supplied text",
      "questions": [
        {"text": "a clarification question", "evidence_ids": []}
      ],
      "risks": [
        {"text": "an evidence-grounded risk", "evidence_ids": ["input evidence ID"]}
      ]
    }
  ],
  "warnings": ["uncertainty or limitations"]
}

Return exactly one assessment for every supplied requirement. Use gap when no
supplied proposal evidence supports the requirement. Use partial when evidence
supports only part of it. Use conflict when distinct proposal sources make
contradictory statements; surface a clarification question instead of choosing
one source. Every supported, partial, or conflict assessment must cite evidence.
Every risk must cite evidence. Questions may have no evidence IDs when they ask
for missing tender information. Never invent evidence IDs.
"""


class EvidenceMatchingError(ValueError):
    """Raised when phase 5 input or model output violates its evidence contract."""


class MatchingModel(Protocol):
    def complete(self, system_prompt: str, user_content: str) -> str: ...


@dataclass(frozen=True)
class MatchingReviewContext:
    """Local provenance shown while reviewing each exact outbound excerpt."""

    content_type: str
    record_id: str
    local_sources: tuple[TenderSourceReference | LocalCitation, ...]
    original_text: str


@dataclass(frozen=True)
class AssessmentReviewContext:
    """Local requirement, model assessment, and raw proposal evidence for review."""

    requirement: Requirement
    assessment: RequirementEvidenceAssessment
    evidence: tuple[tuple[EvidenceMatch, LocalCitation], ...]


@dataclass(frozen=True)
class ClarificationQuestion:
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceRisk:
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class RequirementEvidenceAssessment:
    requirement_id: str
    status: str
    evidence_ids: tuple[str, ...]
    rationale: str
    questions: tuple[ClarificationQuestion, ...]
    risks: tuple[EvidenceRisk, ...]


@dataclass(frozen=True)
class EvidenceWarning:
    code: str
    message: str
    requirement_id: str | None = None


@dataclass(frozen=True)
class EvidenceMatrix:
    assessments: tuple[RequirementEvidenceAssessment, ...]
    requirement_sources: Mapping[str, TenderSourceReference]
    evidence_sources: Mapping[str, LocalCitation]
    warnings: tuple[EvidenceWarning, ...]


MatchingReviewer = Callable[[MatchingReviewContext, DeidentificationResult], bool]
AssessmentReviewer = Callable[[AssessmentReviewContext], bool]
_VALID_STATUSES = {"supported", "partial", "gap", "conflict"}


class EvidenceMatcher:
    """Match requirements to reviewed proposal excerpts with strict references."""

    def __init__(
        self,
        model: MatchingModel,
        deidentifier: LocalDeidentifier,
        reviewer: MatchingReviewer,
        assessment_reviewer: AssessmentReviewer,
    ) -> None:
        self._model = model
        self._deidentifier = deidentifier
        self._reviewer = reviewer
        self._assessment_reviewer = assessment_reviewer

    def analyze(
        self,
        requirement_analysis: RequirementAnalysis,
        evidence_by_requirement: Mapping[str, Sequence[object]],
        evidence_sources: Mapping[str, object],
    ) -> EvidenceMatrix:
        requirements = requirement_analysis.requirements
        requirement_by_id = {requirement.requirement_id: requirement for requirement in requirements}
        if len(requirement_by_id) != len(requirements):
            raise EvidenceMatchingError("Requirement IDs must be unique")
        if not requirement_by_id:
            raise EvidenceMatchingError("At least one requirement is required")

        unknown_requirement_ids = set(evidence_by_requirement) - set(requirement_by_id)
        if unknown_requirement_ids:
            raise EvidenceMatchingError("Evidence refers to an unknown requirement ID")

        known_tender_sources = requirement_analysis.source_references
        for requirement in requirements:
            if not requirement.source_ids or any(
                source_id not in known_tender_sources for source_id in requirement.source_ids
            ):
                raise EvidenceMatchingError(
                    f"Requirement {requirement.requirement_id} has an unknown tender source"
                )

        evidence_by_id: dict[str, EvidenceMatch] = {}
        validated_evidence_by_requirement: dict[str, tuple[EvidenceMatch, ...]] = {}
        validated_evidence_sources: dict[str, LocalCitation] = {}
        for requirement_id, matches in evidence_by_requirement.items():
            if not isinstance(matches, Sequence) or isinstance(matches, (str, bytes)):
                raise EvidenceMatchingError("Evidence matches must be a sequence")
            local_ids: set[str] = set()
            validated_matches: list[EvidenceMatch] = []
            for match in matches:
                if not isinstance(match, EvidenceMatch):
                    raise EvidenceMatchingError("Each candidate must be an EvidenceMatch")
                self._validate_evidence_match(match)
                if match.evidence_id in local_ids:
                    raise EvidenceMatchingError(
                        f"Duplicate evidence ID for requirement {requirement_id}"
                    )
                local_ids.add(match.evidence_id)
                prior_match = evidence_by_id.get(match.evidence_id)
                if prior_match is not None and prior_match != match:
                    raise EvidenceMatchingError("Evidence IDs must identify one stable passage")
                citation = evidence_sources.get(match.evidence_id)
                if not isinstance(citation, LocalCitation):
                    raise EvidenceMatchingError("Evidence is missing its local citation")
                self._validate_citation(citation)
                evidence_by_id[match.evidence_id] = match
                validated_evidence_sources[match.evidence_id] = citation
                validated_matches.append(match)
            validated_evidence_by_requirement[requirement_id] = tuple(validated_matches)

        outbound_requirements = [
            {
                "requirement_id": requirement.requirement_id,
                "text": self._review_and_sanitize(
                    "tender_requirement",
                    requirement.requirement_id,
                    requirement.text,
                    tuple(
                        known_tender_sources[source_id]
                        for source_id in requirement.source_ids
                    ),
                ),
            }
            for requirement in requirements
        ]

        outbound_evidence: dict[str, str] = {}
        for evidence_id, match in evidence_by_id.items():
            outbound_evidence[evidence_id] = self._review_and_sanitize(
                "proposal_evidence",
                evidence_id,
                match.text,
                (validated_evidence_sources[evidence_id],),
            )

        user_content = json.dumps(
            {
                "requirements": outbound_requirements,
                "evidence_by_requirement": [
                    {
                        "requirement_id": requirement.requirement_id,
                        "evidence": [
                            {"evidence_id": match.evidence_id,
                             "text": outbound_evidence[match.evidence_id]}
                            for match in validated_evidence_by_requirement.get(
                                requirement.requirement_id, ()
                            )
                        ],
                    }
                    for requirement in requirements
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        response_text = self._model.complete(MATCHING_SYSTEM_PROMPT, user_content)
        assessments, model_warnings = _parse_matching_response(
            response_text,
            requirement_by_id,
            evidence_by_id,
            validated_evidence_sources,
            validated_evidence_by_requirement,
        )

        output_text = [
            assessment.rationale
            for assessment in assessments
        ] + [
            item.text
            for assessment in assessments
            for item in (*assessment.questions, *assessment.risks)
        ] + list(model_warnings)
        if any(self._deidentifier.sanitize(text).findings for text in output_text):
            raise EvidenceMatchingError(
                "Model response contained a potential direct identifier and was blocked"
            )

        for assessment in assessments:
            review_context = AssessmentReviewContext(
                requirement=requirement_by_id[assessment.requirement_id],
                assessment=assessment,
                evidence=tuple(
                    (
                        match,
                        validated_evidence_sources[match.evidence_id],
                    )
                    for match in validated_evidence_by_requirement.get(
                        assessment.requirement_id, ()
                    )
                ),
            )
            if self._assessment_reviewer(review_context) is not True:
                raise EvidenceMatchingError(
                    "A human must confirm each evidence assessment before it can be used"
                )

        warnings = [
            EvidenceWarning(warning.code, warning.message)
            for warning in requirement_analysis.warnings
        ]
        warnings.extend(
            EvidenceWarning("requirement_warning", warning, requirement.requirement_id)
            for requirement in requirements
            for warning in requirement.warnings
        )
        warnings.extend(
            EvidenceWarning("model_warning", warning) for warning in model_warnings
        )
        for assessment in assessments:
            if not validated_evidence_by_requirement.get(assessment.requirement_id):
                warnings.append(
                    EvidenceWarning(
                        "no_proposal_evidence",
                        "No proposal evidence was retrieved; do not infer a capability.",
                        assessment.requirement_id,
                    )
                )

        return EvidenceMatrix(
            assessments=assessments,
            requirement_sources=known_tender_sources,
            evidence_sources=validated_evidence_sources,
            warnings=tuple(warnings),
        )

    def _review_and_sanitize(
        self,
        content_type: str,
        record_id: str,
        text: str,
        local_sources: tuple[TenderSourceReference | LocalCitation, ...],
    ) -> str:
        result = self._deidentifier.sanitize(text)
        review_context = MatchingReviewContext(
            content_type=content_type,
            record_id=record_id,
            local_sources=local_sources,
            original_text=text,
        )
        if self._reviewer(review_context, result) is not True:
            raise PrivacyGateError(
                "A human must approve each exact excerpt before evidence matching"
            )
        outbound: OutboundExcerpt = self._deidentifier.authorize_for_outbound(
            result,
            reviewer_confirmed_no_customer_identifiers=True,
        )
        return outbound.text

    @staticmethod
    def _validate_evidence_match(match: EvidenceMatch) -> None:
        if not isinstance(match.evidence_id, str) or not match.evidence_id.strip():
            raise EvidenceMatchingError("Evidence ID must be non-empty")
        if not isinstance(match.text, str) or not match.text.strip():
            raise EvidenceMatchingError("Evidence text must be non-empty")
        if (
            isinstance(match.score, bool)
            or not isinstance(match.score, (int, float))
            or not math.isfinite(match.score)
        ):
            raise EvidenceMatchingError("Retrieval score must be finite")

    @staticmethod
    def _validate_citation(citation: LocalCitation) -> None:
        if (
            not isinstance(citation.relative_path, str)
            or not citation.relative_path.strip()
            or not isinstance(citation.source_location, str)
            or not citation.source_location.strip()
        ):
            raise EvidenceMatchingError("Evidence citation is missing local provenance")


def _parse_matching_response(
    response_text: str,
    requirements: Mapping[str, Requirement],
    evidence_by_id: Mapping[str, EvidenceMatch],
    evidence_sources: Mapping[str, LocalCitation],
    evidence_by_requirement: Mapping[str, Sequence[EvidenceMatch]],
) -> tuple[tuple[RequirementEvidenceAssessment, ...], tuple[str, ...]]:
    try:
        response = json.loads(response_text, object_pairs_hook=_unique_object_pairs)
    except (TypeError, ValueError) as error:
        raise EvidenceMatchingError("Model response must be valid JSON") from error
    if not isinstance(response, dict) or set(response) != {"assessments", "warnings"}:
        raise EvidenceMatchingError("Model response must contain exactly assessments and warnings")
    raw_assessments = response["assessments"]
    raw_warnings = _string_list(response["warnings"], "warnings")
    if not isinstance(raw_assessments, list):
        raise EvidenceMatchingError("assessments must be a list")

    parsed: dict[str, RequirementEvidenceAssessment] = {}
    expected_fields = {
        "requirement_id", "status", "evidence_ids", "rationale", "questions", "risks"
    }
    for raw_assessment in raw_assessments:
        if not isinstance(raw_assessment, dict) or set(raw_assessment) != expected_fields:
            raise EvidenceMatchingError("Assessment fields do not match the schema")
        requirement_id = raw_assessment["requirement_id"]
        if not isinstance(requirement_id, str) or requirement_id not in requirements:
            raise EvidenceMatchingError("Assessment refers to an unknown requirement")
        if requirement_id in parsed:
            raise EvidenceMatchingError("Each requirement must have exactly one assessment")
        status = raw_assessment["status"]
        if not isinstance(status, str) or status not in _VALID_STATUSES:
            raise EvidenceMatchingError("Assessment status is invalid")
        evidence_ids = _evidence_ids(raw_assessment["evidence_ids"], evidence_by_id)
        rationale = raw_assessment["rationale"]
        if not isinstance(rationale, str) or not rationale.strip():
            raise EvidenceMatchingError("Assessment rationale must not be empty")
        candidate_ids = {
            match.evidence_id
            for match in evidence_by_requirement.get(requirement_id, ())
        }
        questions = tuple(
            ClarificationQuestion(text, cited_ids)
            for text, cited_ids in _parse_items(
                raw_assessment["questions"],
                "questions",
                evidence_by_id,
                candidate_ids,
            )
        )
        risks = tuple(
            EvidenceRisk(text, cited_ids)
            for text, cited_ids in _parse_items(
                raw_assessment["risks"],
                "risks",
                evidence_by_id,
                candidate_ids,
            )
        )
        if not set(evidence_ids).issubset(candidate_ids):
            raise EvidenceMatchingError(
                "Assessment cites evidence not retrieved for this requirement"
            )
        if status in {"supported", "partial", "conflict"} and not evidence_ids:
            raise EvidenceMatchingError(
                f"{status} assessments must cite proposal evidence"
            )
        if status == "conflict":
            distinct_sources = {
                evidence_sources[evidence_id].relative_path for evidence_id in evidence_ids
            }
            if len(distinct_sources) < 2:
                raise EvidenceMatchingError(
                    "Conflicts must cite contradictory evidence from distinct proposals"
                )
            if not questions:
                raise EvidenceMatchingError(
                    "Conflicts must include a clarification question for human resolution"
                )
        if not candidate_ids and status != "gap":
            raise EvidenceMatchingError(
                "A requirement with no retrieved proposal evidence must be marked as a gap"
            )
        parsed[requirement_id] = RequirementEvidenceAssessment(
            requirement_id=requirement_id,
            status=status,
            evidence_ids=evidence_ids,
            rationale=rationale.strip(),
            questions=questions,
            risks=risks,
        )

    if set(parsed) != set(requirements):
        raise EvidenceMatchingError("Every requirement must have exactly one assessment")
    ordered = tuple(parsed[requirement.requirement_id] for requirement in requirements.values())
    return ordered, raw_warnings


def _evidence_ids(value: object, known_evidence: Mapping[str, EvidenceMatch]) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or item not in known_evidence for item in value)
    ):
        raise EvidenceMatchingError("evidence_ids must contain known evidence IDs")
    if len(value) != len(set(value)):
        raise EvidenceMatchingError("Evidence IDs must be unique within an assessment item")
    return tuple(value)


def _parse_items(
    value: object,
    field_name: str,
    known_evidence: Mapping[str, EvidenceMatch],
    allowed_evidence_ids: set[str],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(value, list):
        raise EvidenceMatchingError(f"{field_name} must be a list")
    parsed: list[tuple[str, tuple[str, ...]]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"text", "evidence_ids"}:
            raise EvidenceMatchingError(f"{field_name} items must contain text and evidence_ids")
        text = item["text"]
        if not isinstance(text, str) or not text.strip():
            raise EvidenceMatchingError(f"{field_name} text must not be empty")
        evidence_ids = _evidence_ids(item["evidence_ids"], known_evidence)
        if not set(evidence_ids).issubset(allowed_evidence_ids):
            raise EvidenceMatchingError(
                f"{field_name} cite evidence not retrieved for this requirement"
            )
        if field_name == "risks" and not evidence_ids:
            raise EvidenceMatchingError("Every risk must cite proposal evidence")
        parsed.append((text.strip(), evidence_ids))
    return tuple(parsed)


def _string_list(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise EvidenceMatchingError(f"{field_name} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _unique_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object contains a duplicate key")
        result[key] = value
    return result
