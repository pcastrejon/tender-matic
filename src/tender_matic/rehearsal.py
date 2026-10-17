"""Synthetic-safe local orchestration for phase 7 workflow replay."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Protocol

from tender_matic.analysis import (
    AnalysisModel,
    AnalysisWarning,
    DeidentificationResult,
    RequirementAnalysis,
    RequirementAnalyzer,
    ReviewContext,
    TenderExcerpt,
)
from tender_matic.corpus import EvidenceMatch, LocalCitation
from tender_matic.matching import (
    AssessmentReviewer,
    EvidenceMatrix,
    EvidenceMatcher,
    MatchingModel,
    MatchingReviewer,
)
from tender_matic.privacy import LocalDeidentifier
from tender_matic.proposal import ProposalDraft, render_markdown, write_markdown
from tender_matic.ingestion import IngestionResult, ingest_directory, write_artifacts


class RehearsalError(RuntimeError):
    """Raised when the local end-to-end rehearsal cannot safely complete."""


class LocalCorpus(Protocol):
    def search(self, query: str, *, limit: int = 5) -> list[EvidenceMatch]: ...

    def resolve_citation(self, evidence_id: str) -> LocalCitation: ...


@dataclass(frozen=True)
class RehearsalReport:
    run_id: str
    started_at: str
    completed_at: str
    duration_seconds: float
    tender_file_count: int
    parsed_document_count: int
    partial_document_count: int
    unsupported_or_failed_file_count: int
    tender_passage_count: int
    requirement_count: int
    retrieved_evidence_count: int
    assessment_count: int
    warning_count: int
    draft_path: str
    status: str


@dataclass(frozen=True)
class RehearsalResult:
    report: RehearsalReport
    ingestion: IngestionResult
    requirement_analysis: RequirementAnalysis
    evidence_matrix: EvidenceMatrix
    draft: ProposalDraft
    artifacts_directory: Path
    draft_path: Path


class LocalRehearsal:
    """Run parsing, reviewed requirement analysis, local retrieval, matching, and drafting.

    Model adapters and human-review callbacks are injected so the same orchestration
    can be replayed with deterministic fakes without network access or credentials.
    """

    def __init__(
        self,
        *,
        corpus: LocalCorpus,
        requirement_model: AnalysisModel,
        matching_model: MatchingModel,
        deidentifier: LocalDeidentifier,
        excerpt_reviewer: Callable[[ReviewContext, DeidentificationResult], bool],
        matching_reviewer: MatchingReviewer,
        assessment_reviewer: AssessmentReviewer,
        retrieval_limit: int = 5,
    ) -> None:
        if isinstance(retrieval_limit, bool) or not isinstance(retrieval_limit, int):
            raise ValueError("Retrieval limit must be a positive integer")
        if retrieval_limit < 1:
            raise ValueError("Retrieval limit must be a positive integer")
        self._corpus = corpus
        self._requirement_model = requirement_model
        self._matching_model = matching_model
        self._deidentifier = deidentifier
        self._excerpt_reviewer = excerpt_reviewer
        self._matching_reviewer = matching_reviewer
        self._assessment_reviewer = assessment_reviewer
        self._retrieval_limit = retrieval_limit

    def run(
        self,
        *,
        tender_directory: Path,
        artifacts_root: Path,
        draft_root: Path,
        draft_relative_path: str | Path,
    ) -> RehearsalResult:
        started_clock = time.perf_counter()
        started_at = datetime.now(UTC)
        tender_root = tender_directory.resolve(strict=True)
        if not tender_root.is_dir():
            raise NotADirectoryError(f"Tender input is not a directory: {tender_directory}")
        resolved_artifacts_root = artifacts_root.expanduser().resolve(strict=False)
        resolved_draft_root = draft_root.expanduser().resolve(strict=False)
        _require_disjoint(tender_root, resolved_artifacts_root, "Artifacts directory")
        _require_disjoint(tender_root, resolved_draft_root, "Draft directory")
        _require_disjoint(
            resolved_artifacts_root,
            resolved_draft_root,
            "Artifacts and draft directories",
        )
        resolved_artifacts_root.mkdir(parents=True, exist_ok=True)
        run_id = uuid.uuid4().hex
        artifacts_directory = resolved_artifacts_root / run_id
        artifacts_directory.mkdir()

        ingestion = ingest_directory(tender_root)
        write_artifacts(ingestion, artifacts_directory / "parsed")
        excerpts = _tender_excerpts(ingestion)
        if not excerpts:
            raise RehearsalError(
                "No tender passages were extracted; the rehearsal cannot continue"
            )
        extraction_warnings = _extraction_warnings(ingestion)

        requirement_analysis = RequirementAnalyzer(
            self._requirement_model,
            self._deidentifier,
            self._excerpt_reviewer,
        ).analyze(excerpts, extraction_warnings=extraction_warnings)

        evidence_by_requirement = {}
        evidence_sources = {}
        for requirement in requirement_analysis.requirements:
            matches = self._corpus.search(
                requirement.text,
                limit=self._retrieval_limit,
            )
            evidence_by_requirement[requirement.requirement_id] = matches
            for match in matches:
                evidence_sources[match.evidence_id] = self._corpus.resolve_citation(
                    match.evidence_id
                )

        evidence_matrix = EvidenceMatcher(
            self._matching_model,
            self._deidentifier,
            self._matching_reviewer,
            self._assessment_reviewer,
        ).analyze(requirement_analysis, evidence_by_requirement, evidence_sources)
        draft = render_markdown(requirement_analysis, evidence_matrix)

        _write_json_exclusive(
            artifacts_directory / "requirement-analysis.json",
            {
                "schema_version": "1",
                "requirement_analysis": asdict(requirement_analysis),
            },
        )
        _write_json_exclusive(
            artifacts_directory / "evidence-matrix.json",
            {"schema_version": "1", "evidence_matrix": asdict(evidence_matrix)},
        )

        draft_path = write_markdown(draft, resolved_draft_root, draft_relative_path)
        completed_at = datetime.now(UTC)
        report = RehearsalReport(
            run_id=run_id,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_seconds=time.perf_counter() - started_clock,
            tender_file_count=len(ingestion.manifest),
            parsed_document_count=sum(
                entry.status == "parsed" for entry in ingestion.manifest
            ),
            partial_document_count=sum(
                entry.status == "partial" for entry in ingestion.manifest
            ),
            unsupported_or_failed_file_count=sum(
                entry.status in {"unsupported", "failed"} for entry in ingestion.manifest
            ),
            tender_passage_count=len(excerpts),
            requirement_count=len(requirement_analysis.requirements),
            retrieved_evidence_count=sum(
                len(matches) for matches in evidence_by_requirement.values()
            ),
            assessment_count=len(evidence_matrix.assessments),
            warning_count=len(requirement_analysis.warnings)
            + len(evidence_matrix.warnings),
            draft_path=str(draft_path),
            status="completed_with_warnings"
            if requirement_analysis.warnings or evidence_matrix.warnings
            else "completed",
        )
        _write_json_exclusive(
            artifacts_directory / "rehearsal-report.json",
            {"schema_version": "1", **asdict(report)},
        )
        return RehearsalResult(
            report=report,
            ingestion=ingestion,
            requirement_analysis=requirement_analysis,
            evidence_matrix=evidence_matrix,
            draft=draft,
            artifacts_directory=artifacts_directory,
            draft_path=draft_path,
        )


def _tender_excerpts(ingestion: IngestionResult) -> tuple[TenderExcerpt, ...]:
    excerpts = [
        TenderExcerpt(
            document_id=document.document_id,
            relative_path=document.relative_path,
            passage_id=passage.passage_id,
            source_location=passage.source_location,
            text=passage.text,
        )
        for document in ingestion.documents
        for passage in document.passages
    ]
    if not excerpts:
        return ()
    return tuple(excerpts)


def _extraction_warnings(ingestion: IngestionResult) -> tuple[AnalysisWarning, ...]:
    warnings = [
        AnalysisWarning(warning.code, warning.message)
        for warning in ingestion.warnings
    ]
    for entry in ingestion.manifest:
        for warning in entry.warnings:
            warnings.append(
                AnalysisWarning(
                    code=warning.code,
                    message=warning.message,
                    document_id=entry.document_id,
                    relative_path=entry.relative_path,
                    source_location=warning.source_location,
                )
            )
    return tuple(warnings)


def _write_json_exclusive(path: Path, value: object) -> None:
    serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as output_file:
        output_file.write(serialized)
        output_file.flush()
        os.fsync(output_file.fileno())


def _require_disjoint(first: Path, second: Path, label: str) -> None:
    if first == second or first in second.parents or second in first.parents:
        raise RehearsalError(
            f"{label} must be separate from the other workflow directory"
        )
