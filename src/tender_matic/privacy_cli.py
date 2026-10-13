"""Attended command-line privacy review for a single local excerpt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tender_matic.privacy import LocalDeidentifier, PrivacyGateError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Redact and locally review an excerpt before any outbound use."
    )
    parser.add_argument("--input", required=True, type=Path, help="Local UTF-8 text excerpt")
    parser.add_argument(
        "--identifiers",
        required=True,
        type=Path,
        help="Local JSON map of identifier values to categories",
    )
    parser.add_argument("--output", required=True, type=Path, help="New local JSON output file")
    arguments = parser.parse_args()

    input_path = arguments.input.resolve(strict=True)
    identifiers_path = arguments.identifiers.resolve(strict=True)
    output_path = arguments.output.resolve()
    if not input_path.is_file() or not identifiers_path.is_file():
        print("Input and identifier registry must be files.", file=sys.stderr)
        return 2
    if output_path in {input_path, identifiers_path}:
        print("Output must not overwrite the input or identifier registry.", file=sys.stderr)
        return 2
    if output_path.exists():
        print("Output already exists; choose a new path.", file=sys.stderr)
        return 2

    try:
        source_text = input_path.read_text(encoding="utf-8")
        registry = json.loads(identifiers_path.read_text(encoding="utf-8"))
        if not isinstance(registry, dict) or not all(
            isinstance(value, str) and isinstance(category, str)
            for value, category in registry.items()
        ):
            raise ValueError("Identifier registry must be a JSON object of string values")
        deidentifier = LocalDeidentifier(registry)
        result = deidentifier.sanitize(source_text)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not prepare excerpt: {error}", file=sys.stderr)
        return 2

    print("Sanitized preview (compare it with the source document locally):")
    print(result.sanitized_text)
    print(
        json.dumps(
            {
                "human_review_required": result.human_review_required,
                "findings": [finding.__dict__ for finding in result.findings],
            },
            indent=2,
            sort_keys=True,
        )
    )
    try:
        approval = input(
            "Confirm that no customer-identifying information remains? Type APPROVE: "
        )
        excerpt = deidentifier.authorize_for_outbound(
            result,
            reviewer_confirmed_no_customer_identifiers=approval == "APPROVE",
        )
    except (EOFError, PrivacyGateError) as error:
        print(f"Excerpt not approved: {error}", file=sys.stderr)
        return 1

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8") as output_file:
            json.dump({"text": excerpt.text}, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
    except OSError as error:
        print(f"Could not write sanitized output: {error}", file=sys.stderr)
        return 2

    print(f"Sanitized excerpt written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())