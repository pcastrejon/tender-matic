# Solution Design

## Problem

Bid teams have limited time to understand public tenders and prepare high-quality responses. They need to identify requirements, compare them with previously proposed capabilities, expose gaps and ambiguities, and prepare an initial technical proposal with risks.

Tender-matic should reduce this analysis effort while keeping outputs evidence-based and under human control.

## Prototype Goals

- Ingest and search historical delivered proposals using company-controlled storage and indexing.
- Analyze new tender documents and extract requirements with source locations.
- Match requirements to proposal evidence; identify gaps, clarification questions, and risks.
- Produce an initial technical proposal grounded in retrieved evidence.
- Allow the accompanying BID team to start and supervise a run using a natural-language prompt, without building a UI.
- Produce a readable Markdown draft for management review; corporate Word templates are deferred.
- Keep customer-identifying information inside the company while allowing minimum necessary de-identified excerpts to be processed by Claude.

## MVP Scope

**In scope:** historical delivered proposals as the sole capability-evidence source; new tender ingestion; requirement/evidence mapping; gaps, questions, risks, and an initial technical proposal; local parsing, indexing, and de-identification; prompt-triggered supervised execution; Markdown output; independent phase tests.

**Deferred or out of scope:** custom UI and formal application authentication; product specifications and solution design documents; Word templates; treating inferred or newly generated capabilities as established; autonomous approval or tender submission; automatic resolution of conflicting or outdated proposal statements.

## User Workflow

1. An accompanying BID operator places the new tender in the designated local workspace and starts the run with a prompt that contains no customer identifiers.
2. The agent host invokes narrowly scoped local tools. The tools parse documents, report extraction issues, and keep originals in the company workspace.
3. A local privacy gate removes or generalizes customer-identifying information. Uncertain content is blocked for BID review.
4. The system retrieves relevant proposal evidence locally. Only minimum necessary, de-identified excerpts are made available to Claude.
5. Claude returns structured findings. Local validation checks the result and resolves opaque source references.
6. The workflow writes a Markdown draft to the designated output folder. The BID team reviews it in person and handles any customer-specific completion locally.
7. Nothing is approved or submitted automatically.

The prompt is the user-facing trigger, not the execution mechanism. It requires an approved Claude host with local tool access. The local tools enforce the workflow and privacy rules; the model must not have unrestricted access to raw source files.

## Expected Outputs

- Requirement register with source locations.
- Requirement-to-evidence mapping with proposal references and match rationale.
- Gaps for unsupported requirements.
- Clarification questions for ambiguous, incomplete, or conflicting requirements.
- Initial technical proposal draft and major risks, with sources or explicit uncertainty.

## Evidence Rules

- Any eligible historical proposal may be retrieved; no proposal is globally preferred over another.
- Retrieval ranking reflects relevance, not greater authority or truth.
- A proposal establishes that a capability was proposed and internally validated at that time; it does not alone prove current availability or delivery.
- Conflicts are presented for human resolution.
- No evidence means a gap. The system must not extrapolate or combine unrelated claims into a new capability.

Bid team members remain responsible for applicability, current validity, conflict resolution, and approval. The prototype is decision support, not an autonomous bidding authority. It runs in a company-controlled environment under the responsibility of the accompanying operator; omitting formal application authentication does not authorize exposing the workspace or tool server to a network.