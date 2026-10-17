# Repository Agent Instructions

## Session Continuity

Before implementing a phase, read [spec/progress.md](spec/progress.md) and the relevant section of [spec/prototype-implementation-plan.md](spec/prototype-implementation-plan.md). Verify the current code and working tree; the checkpoint is a handoff aid, not a substitute for implementation evidence.

After implementing or materially changing a phase, update `spec/progress.md` before the final response, without waiting for a separate user request. Update the checkpoint date, phase status, affected contracts and files, exact validation commands and observed results, known limitations, blockers, and the next concrete task. If interrupted or blocked, record partial status rather than claiming completion. Never claim that tests, live API calls, or security reviews passed unless actually verified. Keep this as one maintained checkpoint rather than creating a progress file for each session.

Record new design decisions in [spec/design-decisions.md](spec/design-decisions.md) and reconcile any directly conflicting design documentation. Keep repository documentation in English. Do not start the next phase without user authorization merely to update progress.

## Required Boundaries

Preserve the evidence and privacy rules in [spec/privacy-and-security.md](spec/privacy-and-security.md) and [spec/solution-design.md](spec/solution-design.md). Do not read real customer material through an external assistant or commit source proposals, tenders, corpus databases, identifier registries, identity mappings, or secrets. Use synthetic test fixtures. Customer identifiers must not reach Claude; rule-based redaction still requires attended human review.

## Validation

Use Python 3.12 or newer and the project environment. Install with `python -m pip install -e '.[retrieval,test]'`. Run the narrow tests for the touched phase first, then the relevant integration/regression tests. The full local suite is `python -m unittest discover -s tests -v`; it uses fake embeddings and needs no credentials or model download. Live embedding/model tests are separate and must be reported separately.