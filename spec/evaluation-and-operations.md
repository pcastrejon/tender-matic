# Evaluation and Operations

## Quality Principles

The system must reduce analysis effort without hiding uncertainty or creating unsupported capability claims. Evaluate extraction, retrieval, privacy, generated analysis, and the human workflow.

## Evaluation Set

Before a pilot, select representative historical tenders and proposals. Experienced Bid reviewers should validate reference requirements and source locations, relevant evidence, known gaps, ambiguous requirements, known proposal conflicts, and direct/indirect customer identifiers. Use approved evaluation documents and apply production privacy controls.

## Suggested Measures

- Requirement coverage and source-location accuracy.
- Evidence precision: whether cited passages actually support mapped requirements.
- Unsupported capability claims in approved outputs (target: zero).
- Recall of known gaps and known evidence conflicts.
- Customer identifiers in outbound test requests (target: zero).
- Extraction completeness for supported formats, tables, and OCR cases.
- Reviewer time saved and correction effort compared with the existing workflow.

Agree targets with Bid, security, and product stakeholders. Aggregate scores must not conceal severe failures such as a privacy leak or unsupported approved claim.

## Human Review Gates

- Review low-confidence extraction before relying on analysis.
- Review privacy-gate exceptions before any content is sent to Claude.
- Review gaps, conflicts, assumptions, risks, and generated proposal content.
- Require explicit approval before exporting final content or submitting it externally.

For the prototype, these gates are performed by the accompanying BID team rather than through a product UI. The operator confirms the selected local workspace before starting and reviews the Markdown draft before sharing it with management.

## Monitoring

Track ingestion and parsing status, retrieval outcomes, privacy blocks, Claude failures, output validation failures, and user corrections. Use opaque local identifiers in logs and avoid retaining raw sensitive text unnecessarily. Monitor latency and cost by workflow stage. Clearly identify incomplete processing; never silently present partial analysis as complete.

## Pilot Readiness

Do not begin a live pilot until the Claude processing configuration is approved; de-identification tests block direct and indirect identifiers; parser limitations are visible; citations resolve to local sources; gap/conflict behavior is validated; access, retention, incident, and deletion responsibilities are documented; and Bid reviewers understand that generated output requires approval.