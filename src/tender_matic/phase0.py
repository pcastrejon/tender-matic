"""Phase 0 contracts for a local runner using Claude API tool use.

This module deliberately contains no API client and performs no network calls.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping


WORKSPACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "inspect_workspace",
        "description": (
            "Return a synthetic, non-sensitive summary for an allowlisted "
            "workspace. This phase 0 tool does not read source files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9_-]{1,64}$",
                }
            },
            "required": ["workspace_id"],
            "additionalProperties": False,
        },
    }
]


class ToolCallError(ValueError):
    """Raised when a model tool request violates the local tool contract."""


class PromptPrivacyError(ValueError):
    """Raised when a prompt contains a locally configured blocked term."""


class PromptPrivacyGuard:
    """Block known sensitive terms before a prompt is sent to a model.

    This exact-term guard is only a phase 0 contract probe. It is not a
    de-identification system and must not be used as the production privacy gate.
    """

    def __init__(self, blocked_terms: list[str]) -> None:
        self._blocked_terms = tuple(
            term.strip().casefold() for term in blocked_terms if term.strip()
        )

    def validate(self, prompt: str) -> None:
        normalized_prompt = prompt.casefold()
        if any(term in normalized_prompt for term in self._blocked_terms):
            raise PromptPrivacyError("Prompt contains a configured sensitive term")


def resolve_workspace_path(workspace_root: Path, relative_path: str) -> Path:
    """Resolve a path and reject absolute paths or traversal outside the workspace."""
    requested_path = Path(relative_path)
    if requested_path.is_absolute():
        raise PermissionError("Absolute paths are not allowed")

    resolved_root = workspace_root.resolve(strict=True)
    resolved_path = (resolved_root / requested_path).resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise PermissionError("Path is outside the designated workspace") from error
    return resolved_path


def execute_tool_use(
    tool_use: Mapping[str, Any],
    workspace_summaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate and execute one synthetic Anthropic API tool_use block."""
    tool_use_id = tool_use.get("id")
    tool_name = tool_use.get("name")
    tool_input = tool_use.get("input")

    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise ToolCallError("tool_use id is required")
    if tool_name != "inspect_workspace":
        raise ToolCallError("Tool is not allowlisted")
    if not isinstance(tool_input, dict) or set(tool_input) != {"workspace_id"}:
        raise ToolCallError("Tool input does not match the allowed schema")

    workspace_id = tool_input["workspace_id"]
    if not isinstance(workspace_id, str) or not WORKSPACE_ID_PATTERN.fullmatch(
        workspace_id
    ):
        raise ToolCallError("workspace_id is invalid")
    if workspace_id not in workspace_summaries:
        raise ToolCallError("Workspace is not allowlisted")

    summary = dict(workspace_summaries[workspace_id])
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(summary, sort_keys=True),
        "is_error": False,
    }


DEMO_WORKSPACE_SUMMARIES: dict[str, dict[str, Any]] = {
    "demo": {
        "workspace_id": "demo",
        "status": "ready",
        "document_count": 2,
        "formats": ["pdf", "docx"],
    }
}

DEMO_BLOCKED_TERMS = ["Example Customer Ltd", "42 Test Street"]


def run_phase0_demo(prompt: str) -> dict[str, Any]:
    """Run the prompt-to-tool flow with a deterministic fake Claude response."""
    if not prompt.strip():
        raise ValueError("A non-empty prompt is required")

    PromptPrivacyGuard(DEMO_BLOCKED_TERMS).validate(prompt)
    simulated_tool_use = {
        "type": "tool_use",
        "id": "toolu_phase0_demo",
        "name": "inspect_workspace",
        "input": {"workspace_id": "demo"},
    }
    tool_result = execute_tool_use(simulated_tool_use, DEMO_WORKSPACE_SUMMARIES)
    return {
        "mode": "simulation",
        "assistant_message": "Synthetic workspace inspected; no files were read.",
        "workspace_summary": json.loads(tool_result["content"]),
    }


def main() -> int:
    prompt = " ".join(sys.argv[1:])
    try:
        result = run_phase0_demo(prompt)
    except (PromptPrivacyError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())