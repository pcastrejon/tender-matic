"""Human-reviewed tender requirement extraction for phase 4."""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence

from tender_matic.privacy import (
    DeidentificationResult,
    LocalDeidentifier,
    OutboundExcerpt,
    PrivacyGateError,
)


ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"

ANALYSIS_SYSTEM_PROMPT = """\
Extract explicit requirements from the supplied tender excerpts. Do not infer
requirements that are not stated. Return only one JSON object with exactly the
schema below:
{
  "requirements": [
    {
      "text": "A concise, faithful statement of one explicit requirement",
      "source_ids": ["one or more source_id values from the input"],
      "confidence": 0.0,
      "warnings": ["uncertainty or interpretation notes"]
    }
  ],
  "warnings": ["document-level extraction or interpretation warnings"]
}
Every requirement must cite at least one supplied source_id. Confidence must be
a number from 0 to 1. Use warnings when wording is ambiguous, incomplete, or
could not be extracted reliably. Do not invent source IDs or customer details.
"""


class RequirementAnalysisError(ValueError):
    """Raised when tender input or model output violates the analysis contract."""


class ClaudeAPIError(RuntimeError):
    """Raised when a Claude Messages API request fails or is malformed."""


class AnalysisModel(Protocol):
    def complete(self, system_prompt: str, user_content: str) -> str: ...


@dataclass(frozen=True)
class TenderExcerpt:
    """A locally selected excerpt and its local-only provenance."""

    document_id: str
    relative_path: str
    passage_id: str
    source_location: str
    text: str


@dataclass(frozen=True)
class ReviewContext:
    """Information shown to the human reviewer; never serialized to Claude."""

    document_id: str
    relative_path: str
    passage_id: str
    source_location: str
    original_text: str


@dataclass(frozen=True)
class TenderSourceReference:
    document_id: str
    relative_path: str
    passage_id: str
    source_location: str


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    text: str
    source_ids: tuple[str, ...]
    extraction_confidence: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisWarning:
    code: str
    message: str
    document_id: str | None = None
    relative_path: str | None = None
    source_location: str | None = None


@dataclass(frozen=True)
class RequirementAnalysis:
    requirements: tuple[Requirement, ...]
    source_references: Mapping[str, TenderSourceReference]
    warnings: tuple[AnalysisWarning, ...]


ExcerptReviewer = Callable[[ReviewContext, DeidentificationResult], bool]


class RequirementAnalyzer:
    """Analyze explicitly selected excerpts after attended local privacy review."""

    def __init__(
        self,
        model: AnalysisModel,
        deidentifier: LocalDeidentifier,
        reviewer: ExcerptReviewer,
    ) -> None:
        self._model = model
        self._deidentifier = deidentifier
        self._reviewer = reviewer

    def analyze(
        self,
        excerpts: Sequence[TenderExcerpt],
        *,
        extraction_warnings: Sequence[AnalysisWarning] = (),
    ) -> RequirementAnalysis:
        if not excerpts:
            raise RequirementAnalysisError("At least one selected tender excerpt is required")

        source_references: dict[str, TenderSourceReference] = {}
        model_sources: list[dict[str, str]] = []
        for excerpt in excerpts:
            self._validate_excerpt(excerpt)
            source_id = f"src_{uuid.uuid4().hex}"
            deidentification = self._deidentifier.sanitize(excerpt.text)
            review_context = ReviewContext(
                document_id=excerpt.document_id,
                relative_path=excerpt.relative_path,
                passage_id=excerpt.passage_id,
                source_location=excerpt.source_location,
                original_text=excerpt.text,
            )
            if self._reviewer(review_context, deidentification) is not True:
                raise PrivacyGateError(
                    "A human must approve each exact excerpt before model analysis"
                )
            outbound: OutboundExcerpt = self._deidentifier.authorize_for_outbound(
                deidentification,
                reviewer_confirmed_no_customer_identifiers=True,
            )
            source_references[source_id] = TenderSourceReference(
                document_id=excerpt.document_id,
                relative_path=excerpt.relative_path,
                passage_id=excerpt.passage_id,
                source_location=excerpt.source_location,
            )
            model_sources.append({"source_id": source_id, "text": outbound.text})

        user_content = json.dumps({"sources": model_sources}, ensure_ascii=False)
        response_text = self._model.complete(ANALYSIS_SYSTEM_PROMPT, user_content)
        requirements, model_warnings = _parse_model_response(
            response_text, set(source_references)
        )
        generated_text = [
            value
            for requirement in requirements
            for value in (requirement.text, *requirement.warnings)
        ] + list(model_warnings)
        if any(self._deidentifier.sanitize(value).findings for value in generated_text):
            raise RequirementAnalysisError(
                "Model response contained a potential direct identifier and was blocked"
            )

        warnings = list(extraction_warnings)
        warnings.extend(AnalysisWarning("model_warning", warning) for warning in model_warnings)
        if not requirements:
            warnings.append(
                AnalysisWarning(
                    "no_requirements_extracted",
                    "No requirements were returned; confirm extraction coverage locally.",
                )
            )

        return RequirementAnalysis(
            requirements=requirements,
            source_references=source_references,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _validate_excerpt(excerpt: TenderExcerpt) -> None:
        if not isinstance(excerpt, TenderExcerpt):
            raise RequirementAnalysisError("Each input must be a TenderExcerpt")
        fields = (
            excerpt.document_id,
            excerpt.relative_path,
            excerpt.passage_id,
            excerpt.source_location,
            excerpt.text,
        )
        if any(not isinstance(value, str) or not value.strip() for value in fields):
            raise RequirementAnalysisError(
                "Tender excerpts require document, path, passage, location, and text"
            )


class ClaudeMessagesAdapter:
    """Minimal Claude Messages API client; it sends only caller-approved content."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 30,
        max_tokens: int = 4096,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("A Claude model identifier is required")
        if not isinstance(resolved_key, str) or not resolved_key.strip():
            raise ValueError("Set ANTHROPIC_API_KEY locally before using Claude")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("API timeout must be a positive finite number")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise ValueError("max_tokens must be a positive integer")
        self.model = model.strip()
        self._api_key = resolved_key
        self._timeout = timeout
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_content: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": self._max_tokens,
                "temperature": 0,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_content}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            ANTHROPIC_MESSAGES_URL,
            data=body,
            headers={
                "content-type": "application/json",
                "anthropic-version": ANTHROPIC_API_VERSION,
                "x-api-key": self._api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                response_body = response.read()
        except urllib.error.HTTPError as error:
            raise ClaudeAPIError(
                f"Claude Messages API returned HTTP {error.code}"
            ) from error
        except urllib.error.URLError as error:
            raise ClaudeAPIError("Claude Messages API request failed") from error

        try:
            payload = json.loads(response_body, object_pairs_hook=_unique_object_pairs)
        except (UnicodeDecodeError, ValueError) as error:
            raise ClaudeAPIError("Claude Messages API returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise ClaudeAPIError("Claude Messages API response must be an object")
        if payload.get("stop_reason") != "end_turn":
            raise ClaudeAPIError("Claude did not complete the requirement analysis response")
        content = payload.get("content")
        if not isinstance(content, list) or not content:
            raise ClaudeAPIError("Claude Messages API response has no content blocks")
        text_blocks: list[str] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                raise ClaudeAPIError("Claude response included a non-text content block")
            text = block.get("text")
            if not isinstance(text, str):
                raise ClaudeAPIError("Claude response text block is malformed")
            text_blocks.append(text)
        return "\n".join(text_blocks)


def _parse_model_response(
    response_text: str, known_source_ids: set[str]
) -> tuple[tuple[Requirement, ...], tuple[str, ...]]:
    try:
        response = json.loads(response_text, object_pairs_hook=_unique_object_pairs)
    except (TypeError, ValueError) as error:
        raise RequirementAnalysisError("Model response must be valid JSON") from error
    if not isinstance(response, dict) or set(response) != {"requirements", "warnings"}:
        raise RequirementAnalysisError(
            "Model response must contain exactly requirements and warnings"
        )
    raw_requirements = response["requirements"]
    raw_warnings = response["warnings"]
    if not isinstance(raw_requirements, list):
        raise RequirementAnalysisError("requirements must be a list")
    warnings = _string_list(raw_warnings, "warnings")

    requirements: list[Requirement] = []
    for index, raw_requirement in enumerate(raw_requirements, start=1):
        expected_fields = {"text", "source_ids", "confidence", "warnings"}
        if not isinstance(raw_requirement, dict) or set(raw_requirement) != expected_fields:
            raise RequirementAnalysisError(
                "Each requirement must contain exactly text, source_ids, confidence, and warnings"
            )
        text = raw_requirement["text"]
        if not isinstance(text, str) or not text.strip():
            raise RequirementAnalysisError("Requirement text must not be empty")
        source_ids = raw_requirement["source_ids"]
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or any(not isinstance(source_id, str) or not source_id for source_id in source_ids)
        ):
            raise RequirementAnalysisError("Every requirement must have at least one source ID")
        if len(source_ids) != len(set(source_ids)):
            raise RequirementAnalysisError("Requirement source IDs must be unique")
        unknown_source_ids = set(source_ids) - known_source_ids
        if unknown_source_ids:
            raise RequirementAnalysisError("Requirement refers to an unknown source ID")
        confidence = raw_requirement["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise RequirementAnalysisError("Requirement confidence must be a number from 0 to 1")
        requirement_warnings = _string_list(raw_requirement["warnings"], "requirement warnings")
        requirements.append(
            Requirement(
                requirement_id=f"req_{index:03d}",
                text=text.strip(),
                source_ids=tuple(source_ids),
                extraction_confidence=float(confidence),
                warnings=requirement_warnings,
            )
        )
    return tuple(requirements), warnings


def _string_list(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise RequirementAnalysisError(f"{field_name} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _unique_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object contains a duplicate key")
        result[key] = value
    return result
