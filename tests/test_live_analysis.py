"""Opt-in integration test; sends only synthetic tender text to Claude."""

import os
import unittest

from tender_matic.analysis import ClaudeMessagesAdapter, RequirementAnalyzer, TenderExcerpt
from tender_matic.privacy import LocalDeidentifier


class LiveClaudeAnalysisTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("TENDER_MATIC_RUN_LIVE_CLAUDE_TEST") == "1",
        "set TENDER_MATIC_RUN_LIVE_CLAUDE_TEST=1 to opt in",
    )
    def test_extracts_a_requirement_from_synthetic_text(self):
        model_name = os.environ.get("TENDER_MATIC_CLAUDE_MODEL")
        if not model_name:
            self.fail("Set TENDER_MATIC_CLAUDE_MODEL locally for the opted-in test")
        adapter = ClaudeMessagesAdapter(model_name)
        analyzer = RequirementAnalyzer(adapter, LocalDeidentifier({}), lambda *_: True)
        excerpt = TenderExcerpt(
            document_id="synthetic-live-test",
            relative_path="synthetic/tender.txt",
            passage_id="synthetic-passage-01",
            source_location="line:1",
            text=(
                "Synthetic tender requirement: the system must support "
                "multi-factor authentication."
            ),
        )

        result = analyzer.analyze([excerpt])

        self.assertTrue(result.requirements)
        self.assertTrue(result.requirements[0].source_ids)
        self.assertTrue(result.requirements[0].extraction_confidence > 0)


if __name__ == "__main__":
    unittest.main()
