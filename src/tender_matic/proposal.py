"""Local Markdown draft rendering for phase 6."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Mapping

from tender_matic.analysis import Requirement, RequirementAnalysis
from tender_matic.matching import (
    EvidenceMatrix,
    RequirementEvidenceAssessment,
)


class ProposalDraftError(ValueError):
    """Raised when phase outputs cannot safely produce a traceable draft."""


@dataclass(frozen=True)
class ProposalDraft:
    markdown: str


def render_markdown(
    requirement_analysis: RequirementAnalysis,
    evidence_matrix: EvidenceMatrix,
) -> ProposalDraft:
    """Render a validated phase 4/5 result with resolved local citations."""
    requirements = {
        requirement.requirement_id: requirement
        for requirement in requirement_analysis.requirements
    }
    if not requirements or len(requirements) != len(requirement_analysis.requirements):
        raise ProposalDraftError("Draft requires unique, non-empty requirement records")

    if dict(evidence_matrix.requirement_sources) != dict(
        requirement_analysis.source_references
    ):
        raise ProposalDraftError("Requirement source mappings do not match phase 4 output")

    assessments = _validated_assessments(evidence_matrix, requirements)
    used_tender_ids = {
        source_id for requirement in requirements.values() for source_id in requirement.source_ids
    }
    missing_tender_ids = used_tender_ids - set(requirement_analysis.source_references)
    if missing_tender_ids:
        raise ProposalDraftError("A requirement is missing a local tender source reference")

    used_evidence_ids = {
        evidence_id
        for assessment in assessments
        for evidence_id in assessment.evidence_ids
    }
    used_evidence_ids.update(
        evidence_id
        for assessment in assessments
        for item in (*assessment.questions, *assessment.risks)
        for evidence_id in item.evidence_ids
    )
    missing_evidence_ids = used_evidence_ids - set(evidence_matrix.evidence_sources)
    if missing_evidence_ids:
        raise ProposalDraftError("An assessment is missing a local proposal citation")

    tender_labels = {
        source_id: f"T{index}"
        for index, source_id in enumerate(sorted(used_tender_ids), start=1)
    }
    evidence_labels = {
        evidence_id: f"P{index}"
        for index, evidence_id in enumerate(sorted(used_evidence_ids), start=1)
    }
    lines = [
        "# Technical Proposal Draft",
        "",
        "> **Draft for BID review — not approved for submission.**",
        "",
        "This draft organizes tender requirements and historical proposal evidence. "
        "Historical proposal evidence records what was previously proposed; it does not "
        "establish current availability, delivery, or applicability.",
        "",
        "## Requirement and Evidence Matrix",
        "",
    ]

    assessments_by_id = {assessment.requirement_id: assessment for assessment in assessments}
    for requirement_id, requirement in requirements.items():
        assessment = assessments_by_id[requirement_id]
        lines.extend(
            [
                f"### {_inline(requirement_id)} — {_inline(assessment.status.title())}",
                "",
                f"**Requirement:** {_inline(requirement.text)}",
                "",
                f"**Extraction confidence:** {requirement.extraction_confidence:.2f}",
                "",
                f"**Assessment:** {_inline(assessment.rationale)}",
                "",
                f"**Tender sources:** {_citation_labels(requirement.source_ids, tender_labels)}",
                "",
                f"**Proposal evidence:** {_citation_labels(assessment.evidence_ids, evidence_labels)}",
                "",
            ]
        )
        if requirement.warnings:
            lines.append("**Requirement warnings:**")
            lines.extend(f"- {_inline(warning)}" for warning in requirement.warnings)
            lines.append("")
        if assessment.status == "gap":
            lines.extend(
                [
                    "**Gap:** No proposal evidence is accepted as support for this requirement. "
                    "Do not infer that the capability exists.",
                    "",
                ]
            )
        if assessment.status == "conflict":
            lines.extend(
                [
                    "**Conflict:** The cited proposals contain conflicting statements. "
                    "Resolve applicability with the BID team; proposal dates do not decide the conflict.",
                    "",
                ]
            )

    lines.extend(["## Gaps", ""])
    gaps = [item for item in assessments if item.status == "gap"]
    if gaps:
        for assessment in gaps:
            requirement = requirements[assessment.requirement_id]
            lines.append(
                f"- **{_inline(assessment.requirement_id)}:** {_inline(requirement.text)} "
                "— no supporting proposal evidence was established."
            )
    else:
        lines.append("No requirements were classified as gaps in the reviewed analysis.")
    lines.append("")

    lines.extend(["## Unresolved Conflicts", ""])
    conflicts = [item for item in assessments if item.status == "conflict"]
    if conflicts:
        for assessment in conflicts:
            lines.append(
                f"- **{_inline(assessment.requirement_id)}:** "
                f"{_citation_labels(assessment.evidence_ids, evidence_labels)} "
                f"{_inline(assessment.rationale)}"
            )
    else:
        lines.append("No proposal conflicts were classified in the reviewed analysis.")
    lines.append("")

    questions = [
        (assessment.requirement_id, question)
        for assessment in assessments
        for question in assessment.questions
    ]
    lines.extend(["## Clarification Questions", ""])
    if questions:
        for requirement_id, question in questions:
            lines.append(
                f"- **{_inline(requirement_id)}:** {_inline(question.text)} "
                f"{_citation_labels(question.evidence_ids, evidence_labels)}"
            )
    else:
        lines.append("No clarification questions were recorded.")
    lines.append("")

    risks = [
        (assessment.requirement_id, risk)
        for assessment in assessments
        for risk in assessment.risks
    ]
    lines.extend(["## Risks", ""])
    if risks:
        for requirement_id, risk in risks:
            lines.append(
                f"- **{_inline(requirement_id)}:** {_inline(risk.text)} "
                f"{_citation_labels(risk.evidence_ids, evidence_labels)}"
            )
    else:
        lines.append("No evidence-linked risks were recorded.")
    lines.append("")

    warnings = list(dict.fromkeys([
        f"{warning.code}: {warning.message}"
        for warning in requirement_analysis.warnings
    ] + [
        f"{warning.code}: {warning.message}"
        for warning in evidence_matrix.warnings
    ]))
    lines.extend(["## Extraction and Analysis Warnings", ""])
    if warnings:
        lines.extend(f"- {_inline(warning)}" for warning in warnings)
    else:
        lines.append("No extraction or analysis warnings were recorded.")
    lines.append("")

    lines.extend(["## Local Source References", ""])
    for source_id in sorted(used_tender_ids):
        reference = requirement_analysis.source_references[source_id]
        lines.extend(
            [
                f"- **[{tender_labels[source_id]}] Tender:** "
                f"{_inline(reference.relative_path)} — {_inline(reference.source_location)}",
            ]
        )
    for evidence_id in sorted(used_evidence_ids):
        citation = evidence_matrix.evidence_sources[evidence_id]
        lines.append(
            f"- **[{evidence_labels[evidence_id]}] Historical proposal:** "
            f"{_inline(citation.relative_path)} — {_inline(citation.source_location)}"
        )
    lines.append("")

    return ProposalDraft("\n".join(lines))


def write_markdown(
    draft: ProposalDraft,
    output_root: Path,
    relative_path: str | Path,
) -> Path:
    """Write a draft beneath output_root without overwriting an existing file."""
    if not isinstance(draft, ProposalDraft) or not draft.markdown.strip():
        raise ProposalDraftError("A non-empty ProposalDraft is required")

    root = output_root.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve(strict=True)
    relative = Path(relative_path)
    if (
        relative.is_absolute()
        or PureWindowsPath(str(relative_path)).is_absolute()
        or PureWindowsPath(str(relative_path)).drive
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ProposalDraftError("Output path must be a safe relative path")
    if relative.suffix.casefold() != ".md":
        raise ProposalDraftError("Draft output must use the .md extension")

    destination = resolved_root / relative
    resolved_parent = destination.parent.resolve(strict=False)
    try:
        resolved_parent.relative_to(resolved_root)
    except ValueError as error:
        raise ProposalDraftError("Output path escapes the designated draft directory") from error
    resolved_parent.mkdir(parents=True, exist_ok=True)
    resolved_destination = resolved_parent / destination.name
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=resolved_parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(draft.markdown)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        try:
            os.link(temporary_path, resolved_destination)
        except FileExistsError as error:
            raise ProposalDraftError("Refusing to overwrite an existing draft") from error
        return resolved_destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _validated_assessments(
    matrix: EvidenceMatrix, requirements: Mapping[str, Requirement]
) -> tuple[RequirementEvidenceAssessment, ...]:
    assessments = matrix.assessments
    if any(not isinstance(item, RequirementEvidenceAssessment) for item in assessments):
        raise ProposalDraftError("Evidence matrix contains an invalid assessment")
    assessment_ids = [assessment.requirement_id for assessment in assessments]
    if len(assessment_ids) != len(set(assessment_ids)) or set(assessment_ids) != set(
        requirements
    ):
        raise ProposalDraftError("Evidence matrix must have exactly one assessment per requirement")
    for assessment in assessments:
        if not isinstance(assessment.status, str) or assessment.status not in {
            "supported", "partial", "gap", "conflict"
        }:
            raise ProposalDraftError("Evidence matrix contains an invalid assessment status")
        evidence_ids = assessment.evidence_ids
        if (
            any(not isinstance(evidence_id, str) for evidence_id in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
            or any(evidence_id not in matrix.evidence_sources for evidence_id in evidence_ids)
        ):
            raise ProposalDraftError("Assessment refers to an unresolved proposal citation")
        if assessment.status in {"supported", "partial", "conflict"} and not evidence_ids:
            raise ProposalDraftError("Supported assessments must cite proposal evidence")
        if assessment.status == "conflict":
            paths = {
                matrix.evidence_sources[evidence_id].relative_path
                for evidence_id in evidence_ids
            }
            if len(paths) < 2 or not assessment.questions:
                raise ProposalDraftError(
                    "Conflicts require multiple proposal citations and a clarification question"
                )
        for item in (*assessment.questions, *assessment.risks):
            if any(
                evidence_id not in matrix.evidence_sources
                for evidence_id in item.evidence_ids
            ):
                raise ProposalDraftError("Question or risk refers to an unresolved citation")
        if any(not risk.evidence_ids for risk in assessment.risks):
            raise ProposalDraftError("Every risk must cite proposal evidence")

    for requirement in requirements.values():
        if (
            not requirement.source_ids
            or any(
                not isinstance(source_id, str)
                or source_id not in matrix.requirement_sources
                for source_id in requirement.source_ids
            )
        ):
            raise ProposalDraftError("Requirement is missing a local tender citation")
    return assessments


def _citation_labels(
    identifiers: tuple[str, ...], labels: Mapping[str, str]
) -> str:
    if not identifiers:
        return "None"
    return ", ".join(f"[{labels[identifier]}]" for identifier in identifiers)


def _inline(value: str) -> str:
    """Render model/user text as safe single-line Markdown text."""
    escaped = " ".join(value.split())
    escaped = escaped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for character in "\\`*_{}[]()#+-.!|":
        escaped = escaped.replace(character, f"\\{character}")
    return escaped
