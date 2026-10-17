# Prototype Testing Strategy

## Principles

- Every implementation phase must have a testable contract and a local test path that does not require later phases.
- Default tests use synthetic documents, fake Claude responses, and deterministic fixtures.
- Live Claude calls are opt-in integration tests, use synthetic content by default, and run only after provider approval.
- Never commit real customer tenders, proposals, identity mappings, or sensitive evaluation data to the repository.
- Privacy and evidence failures are release blockers, not averageable quality defects.

## Test Layers

### Unit tests

Test parsing helpers, identifier detection, token replacement, schema validation, retrieval ranking, citation formatting, and Markdown rendering in isolation.

### Contract tests

Validate versioned artifacts between phases, tool request/response schemas, path/workspace restrictions, and failure states. If MCP is selected, validate tool schemas and ensure tools expose only the intended operations.

### Integration tests with fakes

Connect local parsing, privacy, retrieval, orchestration, and output components while replacing Claude with a deterministic fake model adapter. Assert control flow, provenance, and fail-closed behavior.

### Live model tests

Use a small approved set of synthetic tender passages to validate Claude connectivity, structured output handling, and cost/latency. Do not use real client-identifying data. Keep expected assertions focused on schema and evidence constraints rather than exact wording.

### End-to-end rehearsal

Run the full workflow with the accompanying BID team on approved material only after privacy and provider gates are met. Compare with a reviewer-prepared reference and record corrections, timing, and incomplete extraction.

The local synthetic orchestration replay is covered by `python -B -m unittest discover -s tests -p 'test_rehearsal.py' -v`. It verifies intermediate artifacts and privacy gates without network access; it does not replace attended review or live-provider approval. See [phase-7-rehearsal.md](phase-7-rehearsal.md) for the current status and gated procedure.

## Required Test Scenarios

- Supported, unsupported, empty, corrupt, encrypted, and OCR-dependent files.
- Customer identifiers in body text, tables, headers, footers, filenames, metadata, and OCR output.
- Indirect identifiers that are uncertain and must therefore be blocked for review.
- Attempts to access paths outside the designated workspace.
- Model/tool failure, timeout, malformed structured output, and retry without duplicate side effects.
- Relevant evidence, no evidence, partial support, contradictory proposals, and stale context.
- Assertions that retrieval relevance does not elevate a proposal's authority.
- Markdown output with gaps, conflicts, questions, risks, and local citations.
- Checks that raw source text and identifiers are not included in outbound payloads or logs.

## Phase Exit Evidence

Each phase should produce: test command or repeatable test procedure; fixture set; pass/fail report; known limitations; and confirmation that no real sensitive files entered the repository. The end-to-end pilot additionally requires BID reviewer sign-off and security approval for any live Claude processing.