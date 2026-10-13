# Technology Options and Selection Criteria

## Selection Status

This is a technology direction, not a finalized bill of materials. Claude is mandatory. Specific products, libraries, versions, deployment targets, and providers require security, procurement, and environment review.

## Provisional Direction

| Concern | Direction | Rationale and selection criteria |
| --- | --- | --- |
| Language model | Claude through an approved integration | Required. Must support controlled requests and structured outputs under acceptable privacy and retention terms. |
| Workflow | Local workflow service with explicit stages, invoked by an agent host | Keeps deterministic steps and privacy policy local while supporting a natural-language prompt trigger. |
| Parsing and OCR | Company-controlled parsing and OCR when needed | Keeps raw files and identities internal; supports inspection of extraction quality and required languages/formats. |
| Source storage | Existing company-controlled storage where feasible | Reuses access controls and avoids needless duplication; must support stable references, backup, and retention. |
| Search and RAG | Local hybrid search over passages and metadata | Combines exact keyword and semantic retrieval. Keep indexes and embeddings company-controlled initially. |
| Embeddings | Prefer locally generated embeddings for the MVP | Avoids sending full source passages to a separate embedding service; validate language quality and hardware cost. |
| Privacy layer | Local de-identification and fail-closed outbound gate | Enforces the customer-identifier restriction before Claude calls. |
| User interaction | Prompt to a local Python runner that calls the Claude Messages API | BID staff accompany and review runs; no custom UI is needed. |
| Tool execution | Anthropic API tool-use loop executed by the local runner | Claude requests a tool; the runner validates and executes only allowlisted local operations, then returns privacy-checked results. MCP is unnecessary for this direct API flow. |
| Output | Locally written Markdown draft | Human-readable for management without implementing corporate Word templates. |

## Claude Integration Requirements

The integration should receive only minimized, de-identified excerpts; return structured requirements, evidence matches, gaps, questions, risks, and draft sections; preserve opaque source IDs; support bounded context; and be evaluated for quality, latency, cost, and failure handling. Provider processing terms must be approved before production.

Do not claim that provider processing is local or that particular retention protections apply until verified technically and contractually.

## Workflow Strategy

Use explicit stages: local parsing; local privacy validation; requirement extraction; local evidence retrieval; bounded Claude analysis through the Messages API; output validation and local citation resolution; Markdown writing; human review. The runner owns the tool-use loop and must not authorize free-form access to raw files. Separate prompts may handle analysis subtasks, but each stage needs explicit inputs and validated outputs. Separate autonomous agents are not justified for the MVP.

## Selection Gates

Choose concrete technologies after confirming the approved Claude access method and terms, company hosting and identity environment, corpus size/formats/languages/OCR needs, permissions, user load, latency and budget, privacy review, and required exports. No framework or vector database is prescribed until these constraints are known.