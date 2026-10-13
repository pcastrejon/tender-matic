# Design Decisions

This log records current decisions and unresolved choices. Implementation details remain open where the environment or stakeholders have not provided enough information.

## Accepted Decisions

### D-001: Historical proposals are the only capability evidence in the MVP

**Status:** Accepted. **Decision:** Use previously delivered proposals that were internally validated as the sole capability-evidence source. Defer product specifications and solution-design documents. **Rationale:** Current scope and the rule against claiming capabilities not previously proposed. **Consequence:** Evidence proves a capability was proposed and validated at that time, not necessarily that it is available today or was delivered.

### D-002: Historical proposals have equal evidentiary weight

**Status:** Accepted. **Decision:** Do not globally prefer proposals by recency or other metadata. Retrieval ranks relevance, not authority. **Rationale:** Stakeholder clarification. **Consequence:** Surface conflicts for human resolution; users assess applicability and current validity.

### D-003: Unsupported requirements are gaps

**Status:** Accepted. **Decision:** Without proposal evidence, mark a requirement as a gap; do not infer or invent capabilities. **Rationale:** Explicit stakeholder instruction and need for defensible content. **Consequence:** Distinguish gaps from questions, assumptions, and potential work requiring validation.

### D-004: Only minimized, de-identified excerpts may be sent to Claude

**Status:** Accepted, subject to provider approval. **Decision:** Claude may process the minimum necessary tender and proposal excerpts, but no customer name, address, or other direct or indirect customer-identifying information. **Rationale:** Stakeholder permits necessary Claude processing while prohibiting customer identifiers. **Consequence:** De-identify locally for both source types; keep identity mappings local; block uncertain cases for review; confirm provider terms before production.

### D-005: RAG is required; the local runner executes Claude API tool use

**Status:** Accepted for the prototype. **Decision:** Use local RAG for historical proposals and a local Python runner that calls the Claude Messages API. The runner validates API `tool_use` requests and executes only allowlisted local operations. MCP is not required. **Rationale:** The prototype will use the Claude API; API tool use lets the application retain control of local tool execution. A prompt alone cannot access local files. **Consequence:** Tool results visible to Claude must pass the privacy gate. A live API smoke test needs an approved model identifier and locally configured API key.

### D-006: Use an orchestrated, human-reviewed workflow

**Status:** Proposed baseline. **Decision:** Use explicit workflow stages, output validation, and human approval rather than autonomous multi-agent execution. **Rationale:** Evidence and privacy constraints require control and traceability; multi-agent complexity has no demonstrated MVP benefit. **Consequence:** Build review controls; do not autonomously approve or submit tender responses.

### D-007: No custom UI or formal application authentication for the prototype

**Status:** Accepted for the accompanied prototype only. **Decision:** BID staff run and review the workflow on a company-controlled machine and designated workspace. Rely on existing OS-level access controls; do not build a UI or application login. **Rationale:** The prototype is operated in person and needs to validate the workflow before productizing it. **Consequence:** Do not expose local tools on an untrusted network or grant unrestricted file/shell access. This is not an acceptable production security model.

### D-008: Markdown is the prototype output format

**Status:** Accepted. **Decision:** Generate a local Markdown proposal draft; defer corporate Word templates. **Rationale:** It is sufficient to demonstrate the analysis to management with less formatting complexity. **Consequence:** The draft is not a final corporate deliverable and remains subject to BID review.

## Open Decisions

### O-001: Claude product, hosting, and contractual configuration

Confirm retention, model-training use, processing region, access controls, and legal/security terms before selection.

### O-002: De-identification method and review threshold

Define detection methods, confidence thresholds, reviewers, and handling of rare details that could identify customers indirectly.

### O-003: Corpus permissions and governance

Define who can ingest, search, and view proposals; versioning, correction, retention, and deletion procedures.

### O-004: Supported formats and languages

Inventory the tender/proposal corpus to determine parsing, OCR, table, and language requirements.

### O-005: Output templates and exports

Confirm formats for the compliance matrix, clarification questions, risk summary, and technical proposal.

### O-006: Capability currency and conflict resolution

Define who determines whether historical capabilities remain applicable and how contradictions are resolved. Until then, report evidence and uncertainty without deciding.

### O-007: Concrete stack and operating targets

Choose libraries, hosting, performance targets, and budgets after environment, corpus, and security constraints are known.

### O-008: Claude model identifier and API configuration

Choose the model identifier and confirm API account, network, retention, and data-processing settings. Configure the API key locally as a secret; never place it in source control or send it in chat. The phase 0 contract tests do not require a key.