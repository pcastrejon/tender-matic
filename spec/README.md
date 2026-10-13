# Tender-matic Design Documentation

These documents describe the initial proposed design, based on the source specification and stakeholder clarifications. They do not describe an implemented system.

## Documents

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
- RAG is part of the design. A local MCP server is the preferred prompt-to-tools bridge when supported by the selected Claude host; a constrained local runner is the fallback.
- The prototype is operated by the BID team with no custom UI or formal application authentication.
- A natural-language prompt starts the workflow through an agent host with access to narrowly scoped local tools.
- The prototype produces a Markdown draft; corporate Word templates are deferred.

The original [tender-matic.md](tender-matic.md) is retained as the source specification. These documents record subsequent clarifications. Its statement that all company know-how must remain local needs reconciliation with the clarified permission to send de-identified excerpts to Claude. The proposed boundary keeps source documents, customer identity, indexes, and identity mappings inside the company, while allowing narrowly scoped de-identified content to be processed by Claude.

Specific providers, libraries, deployment topology, retention terms, and security approvals remain undecided.

The current prototype scope supersedes earlier references to a guided internal UI and formal in-product review workflow. Review is performed by the accompanying BID team. A prompt alone cannot access local files: the selected Claude host must have an approved route to local tools. See the [implementation plan](prototype-implementation-plan.md) for the recommended MCP-based prototype and the remaining runtime decision.