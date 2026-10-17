import io
import json
import unittest
from unittest.mock import patch

from tender_matic.analysis import (
    ANALYSIS_SYSTEM_PROMPT,
    ANTHROPIC_API_VERSION,
    ANTHROPIC_MESSAGES_URL,
    AnalysisWarning,
    ClaudeAPIError,
    ClaudeMessagesAdapter,
    RequirementAnalysisError,
    RequirementAnalyzer,
    TenderExcerpt,
)
from tender_matic.privacy import LocalDeidentifier, PrivacyGateError


class FakeAnalysisModel:
    def __init__(self, response_factory=None):
        self.response_factory = response_factory
        self.response_text = None
        self.calls = []

    def complete(self, system_prompt, user_content):
        self.calls.append((system_prompt, user_content))
        if self.response_factory is not None:
            return self.response_factory(json.loads(user_content))
        return self.response_text


def requirement_response(sources, *, confidence=0.94, warnings=None):
    source_id = sources["sources"][0]["source_id"]
    return json.dumps(
        {
            "requirements": [
                {
                    "text": "Support multi-factor authentication.",
                    "source_ids": [source_id],
                    "confidence": confidence,
                    "warnings": [],
                }
            ],
            "warnings": warnings or [],
        }
    )


class RequirementAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.excerpt = TenderExcerpt(
            document_id="synthetic-document-01",
            relative_path="tender/synthetic.txt",
            passage_id="passage-01",
            source_location="line:12",
            text="Example Customer requires multi-factor authentication at "
            "https://synthetic.invalid.",
        )

    def test_sends_only_reviewed_deidentified_text_and_resolves_source_locally(self):
        model = FakeAnalysisModel(response_factory=requirement_response)
        reviewed = []

        def reviewer(context, result):
            reviewed.append((context, result))
            return True

        analyzer = RequirementAnalyzer(
            model,
            LocalDeidentifier({"Example Customer": "CUSTOMER_NAME"}),
            reviewer,
        )
        analysis = analyzer.analyze([self.excerpt])

        self.assertEqual(len(reviewed), 1)
        self.assertEqual(reviewed[0][0].original_text, self.excerpt.text)
        self.assertNotIn("Example Customer", reviewed[0][1].sanitized_text)
        self.assertEqual(model.calls[0][0], ANALYSIS_SYSTEM_PROMPT)
        sent_content = model.calls[0][1]
        self.assertNotIn("Example Customer", sent_content)
        self.assertNotIn("https://synthetic.invalid", sent_content)
        self.assertNotIn("tender/synthetic.txt", sent_content)
        self.assertNotIn("line:12", sent_content)
        self.assertEqual(len(analysis.requirements), 1)
        requirement = analysis.requirements[0]
        self.assertEqual(requirement.requirement_id, "req_001")
        self.assertEqual(requirement.extraction_confidence, 0.94)
        local_source = analysis.source_references[requirement.source_ids[0]]
        self.assertEqual(local_source.relative_path, "tender/synthetic.txt")
        self.assertEqual(local_source.source_location, "line:12")

    def test_denied_review_blocks_model_request(self):
        model = FakeAnalysisModel(response_factory=requirement_response)
        analyzer = RequirementAnalyzer(
            model,
            LocalDeidentifier({}),
            lambda _context, _result: False,
        )

        with self.assertRaises(PrivacyGateError):
            analyzer.analyze([self.excerpt])

        self.assertEqual(model.calls, [])

    def test_all_excerpts_are_reviewed_before_the_model_is_called(self):
        model = FakeAnalysisModel(response_factory=requirement_response)
        review_count = 0

        def reviewer(_context, _result):
            nonlocal review_count
            review_count += 1
            return review_count == 1

        analyzer = RequirementAnalyzer(model, LocalDeidentifier({}), reviewer)
        second_excerpt = TenderExcerpt(
            document_id="synthetic-document-02",
            relative_path="tender/second.txt",
            passage_id="passage-02",
            source_location="page:2",
            text="A second synthetic requirement.",
        )

        with self.assertRaises(PrivacyGateError):
            analyzer.analyze([self.excerpt, second_excerpt])

        self.assertEqual(review_count, 2)
        self.assertEqual(model.calls, [])

    def test_extraction_and_model_warnings_are_preserved(self):
        model = FakeAnalysisModel(
            response_factory=lambda _sources: json.dumps(
                {
                    "requirements": [],
                    "warnings": ["The source wording is ambiguous."],
                }
            )
        )
        analyzer = RequirementAnalyzer(model, LocalDeidentifier({}), lambda *_: True)

        analysis = analyzer.analyze(
            [self.excerpt],
            extraction_warnings=[
                AnalysisWarning(
                    "ocr_required_or_empty_page",
                    "One page had no text layer.",
                    document_id=self.excerpt.document_id,
                    relative_path=self.excerpt.relative_path,
                    source_location="page:13",
                )
            ],
        )

        self.assertEqual(
            [warning.code for warning in analysis.warnings],
            ["ocr_required_or_empty_page", "model_warning", "no_requirements_extracted"],
        )
        self.assertEqual(analysis.warnings[0].source_location, "page:13")

    def test_rejects_malformed_json(self):
        model = FakeAnalysisModel()
        model.response_text = "not JSON"
        analyzer = RequirementAnalyzer(model, LocalDeidentifier({}), lambda *_: True)

        with self.assertRaisesRegex(RequirementAnalysisError, "valid JSON"):
            analyzer.analyze([self.excerpt])

    def test_rejects_duplicate_json_fields(self):
        model = FakeAnalysisModel()
        model.response_text = (
            '{"requirements":[],"requirements":[],"warnings":[]}'
        )
        analyzer = RequirementAnalyzer(model, LocalDeidentifier({}), lambda *_: True)

        with self.assertRaisesRegex(RequirementAnalysisError, "valid JSON"):
            analyzer.analyze([self.excerpt])

    def test_rejects_unknown_source_reference(self):
        model = FakeAnalysisModel(
            response_factory=lambda _sources: json.dumps(
                {
                    "requirements": [
                        {
                            "text": "A synthetic requirement.",
                            "source_ids": ["src_not_provided"],
                            "confidence": 0.8,
                            "warnings": [],
                        }
                    ],
                    "warnings": [],
                }
            )
        )
        analyzer = RequirementAnalyzer(model, LocalDeidentifier({}), lambda *_: True)

        with self.assertRaisesRegex(RequirementAnalysisError, "unknown source ID"):
            analyzer.analyze([self.excerpt])

    def test_rejects_invalid_confidence(self):
        model = FakeAnalysisModel(
            response_factory=lambda sources: requirement_response(
                sources, confidence=True
            )
        )
        analyzer = RequirementAnalyzer(model, LocalDeidentifier({}), lambda *_: True)

        with self.assertRaisesRegex(RequirementAnalysisError, "confidence"):
            analyzer.analyze([self.excerpt])

    def test_rejects_requirement_without_source_reference(self):
        model = FakeAnalysisModel(
            response_factory=lambda _sources: json.dumps(
                {
                    "requirements": [
                        {
                            "text": "A synthetic requirement.",
                            "source_ids": [],
                            "confidence": 0.8,
                            "warnings": [],
                        }
                    ],
                    "warnings": [],
                }
            )
        )
        analyzer = RequirementAnalyzer(model, LocalDeidentifier({}), lambda *_: True)

        with self.assertRaisesRegex(RequirementAnalysisError, "at least one source ID"):
            analyzer.analyze([self.excerpt])

    def test_blocks_model_response_with_known_customer_identifier(self):
        model = FakeAnalysisModel(
            response_factory=lambda sources: json.dumps(
                {
                    "requirements": [
                        {
                            "text": "Example Customer requires secure sign-in.",
                            "source_ids": [sources["sources"][0]["source_id"]],
                            "confidence": 0.9,
                            "warnings": [],
                        }
                    ],
                    "warnings": [],
                }
            )
        )
        analyzer = RequirementAnalyzer(
            model,
            LocalDeidentifier({"Example Customer": "CUSTOMER_NAME"}),
            lambda *_: True,
        )

        with self.assertRaisesRegex(RequirementAnalysisError, "potential direct identifier"):
            analyzer.analyze([self.excerpt])

    def test_rejects_empty_excerpt_set(self):
        model = FakeAnalysisModel()
        analyzer = RequirementAnalyzer(model, LocalDeidentifier({}), lambda *_: True)

        with self.assertRaisesRegex(RequirementAnalysisError, "(?i)at least one"):
            analyzer.analyze([])

        self.assertEqual(model.calls, [])


class ClaudeMessagesAdapterTests(unittest.TestCase):
    def test_sends_messages_api_request_and_returns_text(self):
        response = io.BytesIO(
            json.dumps(
                {
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": '{"requirements":[]}'}],
                }
            ).encode("utf-8")
        )
        adapter = ClaudeMessagesAdapter(
            "claude-synthetic-model",
            api_key="local-test-key",
            timeout=4,
            max_tokens=1024,
        )

        with patch(
            "tender_matic.analysis.urllib.request.urlopen", return_value=response
        ) as urlopen:
            result = adapter.complete("system", '{"sources": []}')

        request = urlopen.call_args.args[0]
        sent_body = json.loads(request.data)
        self.assertEqual(result, '{"requirements":[]}')
        self.assertEqual(request.full_url, ANTHROPIC_MESSAGES_URL)
        self.assertEqual(request.get_header("Anthropic-version"), ANTHROPIC_API_VERSION)
        self.assertEqual(request.get_header("X-api-key"), "local-test-key")
        self.assertEqual(sent_body["model"], "claude-synthetic-model")
        self.assertEqual(sent_body["messages"][0]["content"], '{"sources": []}')
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 4)

    def test_rejects_incomplete_api_response(self):
        response = io.BytesIO(
            json.dumps(
                {
                    "stop_reason": "max_tokens",
                    "content": [{"type": "text", "text": "{}"}],
                }
            ).encode("utf-8")
        )
        adapter = ClaudeMessagesAdapter("claude-synthetic-model", api_key="test")

        with patch(
            "tender_matic.analysis.urllib.request.urlopen", return_value=response
        ):
            with self.assertRaises(ClaudeAPIError):
                adapter.complete("system", "content")


if __name__ == "__main__":
    unittest.main()
