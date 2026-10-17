import tempfile
import unittest
from pathlib import Path

from tender_matic.analysis import (
    AnalysisWarning,
    Requirement,
    RequirementAnalysis,
    TenderSourceReference,
)
from tender_matic.corpus import LocalCitation
from tender_matic.matching import (
    ClarificationQuestion,
    EvidenceMatrix,
    EvidenceRisk,
    EvidenceWarning,
    RequirementEvidenceAssessment,
)
from tender_matic.proposal import (
    ProposalDraftError,
    render_markdown,
    write_markdown,
)


class ProposalDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analysis = RequirementAnalysis(
            requirements=(
                Requirement(
                    "req_001",
                    "Support multi-factor authentication.",
                    ("tender_01",),
                    0.96,
                    (),
                ),
                Requirement(
                    "req_002",
                    "Provide 99.99% availability.",
                    ("tender_02",),
                    0.83,
                    ("The measurement period is unspecified.",),
                ),
                Requirement(
                    "req_003",
                    "Support delegated administration.",
                    ("tender_03",),
                    0.72,
                    (),
                ),
            ),
            source_references={
                "tender_01": TenderSourceReference(
                    "tender_doc",
                    "tender/requirements.md",
                    "p1",
                    "line:10",
                ),
                "tender_02": TenderSourceReference(
                    "tender_doc",
                    "tender/requirements.md",
                    "p2",
                    "line:20",
                ),
                "tender_03": TenderSourceReference(
                    "tender_doc",
                    "tender/requirements.md",
                    "p3",
                    "line:30",
                ),
            },
            warnings=(
                AnalysisWarning(
                    "partial_extraction",
                    "A synthetic page had no text layer.",
                    "tender_doc",
                    "tender/requirements.md",
                    "page:4",
                ),
            ),
        )
        self.matrix = EvidenceMatrix(
            assessments=(
                RequirementEvidenceAssessment(
                    "req_001",
                    "supported",
                    ("evidence_01",),
                    "The passage describes multi-factor authentication.",
                    (ClarificationQuestion("Is phishing-resistant MFA required?", ()),),
                    (EvidenceRisk("Current availability requires confirmation.", ("evidence_01",)),),
                ),
                RequirementEvidenceAssessment(
                    "req_002",
                    "gap",
                    (),
                    "No proposal evidence establishes this availability target.",
                    (),
                    (),
                ),
                RequirementEvidenceAssessment(
                    "req_003",
                    "conflict",
                    ("evidence_02", "evidence_03"),
                    "Two historical proposals describe incompatible delegation models.",
                    (
                        ClarificationQuestion(
                            "Which delegation model is applicable?",
                            ("evidence_02", "evidence_03"),
                        ),
                    ),
                    (),
                ),
            ),
            requirement_sources=self.analysis.source_references,
            evidence_sources={
                "evidence_01": LocalCitation(
                    "proposals/security.md", "section:Authentication", "2023-01-01", "en"
                ),
                "evidence_02": LocalCitation(
                    "proposals/admin-a.md", "section:Delegation", "2020-01-01", "en"
                ),
                "evidence_03": LocalCitation(
                    "proposals/admin-b.md", "section:Administration", "2025-01-01", "en"
                ),
            },
            warnings=(
                EvidenceWarning("model_warning", "The answer needs human confirmation."),
            ),
        )

    def test_golden_markdown_includes_sections_statuses_and_local_citations(self) -> None:
        draft = render_markdown(self.analysis, self.matrix)

        self.assertEqual(
            draft.markdown,
            """# Technical Proposal Draft

> **Draft for BID review — not approved for submission.**

This draft organizes tender requirements and historical proposal evidence. Historical proposal evidence records what was previously proposed; it does not establish current availability, delivery, or applicability.

## Requirement and Evidence Matrix

### req\\_001 — Supported

**Requirement:** Support multi\\-factor authentication\\.

**Extraction confidence:** 0.96

**Assessment:** The passage describes multi\\-factor authentication\\.

**Tender sources:** [T1]

**Proposal evidence:** [P1]

### req\\_002 — Gap

**Requirement:** Provide 99\\.99% availability\\.

**Extraction confidence:** 0.83

**Assessment:** No proposal evidence establishes this availability target\\.

**Tender sources:** [T2]

**Proposal evidence:** None

**Requirement warnings:**
- The measurement period is unspecified\\.

**Gap:** No proposal evidence is accepted as support for this requirement. Do not infer that the capability exists.

### req\\_003 — Conflict

**Requirement:** Support delegated administration\\.

**Extraction confidence:** 0.72

**Assessment:** Two historical proposals describe incompatible delegation models\\.

**Tender sources:** [T3]

**Proposal evidence:** [P2], [P3]

**Conflict:** The cited proposals contain conflicting statements. Resolve applicability with the BID team; proposal dates do not decide the conflict.

## Gaps

- **req\\_002:** Provide 99\\.99% availability\\. — no supporting proposal evidence was established.

## Unresolved Conflicts

- **req\\_003:** [P2], [P3] Two historical proposals describe incompatible delegation models\\.

## Clarification Questions

- **req\\_001:** Is phishing\\-resistant MFA required? None
- **req\\_003:** Which delegation model is applicable? [P2], [P3]

## Risks

- **req\\_001:** Current availability requires confirmation\\. [P1]

## Extraction and Analysis Warnings

- partial\\_extraction: A synthetic page had no text layer\\.
- model\\_warning: The answer needs human confirmation\\.

## Local Source References

- **[T1] Tender:** tender/requirements\\.md — line:10
- **[T2] Tender:** tender/requirements\\.md — line:20
- **[T3] Tender:** tender/requirements\\.md — line:30
- **[P1] Historical proposal:** proposals/security\\.md — section:Authentication
- **[P2] Historical proposal:** proposals/admin\\-a\\.md — section:Delegation
- **[P3] Historical proposal:** proposals/admin\\-b\\.md — section:Administration
""",
        )
        self.assertNotIn("2020-01-01", draft.markdown)
        self.assertNotIn("2025-01-01", draft.markdown)

    def test_escapes_untrusted_markdown_and_html_in_content(self) -> None:
        analysis = RequirementAnalysis(
            (
                Requirement(
                    "req_001",
                    "<script>alert(1)</script> [unsafe] | content",
                    ("tender_01",),
                    0.8,
                    (),
                ),
            ),
            self.analysis.source_references,
            (),
        )
        matrix = EvidenceMatrix(
            (
                RequirementEvidenceAssessment(
                    "req_001", "gap", (), "No evidence.", (), ()
                ),
            ),
            self.analysis.source_references,
            {},
            (),
        )

        rendered = render_markdown(analysis, matrix).markdown

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("\\[unsafe\\]", rendered)
        self.assertIn("\\| content", rendered)

    def test_rejects_missing_assessment_or_source_mapping(self) -> None:
        missing_assessment = EvidenceMatrix(
            (),
            self.analysis.source_references,
            {},
            (),
        )
        with self.assertRaisesRegex(ProposalDraftError, "one assessment"):
            render_markdown(self.analysis, missing_assessment)

        mismatched_sources = EvidenceMatrix(
            self.matrix.assessments,
            {},
            self.matrix.evidence_sources,
            self.matrix.warnings,
        )
        with self.assertRaisesRegex(ProposalDraftError, "source mappings"):
            render_markdown(self.analysis, mismatched_sources)

    def test_rejects_missing_evidence_citation(self) -> None:
        matrix = EvidenceMatrix(
            self.matrix.assessments,
            self.matrix.requirement_sources,
            {},
            self.matrix.warnings,
        )

        with self.assertRaisesRegex(ProposalDraftError, "unresolved proposal citation"):
            render_markdown(self.analysis, matrix)

    def test_deduplicates_phase_warnings_carried_forward_by_matching(self) -> None:
        warning = EvidenceWarning(
            "partial_extraction",
            "A synthetic page had no text layer.",
        )
        matrix = EvidenceMatrix(
            self.matrix.assessments,
            self.matrix.requirement_sources,
            self.matrix.evidence_sources,
            (*self.matrix.warnings, warning),
        )

        rendered = render_markdown(self.analysis, matrix).markdown

        self.assertEqual(
            rendered.count("- partial\\_extraction: A synthetic page had no text layer\\."),
            1,
        )

    def test_writes_markdown_inside_output_root_without_overwrite(self) -> None:
        draft = render_markdown(self.analysis, self.matrix)
        with tempfile.TemporaryDirectory() as temp_directory:
            output_root = Path(temp_directory) / "drafts"
            output_file = write_markdown(draft, output_root, "run/final.md")

            self.assertEqual(output_file, output_root / "run" / "final.md")
            self.assertEqual(output_file.read_text(encoding="utf-8"), draft.markdown)
            with self.assertRaisesRegex(ProposalDraftError, "Refusing to overwrite"):
                write_markdown(draft, output_root, "run/final.md")

    def test_rejects_traversal_absolute_and_non_markdown_output_paths(self) -> None:
        draft = render_markdown(self.analysis, self.matrix)
        with tempfile.TemporaryDirectory() as temp_directory:
            output_root = Path(temp_directory) / "drafts"
            for path in ("../outside.md", "/tmp/outside.md", "report.txt", "C:\\outside.md"):
                with self.subTest(path=path):
                    with self.assertRaises(ProposalDraftError):
                        write_markdown(draft, output_root, path)
            self.assertFalse((Path(temp_directory) / "outside.md").exists())

    def test_rejects_symlinked_output_directory_that_escapes_root(self) -> None:
        draft = render_markdown(self.analysis, self.matrix)
        with tempfile.TemporaryDirectory() as temp_directory:
            base = Path(temp_directory)
            output_root = base / "drafts"
            outside = base / "outside"
            output_root.mkdir()
            outside.mkdir()
            try:
                (output_root / "linked").symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"Symlinks are unavailable: {error}")

            with self.assertRaisesRegex(ProposalDraftError, "escapes"):
                write_markdown(draft, output_root, "linked/escape.md")
            self.assertFalse((outside / "escape.md").exists())


if __name__ == "__main__":
    unittest.main()
