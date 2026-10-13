import json
import io
import tempfile
import unittest
from dataclasses import asdict
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from tender_matic.privacy_cli import main as privacy_cli_main
from tender_matic.privacy import DeidentificationResult, LocalDeidentifier, PrivacyGateError


class LocalDeidentifierTests(unittest.TestCase):
    def test_redacts_configured_customer_values_case_insensitively(self) -> None:
        deidentifier = LocalDeidentifier(
            {
                "Example Customer Ltd": "CUSTOMER_NAME",
                "42 Example Road, Madrid": "CUSTOMER_ADDRESS",
            }
        )

        result = deidentifier.sanitize(
            "Example Customer Ltd operates at 42 Example Road, Madrid. "
            "EXAMPLE CUSTOMER LTD is the customer."
        )

        self.assertNotIn("Example Customer Ltd", result.sanitized_text)
        self.assertNotIn("42 Example Road, Madrid", result.sanitized_text)
        self.assertEqual(result.sanitized_text.count("[CUSTOMER_NAME_001]"), 2)
        self.assertIn("[CUSTOMER_ADDRESS_001]", result.sanitized_text)
        self.assertEqual(deidentifier.local_mapping["[CUSTOMER_NAME_001]"], "Example Customer Ltd")

    def test_redacts_common_direct_identifier_patterns(self) -> None:
        deidentifier = LocalDeidentifier({})
        raw_text = (
            "Contact bid@example.test or +1 (555) 010-2222. "
            "Portal https://customer.example.test/tender. "
            "Customer ID: ACME-991. Server 192.0.2.10."
        )

        result = deidentifier.sanitize(raw_text)

        for direct_identifier in (
            "bid@example.test",
            "+1 (555) 010-2222",
            "https://customer.example.test/tender",
            "Customer ID: ACME-991",
            "192.0.2.10",
        ):
            self.assertNotIn(direct_identifier, result.sanitized_text)
        self.assertEqual(len(result.findings), 5)

    def test_flags_and_redacts_a_potential_location_for_review(self) -> None:
        result = LocalDeidentifier({}).sanitize(
            "The delivery facility is located in San Sebastian."
        )

        self.assertNotIn("San Sebastian", result.sanitized_text)
        self.assertIn("POTENTIAL_LOCATION", {finding.category for finding in result.findings})
        self.assertTrue(result.human_review_required)

    def test_repeated_value_uses_same_token_without_exposing_map(self) -> None:
        deidentifier = LocalDeidentifier({"Example Customer": "CUSTOMER_NAME"})
        result = deidentifier.sanitize("Example Customer and Example Customer")
        outbound = deidentifier.authorize_for_outbound(
            result,
            reviewer_confirmed_no_customer_identifiers=True,
        )
        outbound_json = json.dumps(asdict(outbound))

        self.assertEqual(result.sanitized_text.count("[CUSTOMER_NAME_001]"), 2)
        self.assertNotIn("Example Customer", outbound_json)
        self.assertNotIn("local_mapping", outbound_json)
        self.assertEqual(set(asdict(outbound)), {"text"})

    def test_blocks_outbound_release_without_human_confirmation(self) -> None:
        deidentifier = LocalDeidentifier({})
        result = deidentifier.sanitize("A technical requirement without direct identifiers.")

        with self.assertRaises(PrivacyGateError):
            deidentifier.authorize_for_outbound(
                result,
                reviewer_confirmed_no_customer_identifiers=False,
            )

    def test_does_not_release_empty_content(self) -> None:
        deidentifier = LocalDeidentifier({})
        with self.assertRaises(ValueError):
            deidentifier.sanitize("   ")

        with self.assertRaises(PrivacyGateError):
            deidentifier.authorize_for_outbound(
                DeidentificationResult("   ", ()),
                reviewer_confirmed_no_customer_identifiers=True,
            )

    def test_does_not_treat_lowercase_generic_location_as_a_proper_name(self) -> None:
        result = LocalDeidentifier({}).sanitize("The system is located in a secure facility.")

        self.assertEqual(result.sanitized_text, "The system is located in a secure facility.")

    def test_rejects_invalid_identifier_registry_values(self) -> None:
        with self.assertRaises(ValueError):
            LocalDeidentifier({" ": "CUSTOMER_NAME"})

        with self.assertRaises(ValueError):
            LocalDeidentifier({"Example Customer": "not a safe category"})


class PrivacyCliTests(unittest.TestCase):
    def test_cli_writes_only_sanitized_text_after_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "excerpt.txt"
            registry_path = root / "identifiers.json"
            output_path = root / "outbound.json"
            input_path.write_text(
                "Example Customer Ltd requires email bid@example.test",
                encoding="utf-8",
            )
            registry_path.write_text(
                json.dumps({"Example Customer Ltd": "CUSTOMER_NAME"}),
                encoding="utf-8",
            )
            arguments = [
                "tender-matic-deidentify",
                "--input",
                str(input_path),
                "--identifiers",
                str(registry_path),
                "--output",
                str(output_path),
            ]
            stdout = io.StringIO()

            with (
                patch("sys.argv", arguments),
                patch("builtins.input", return_value="APPROVE"),
                redirect_stdout(stdout),
            ):
                exit_code = privacy_cli_main()

            written_output = output_path.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertNotIn("Example Customer Ltd", written_output)
            self.assertNotIn("bid@example.test", written_output)
            self.assertNotIn("CUSTOMER_NAME_001\": \"Example Customer Ltd", written_output)
            self.assertEqual(set(json.loads(written_output)), {"text"})

    def test_cli_does_not_write_without_exact_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "excerpt.txt"
            registry_path = root / "identifiers.json"
            output_path = root / "outbound.json"
            input_path.write_text("A synthetic requirement", encoding="utf-8")
            registry_path.write_text("{}", encoding="utf-8")
            arguments = [
                "tender-matic-deidentify",
                "--input",
                str(input_path),
                "--identifiers",
                str(registry_path),
                "--output",
                str(output_path),
            ]

            with (
                patch("sys.argv", arguments),
                patch("builtins.input", return_value="yes"),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                exit_code = privacy_cli_main()

            self.assertEqual(exit_code, 1)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()