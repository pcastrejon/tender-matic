# Prototype Implementation Plan

## Purpose

This plan decomposes the Tender-matic prototype into independently testable phases. It is a plan only; no implementation is described as complete. Each phase has explicit inputs and outputs so it can be developed and tested using fixtures without requiring later phases or live Claude access.

## Prototype Operating Model

- An accompanying BID operator places the new tender in a designated local workspace and starts the run with an ordinary-language prompt.
- A local Python runner sends prompts to the Claude Messages API and owns the tool-use loop. It exposes narrowly scoped tool definitions and executes only allowlisted local operations. MCP is not required for direct API tool use.
- Local tools perform file discovery, parsing, privacy checks, retrieval, output validation, and Markdown writing. Claude must not have unrestricted filesystem or shell access to the source workspace.
- Only minimum necessary de-identified passages may be returned to Claude. Customer names, addresses, and other direct or indirect customer identifiers stay local.
- Historical delivered proposals are the only capability evidence. Unsubstantiated tender requirements are gaps.
- The result is a Markdown draft for in-person BID review. No UI, formal application authentication, corporate Word template, or automatic submission is built for this prototype.

## Phase 0: Runtime and Contracts Spike

**Objective:** Prove the local runner's Claude API tool-use contract and that it can dispatch a constrained local tool without exposing raw files.

**Deliverables:** Python runtime and runner contract; sample prompt; Anthropic tool definition and input/output schemas; designated workspace convention; executable prompt-to-tool demo; fake Claude tool-use response; synthetic local tool that returns non-sensitive results.

**Independent tests:** dispatch a fake Anthropic `tool_use` block; reject unknown tools, arguments, and workspace IDs; reject paths outside the workspace; verify no raw file contents are returned; verify configured customer terms in a prompt are rejected. These exact-term tests do not replace Phase 2 de-identification.

**Exit criteria:** the local demo accepts a prompt and safely handles a simulated API tool call; only allowlisted operations and workspace paths are accessible; tests run without network access or credentials. Run it with `PYTHONPATH=src .venv/bin/python -m tender_matic.phase0 "Inspect workspace demo"`. A live API smoke test is separate and requires an approved model identifier and locally configured API key.

**Gate:** do not add live tender or proposal content until Phase 2 passes and the Claude API data-processing terms are approved.

## Phase 1: Local Document Intake and Parsing

**Objective:** Turn files in an input folder into normalized, traceable text without calling Claude.

**Deliverables:** local CLI; JSON file manifest; normalized document/passages with page, line, paragraph, or table-cell references; explicit parse/OCR/unsupported-format warnings. Initial adapters cover TXT, Markdown, text-layer PDF, and DOCX.

**Independent tests:** synthetic PDF/DOCX/text fixtures; invalid UTF-8, corrupt, encrypted, unsupported, and OCR-required inputs; stable source references; output-directory boundary; no network/model dependency.

**Exit criteria:** supported fixtures parse reproducibly; failures are explicit; all extracted passages map to source locations. Inspect an approved sample corpus before deciding whether to add legacy DOC, OCR, more languages, or additional parsers. Scanned PDFs remain partial and require a later OCR decision.

## Phase 2: De-identification and Outbound Gate

**Objective:** Ensure source content cannot reach Claude before local minimization and customer-identifier checks.

**Deliverables:** direct-identifier detection/redaction, configurable tokenization where useful, indirect-identifier review path, outbound allow/deny decision, and privacy audit metadata.

**Independent tests:** synthetic names, addresses, contacts, IDs, URLs, filenames, metadata, OCR text, and indirect-identifier combinations; ensure uncertain cases fail closed; inspect serialized tool responses and logs for raw identifiers.

**Exit criteria:** known direct-identifier fixtures never appear in outbound payloads; uncertain cases are blocked; identity mappings remain local; an operator can resolve a block without silently bypassing the gate.

## Phase 3: Historical Proposal Corpus and Local RAG

**Objective:** Index approved historical proposals locally and retrieve useful evidence without Claude.

**Deliverables:** corpus ingestion command/tool, local metadata and passage index, hybrid retrieval interface, opaque evidence IDs, and a small reviewed query/evidence set.

**Independent tests:** synthetic proposal corpus and fixed queries; expected evidence in top results; metadata filtering; equal evidentiary treatment; duplicate/reprocessing behavior; ensure customer identity is absent from tool responses after privacy processing.

**Exit criteria:** reviewers can trace retrieved passages to local source locations; retrieval errors and empty results are explicit; no claim of current capability is introduced by search ranking.

## Phase 4: Tender Requirement Analysis with Claude

**Objective:** Extract and structure tender requirements using Claude only after local parsing and privacy approval.

**Deliverables:** prompt/schema for requirement records, local orchestration step, source references, and clear extraction-confidence/warning fields.

**Independent tests:** unit tests with a fake model adapter and fixed responses; schema validation; malformed response handling; privacy-gate integration test; separate opt-in live Claude test using synthetic tender text only.

**Exit criteria:** each requirement has a tender source reference; malformed output is rejected; live requests contain only sanitized fixture content; extraction uncertainty remains visible.

## Phase 5: Evidence Matching, Gaps, Questions, and Risks

**Objective:** Compare requirements with retrieved proposal evidence without inventing capabilities.

**Deliverables:** requirement/evidence matrix; unsupported requirements marked as gaps; ambiguity questions; conflicts and risks with evidence references; structured validation rules.

**Independent tests:** synthetic cases for exact match, partial match, no evidence, ambiguous language, conflicting proposals, and tempting but unsupported inference; fake model responses; assertion that unsupported capability claims fail validation.

**Exit criteria:** no-evidence cases always become gaps; conflicts are surfaced rather than resolved by recency; every supported claim links to proposal evidence.

## Phase 6: Markdown Proposal Draft

**Objective:** Render validated analysis into a readable local Markdown draft.

**Deliverables:** Markdown section structure, local writer, stable source citations, and explicit draft/gap/conflict markers.

**Independent tests:** golden Markdown fixtures; required sections; escaping and formatting; citations resolve locally; no direct or indirect customer identifiers in model output; output is written only under the designated workspace.

**Exit criteria:** BID reviewers can use the draft for management review; missing evidence and unresolved items are conspicuous; no Word template dependency exists.

## Phase 7: Supervised End-to-End Rehearsal

**Objective:** Run the complete workflow on approved, representative material with the BID team present.

**Deliverables:** runbook, test report, known limitations, reviewer feedback, cost/latency observations, and a go/no-go recommendation for the next increment.

**Independent tests:** replay a complete run from fixed input fixtures; verify intermediate artifacts and privacy gates; perform one controlled live Claude rehearsal only after approval; compare output to BID-reviewed reference results.

**Exit criteria:** no customer identifier crosses the outbound boundary; source traceability and gap behavior meet agreed acceptance; the operator can identify incomplete processing; BID approves the prototype for its narrowly scoped demonstration.

## Cross-Phase Contracts

Use versioned, machine-readable artifacts between phases: document manifest, normalized passages, sanitized excerpts, requirement records, evidence records, analysis result, and Markdown output. Each artifact carries opaque IDs and source locations. Tests for a phase consume checked-in synthetic fixtures matching the prior phase's contract, so a phase can be developed and run independently. Do not check real tenders or proposals into the source repository.

## Recommended Build Order

Implement phases 0 through 6 in order, but keep each test suite runnable on its own. Phase 7 is an integration/rehearsal gate, not a prerequisite for unit and contract testing. Do not begin live-data use until the privacy and Claude-provider gates are approved.