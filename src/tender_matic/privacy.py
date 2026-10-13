"""Local de-identification and fail-closed outbound gate for phase 2."""

from __future__ import annotations

import ipaddress
import re
from collections import Counter
from dataclasses import dataclass
from typing import Mapping


_SAFE_CATEGORY = re.compile(r"^[A-Z][A-Z0-9_]{1,39}$")
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "EMAIL",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    ),
    (
        "URL",
        re.compile(r"\b(?:https?://|www\.)[^\s<>()]+", re.IGNORECASE),
    ),
    (
        "BUSINESS_IDENTIFIER",
        re.compile(
            r"\b(?:customer|client|account|tax|vat|tender|project|contract)"
            r"\s*(?:id|identifier|number|no\.?|#)\s*[:=#-]?\s*"
            r"[A-Z0-9][A-Z0-9/_-]{2,}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "PHONE",
        re.compile(r"(?<!\w)\+?\d[\d().\s/-]{7,}\d(?!\w)"),
    ),
    (
        "IP_ADDRESS",
        re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)"),
    ),
    (
        "POTENTIAL_LOCATION",
        re.compile(
            r"(?i:\b(?:located\s+in|based\s+in|headquartered\s+in|site\s+in|"
            r"facility\s+in|sede\s+en|ubicado\s+en|instalaci[oó]n\s+en)\s+)"
            r"([A-ZÁÉÍÓÚÜÑ][\wÁÉÍÓÚÜÑ'-]*(?:\s+[A-ZÁÉÍÓÚÜÑ][\wÁÉÍÓÚÜÑ'-]*){0,3})"
        ),
    ),
)


@dataclass(frozen=True)
class RedactionFinding:
    category: str
    token: str
    occurrences: int


@dataclass(frozen=True)
class DeidentificationResult:
    sanitized_text: str
    findings: tuple[RedactionFinding, ...]
    human_review_required: bool = True


@dataclass(frozen=True)
class OutboundExcerpt:
    """The only phase 2 value intended to cross the Claude API boundary."""

    text: str


@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    category: str
    value: str


class PrivacyGateError(PermissionError):
    """Raised when content has not passed the local privacy review gate."""


class LocalDeidentifier:
    """Redact configured customer values and common direct identifier patterns.

    Indirect identification cannot be reliably decided by these rules. Every
    excerpt therefore remains blocked until a human reviews it in context.
    """

    def __init__(self, known_identifiers: Mapping[str, str]) -> None:
        self._known_identifiers: list[tuple[str, str]] = []
        for value, category in known_identifiers.items():
            normalized_value = value.strip()
            normalized_category = category.strip().upper()
            if not normalized_value:
                raise ValueError("Known identifier values must not be empty")
            if not _SAFE_CATEGORY.fullmatch(normalized_category):
                raise ValueError("Identifier categories must be safe uppercase labels")
            self._known_identifiers.append((normalized_value, normalized_category))
        self._known_identifiers.sort(key=lambda item: len(item[0]), reverse=True)
        self._local_mapping: dict[str, str] = {}
        self._token_by_value: dict[tuple[str, str], str] = {}
        self._next_token_by_category: Counter[str] = Counter()

    @property
    def local_mapping(self) -> dict[str, str]:
        """Return a copy of the token map for local use; never include it outbound."""
        return dict(self._local_mapping)

    def sanitize(self, text: str) -> DeidentificationResult:
        if not text.strip():
            raise ValueError("Text to de-identify must not be empty")

        candidates = self._find_candidates(text)
        selected: list[_Candidate] = []
        cursor = 0
        for candidate in sorted(
            candidates,
            key=lambda item: (item.start, -(item.end - item.start), item.category),
        ):
            if candidate.start < cursor:
                continue
            selected.append(candidate)
            cursor = candidate.end

        sanitized_parts: list[str] = []
        occurrence_counts: Counter[tuple[str, str]] = Counter()
        cursor = 0
        for candidate in selected:
            sanitized_parts.append(text[cursor:candidate.start])
            token = self._token_for(candidate.category, candidate.value)
            sanitized_parts.append(token)
            occurrence_counts[(candidate.category, token)] += 1
            cursor = candidate.end
        sanitized_parts.append(text[cursor:])

        findings = tuple(
            RedactionFinding(category, token, occurrences)
            for (category, token), occurrences in sorted(occurrence_counts.items())
        )
        return DeidentificationResult("".join(sanitized_parts), findings)

    def authorize_for_outbound(
        self,
        result: DeidentificationResult,
        *,
        reviewer_confirmed_no_customer_identifiers: bool,
    ) -> OutboundExcerpt:
        if not reviewer_confirmed_no_customer_identifiers:
            raise PrivacyGateError(
                "A human must review the excerpt for direct and indirect customer identifiers"
            )
        if not result.sanitized_text.strip():
            raise PrivacyGateError("Empty excerpts cannot be sent outbound")
        return OutboundExcerpt(text=result.sanitized_text)

    def _find_candidates(self, text: str) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        for value, category in self._known_identifiers:
            pattern = re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)", re.IGNORECASE)
            candidates.extend(
                _Candidate(match.start(), match.end(), category, match.group())
                for match in pattern.finditer(text)
            )

        for category, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(1) if category == "POTENTIAL_LOCATION" else match.group()
                start = match.start(1) if category == "POTENTIAL_LOCATION" else match.start()
                end = match.end(1) if category == "POTENTIAL_LOCATION" else match.end()
                if category == "PHONE" and sum(character.isdigit() for character in value) < 9:
                    continue
                if category == "IP_ADDRESS":
                    try:
                        ipaddress.ip_address(value)
                    except ValueError:
                        continue
                if category == "URL":
                    value = value.rstrip(".,;:!?")
                    end = start + len(value)
                candidates.append(_Candidate(start, end, category, value))
        return candidates

    def _token_for(self, category: str, value: str) -> str:
        normalized_value = " ".join(value.casefold().split())
        mapping_key = (category, normalized_value)
        token = self._token_by_value.get(mapping_key)
        if token is None:
            self._next_token_by_category[category] += 1
            token = f"[{category}_{self._next_token_by_category[category]:03d}]"
            self._token_by_value[mapping_key] = token
            self._local_mapping[token] = value
        return token