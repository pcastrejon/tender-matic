import json
import tempfile
import unittest
from pathlib import Path

from tender_matic.phase0 import (
    DEMO_WORKSPACE_SUMMARIES,
    TOOL_DEFINITIONS,
    PromptPrivacyError,
    PromptPrivacyGuard,
    ToolCallError,
    execute_tool_use,
    resolve_workspace_path,
    run_phase0_demo,
)


class PromptPrivacyGuardTests(unittest.TestCase):
    def test_blocks_configured_customer_name_and_address(self) -> None:
        guard = PromptPrivacyGuard(["Example Customer Ltd", "42 Test Street"])

        with self.assertRaises(PromptPrivacyError):
            guard.validate("Analyze the tender for Example Customer Ltd")

        with self.assertRaises(PromptPrivacyError):
            guard.validate("The delivery location is 42 Test Street")

    def test_allows_prompt_without_configured_terms(self) -> None:
        guard = PromptPrivacyGuard(["Example Customer Ltd"])

        guard.validate("Analyze workspace demo and prepare an evidence summary")


class ToolContractTests(unittest.TestCase):
    def test_prompt_runs_the_fake_claude_tool_use_flow(self) -> None:
        result = run_phase0_demo("Inspect workspace demo and summarize its status")

        self.assertEqual(result["mode"], "simulation")
        self.assertEqual(result["workspace_summary"]["workspace_id"], "demo")
        self.assertIn("no files were read", result["assistant_message"])

    def test_demo_rejects_configured_customer_identifier(self) -> None:
        with self.assertRaises(PromptPrivacyError):
            run_phase0_demo("Analyze the tender for Example Customer Ltd")

    def test_tool_schema_has_no_path_or_document_content_argument(self) -> None:
        schema = TOOL_DEFINITIONS[0]["input_schema"]

        self.assertEqual(schema["required"], ["workspace_id"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["properties"]), {"workspace_id"})

    def test_executes_allowlisted_synthetic_tool_and_returns_no_file_content(self) -> None:
        tool_result = execute_tool_use(
            {
                "type": "tool_use",
                "id": "toolu_test_001",
                "name": "inspect_workspace",
                "input": {"workspace_id": "demo"},
            },
            DEMO_WORKSPACE_SUMMARIES,
        )

        self.assertEqual(tool_result["type"], "tool_result")
        self.assertEqual(tool_result["tool_use_id"], "toolu_test_001")
        self.assertNotIn("raw_text", tool_result["content"])
        self.assertNotIn("file_name", tool_result["content"])
        self.assertEqual(json.loads(tool_result["content"]), DEMO_WORKSPACE_SUMMARIES["demo"])

    def test_rejects_unknown_tool(self) -> None:
        with self.assertRaises(ToolCallError):
            execute_tool_use(
                {
                    "id": "toolu_test_002",
                    "name": "read_arbitrary_file",
                    "input": {"workspace_id": "demo"},
                },
                DEMO_WORKSPACE_SUMMARIES,
            )

    def test_rejects_extra_arguments(self) -> None:
        with self.assertRaises(ToolCallError):
            execute_tool_use(
                {
                    "id": "toolu_test_003",
                    "name": "inspect_workspace",
                    "input": {
                        "workspace_id": "demo",
                        "path": "../../secrets.txt",
                    },
                },
                DEMO_WORKSPACE_SUMMARIES,
            )

    def test_rejects_unknown_workspace(self) -> None:
        with self.assertRaises(ToolCallError):
            execute_tool_use(
                {
                    "id": "toolu_test_004",
                    "name": "inspect_workspace",
                    "input": {"workspace_id": "not-allowlisted"},
                },
                DEMO_WORKSPACE_SUMMARIES,
            )


class WorkspaceBoundaryTests(unittest.TestCase):
    def test_resolves_file_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace_root = Path(directory)
            source_file = workspace_root / "input" / "tender.txt"
            source_file.parent.mkdir()
            source_file.write_text("synthetic tender", encoding="utf-8")

            resolved = resolve_workspace_path(workspace_root, "input/tender.txt")

            self.assertEqual(resolved, source_file.resolve())

    def test_rejects_parent_traversal_and_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace_root = Path(directory)

            with self.assertRaises(PermissionError):
                resolve_workspace_path(workspace_root, "../outside.txt")

            with self.assertRaises(PermissionError):
                resolve_workspace_path(workspace_root, "/etc/passwd")

    def test_rejects_symlink_that_resolves_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base_path = Path(directory)
            workspace_root = base_path / "workspace"
            outside_file = base_path / "outside.txt"
            workspace_root.mkdir()
            outside_file.write_text("synthetic secret", encoding="utf-8")
            (workspace_root / "linked.txt").symlink_to(outside_file)

            with self.assertRaises(PermissionError):
                resolve_workspace_path(workspace_root, "linked.txt")


if __name__ == "__main__":
    unittest.main()