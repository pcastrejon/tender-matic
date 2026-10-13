# Privacy and Security Design

## Requirement and Agreed Boundary

Customer-identifying information must not be sent to Claude. This applies to historical proposals and new tenders, and includes direct identifiers and information that could identify a customer in context. Stakeholder clarification permits Claude to process the minimum necessary de-identified excerpts.

Original documents, customer identity, identity mappings, indexes, and local source references remain in company-controlled systems. The exact Claude product, processing region, retention terms, and contractual approval are not yet established.

## Data Classes

- **Restricted local data:** original documents, customer names and addresses, direct and indirect identifiers, identity mappings, and customer-linked metadata.
- **Outbound eligible only after local review:** minimized technical or operational excerpts that pass de-identification.
- **Generated outputs:** returned analysis and drafts, stored under company access controls and checked before display.

Company stakeholders must confirm whether personal data, security-sensitive requirements, or commercially restricted tender terms need stricter handling.

## Local De-identification Gate

Before each Claude request, a company-controlled service should:

1. Minimize input to passages needed for the current analysis step.
2. Detect direct identifiers: names, addresses, contacts, account or tender IDs, URLs, filenames, and document metadata.
3. Detect or flag indirect identifiers: distinctive locations, rare project descriptions, or combinations of dates and attributes.
4. Remove or generalize identifiers, or replace them with consistent opaque tokens when needed for continuity.
5. Keep token-to-identity mappings exclusively local.
6. Validate the sanitized request and block uncertain content for human review.

De-identification is not assumed to be perfect. The policy is fail closed. Uncertain content must not be sent until reviewed or further minimized.

## Outbound and Output Controls

- Send only minimum necessary, de-identified excerpts, not entire documents by default.
- Exclude hidden document properties and raw attachments unless separately reviewed and explicitly approved.
- Treat MCP tool results as outbound content if Claude receives them; MCP does not make data local by itself.
- Log request metadata and local references without copying sensitive raw text into application logs.
- Check Claude responses for direct identifiers or suspicious re-identification before display.
- Resolve citations locally from opaque references. Customer identity is not needed to cite evidence.
- Mark generated material as draft and require human approval before external use.

Before production, confirm provider retention, training use, processing region, access controls, and legal/security terms. This design does not assume specific protections.

## Access and Validation

For the prototype, do not build application authentication. Restrict operation to an accompanying BID operator on a company-controlled machine and workspace protected by existing OS-level access controls. Keep the local tool service bound to the host or otherwise inaccessible from untrusted networks; do not grant Claude general filesystem or shell access. This is a bounded prototype exception, not a production security model. Define application authentication, authorization, encryption, backups, retention, deletion, incident response, and audit requirements before broader deployment.

Test direct and indirect identifiers in prose, tables, headers, footers, filenames, metadata, and OCR output. Include cases where identity could be inferred from rare facts. Verify uncertain content is blocked and raw identifiers do not appear in outbound logs or Claude responses.