# Tender-matic Design Documentation

These documents describe the proposed design, based on the source specification and stakeholder clarifications. For verified implementation status and limitations, start with [Progress and Handoff](progress.md); design documents alone do not establish completion.

## Documents

- [Progress and Handoff](progress.md): verified phase status, contracts, setup, limitations, and next task.
- [Solution Design](solution-design.md): goals, scope, workflow, and expected outputs.
- [Architecture](architecture.md): components, trust boundaries, and architecture diagram.
- [Ingestion and Retrieval](ingestion-and-retrieval.md): source handling, indexing, and evidence retrieval.
- [Privacy and Security](privacy-and-security.md): customer de-identification and Claude controls.
- [Technology Options](technology-options.md): recommended technology categories and selection criteria.
- [Design Decisions](design-decisions.md): accepted decisions, rationale, trade-offs, and open decisions.
- [Evaluation and Operations](evaluation-and-operations.md): quality gates and operational expectations.
- [Prototype Implementation Plan](prototype-implementation-plan.md): phased build sequence, deliverables, and exit criteria.
- [Testing Strategy](testing-strategy.md): independent phase tests, fixtures, and acceptance gates.

## Design Baseline

- Previously delivered proposals are the MVP's only source of solution-capability evidence. Product specifications and solution-design documents are deferred.
- All proposals have equal evidentiary weight. Retrieval relevance is not authority; conflicts are surfaced for human review.
- Claude is required and may process the minimum necessary excerpts after local de-identification.
- Customer names, addresses, and any other direct or indirect customer identifiers must not be sent to Claude. This applies to tenders and historical proposals.
- Requirements without supporting proposal evidence are gaps, not opportunities to infer capabilities.
- RAG is part of the design. The selected direction is a local Python runner calling Claude Messages API and dispatching allowlisted local tools; MCP is optional and not required.
- The prototype is operated by the BID team with no custom UI or formal application authentication.
- A natural-language prompt is the intended workflow trigger through the local runner; the current phase 0 demo is simulated and the integrated API workflow is not implemented yet.
- The prototype produces a Markdown draft; corporate Word templates are deferred.

The original [tender-matic.md](tender-matic.md) is retained as the source specification. These documents record subsequent clarifications. Its statement that all company know-how must remain local needs reconciliation with the clarified permission to send de-identified excerpts to Claude. The proposed boundary keeps source documents, customer identity, indexes, and identity mappings inside the company, while allowing narrowly scoped de-identified content to be processed by Claude.

Specific providers, libraries, deployment topology, retention terms, and security approvals remain undecided.

The current prototype scope supersedes earlier references to a guided internal UI and formal in-product review workflow. Review is performed by the accompanying BID team. A prompt alone cannot access local files: the local runner must control tool execution and privacy checks. See the [implementation plan](prototype-implementation-plan.md) and [Design Decisions](design-decisions.md) for the Claude API direction and remaining configuration decisions.