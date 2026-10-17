# Progress and Handoff Checkpoint

Last verified: 2026-10-14.

## Purpose and Maintenance

Start here when continuing in a new session or handing the repository to another developer. This is a maintained checkpoint, not a transcript. Code and tests are the implementation source of truth; the implementation plan describes intended scope, not completed work.

Repository agent instructions in [../AGENTS.md](../AGENTS.md) require updating this checkpoint after each implemented or materially changed phase, including partial or blocked work. This is an instruction-based workflow for compatible agents, not an enforced scheduler, hook, or CI gate. Other tools and human contributors must follow the same convention explicitly.

## Product Decisions to Preserve

- Supervised prototype operated alongside the BID team: no custom UI, application login, corporate Word templates, or autonomous submission. Markdown is the planned proposal output.
- Claude Messages API is the chosen integration direction. A local Python runner will own tool execution; MCP is not required. Actual API integration has not been implemented.
- Only previously delivered, internally validated proposals may support capability claims. Product specifications and design documents are deferred.
- Proposals have equal evidentiary weight. Relevance ranking is not authority; dates do not confer authority. Unsupported requirements must be gaps; conflicts need human review.
- Source documents, corpus, identity registry, and identity mappings remain company-local. Only minimized, reviewed, de-identified excerpts may reach Claude. Customer names, addresses, and indirect identifiers are prohibited.
- Do not request originals in chat. Representative-document assessment must occur through approved company-local procedures; external assistant tests use synthetic fixtures.

## Phase Status

| Phase | Current state | Remaining qualification |
| --- | --- | --- |
| 0: Runtime/contracts | Synthetic prompt-to-tool demo and boundary tests implemented | No actual Claude API client, API tool loop, or live API smoke test |
| 1: Intake/parsing | Local CLI and normalized artifacts implemented | No OCR or legacy DOC; actual corpus coverage not validated |
| 2: Privacy gate | Local rule-based redactor and attended excerpt-review CLI implemented | Not automatic anonymization; manual review required for every release; no comprehensive audit/review provenance or end-to-end integration |
| 3: Corpus/retrieval | SQLite FTS5 plus local multilingual embeddings, CLI, citations, model safeguards, and metadata filters implemented | Prototype-scale vector scan; lifecycle, context chunking, relevance calibration, and real-data evaluation remain open |
| 4: Claude requirement analysis | Review-gated service, Messages API adapter, response validation, and synthetic tests implemented | No interactive review CLI or integrated workflow; live provider configuration and approval remain unverified |
| 5: Matching/gaps/questions/risks | Not started | Depends on structured requirements and retrieval/privacy integration |
| 6: Markdown proposal draft | Not started | Depends on validated analysis |
| 7: Supervised rehearsal | Not started | Requires integration, approved provider configuration, and BID/security review |

The components are independently testable but are not yet an integrated prompt-to-proposal workflow.

## Component Contracts and Reading Order

1. [prototype-implementation-plan.md](prototype-implementation-plan.md): phase goals and exit criteria.
2. [design-decisions.md](design-decisions.md): accepted constraints and open decisions.
3. [../src/tender_matic/phase0.py](../src/tender_matic/phase0.py): synthetic tool definitions, allowlist, path boundary checks, and demo. It never reads a real corpus or calls Claude.
4. [../src/tender_matic/ingestion.py](../src/tender_matic/ingestion.py) and [../src/tender_matic/ingest.py](../src/tender_matic/ingest.py): intake and CLI. `manifest.json` has schema version 1; normalized document JSON carries document ID, relative path, format, extraction status, passages, and warnings. Passages contain ID, text, and source location.
5. [../src/tender_matic/privacy.py](../src/tender_matic/privacy.py) and [../src/tender_matic/privacy_cli.py](../src/tender_matic/privacy_cli.py): `LocalDeidentifier.sanitize` returns sanitized text/findings requiring review; `authorize_for_outbound` requires reviewer confirmation. The CLI writes only `{"text": ...}` after exact `APPROVE`. The token map exists locally in memory and is not exported.
6. [../src/tender_matic/corpus.py](../src/tender_matic/corpus.py) and [../src/tender_matic/corpus_cli.py](../src/tender_matic/corpus_cli.py): index fully parsed normalized proposals. `EvidenceMatch` has an opaque evidence ID, raw local text, and retrieval score; `resolve_citation` separately returns local source path/location/date/language. CLI search prints both raw passages and local citations: it is not a model-safe tool response.
7. [../src/tender_matic/analysis.py](../src/tender_matic/analysis.py): `RequirementAnalyzer` accepts caller-selected tender excerpts, requires an explicit human reviewer callback for each exact excerpt, sends only approved text with opaque source IDs, and keeps locations in a local source-reference mapping. `ClaudeMessagesAdapter` calls the Messages API; returned JSON, confidence values, and source IDs are validated, and detected direct identifiers block the result.
8. [testing-strategy.md](testing-strategy.md), [privacy-and-security.md](privacy-and-security.md), and tests under [../tests/test_phase0.py](../tests/test_phase0.py), [../tests/test_ingestion.py](../tests/test_ingestion.py), [../tests/test_privacy.py](../tests/test_privacy.py), [../tests/test_corpus.py](../tests/test_corpus.py), [../tests/test_analysis.py](../tests/test_analysis.py), and [../tests/test_live_analysis.py](../tests/test_live_analysis.py).

## Setup and Commands

Create a fresh environment when cloning; `.venv`, the embedding model cache, and company-local datasets are not transferred by Git.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[retrieval,test]'
.venv/bin/python -m tender_matic.phase0 "Inspect workspace demo"
.venv/bin/python -m tender_matic.ingest --input /company-local/tender/input --output /company-local/tender/parsed
.venv/bin/tender-matic-deidentify --input /company-local/excerpt.txt --identifiers /company-local/identifiers.json --output /company-local/reviewed.json
.venv/bin/tender-matic-corpus index --documents /company-local/proposals/parsed/documents --database /company-local/corpus.sqlite3
.venv/bin/tender-matic-corpus search --database /company-local/corpus.sqlite3 --query "user authentication" --limit 5
```

The identifier registry maps local sensitive values to category labels, for example `{"Synthetic Customer":"CUSTOMER_NAME"}`. Real values stay company-local. Optional corpus metadata is keyed by normalized document ID with `language` and ISO `proposal_date`; see [ingestion-and-retrieval.md](ingestion-and-retrieval.md).

Phase 4 callers must select the minimum necessary excerpts locally, provide an attended review callback, and map ingestion warnings into local analysis warnings. For an explicitly approved synthetic live test only, set `ANTHROPIC_API_KEY` and `TENDER_MATIC_CLAUDE_MODEL` locally and opt in with `TENDER_MATIC_RUN_LIVE_CLAUDE_TEST=1`; never use customer tender text in this test.

## Verification Evidence

Fresh verification on 2026-10-14:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover -s tests -q
```

Result: 45 tests passed in 1.108 seconds (12 phase 0, 11 ingestion, 10 privacy, 12 corpus). No live Claude calls or real company documents were used. Re-run rather than assuming the count remains current after future changes.

Phase 4 verification on 2026-10-14:

```bash
/home/pablo/tender-matic/.venv/bin/python -B -m unittest discover -s tests -p 'test_analysis.py' -v
/home/pablo/tender-matic/.venv/bin/python -B -m unittest discover -s tests -v
git diff --check
```

Results: focused phase 4 suite passed (13 tests); full suite passed (59 tests, 1 opt-in live test skipped); `git diff --check` reported no whitespace errors. Editor diagnostics reported no errors in the changed Python files. The live Claude test was not run, no live API request was made, and no real tender material was used.

Earlier phase 3 verification on 2026-10-13: `pip check` reported no broken requirements; the real local fastembed adapter produced finite 384-dimensional vectors and ranked a synthetic authentication passage above payments for a login query. Model weights were downloaded to this machine's cache; that cache is not repository content. Those earlier checks were not repeated when writing this checkpoint.

Local retrieval uses `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` via optional `fastembed`. Its installed model description reports 128 input tokens: long phase 1 passages need an explicit chunking/truncation strategy before claiming full semantic coverage. Unit tests use a deterministic fake embedder and do not measure model relevance quality.

## Known Limitations and Risks

- Privacy rules cover configured values and selected patterns, not all names, addresses, languages, OCR errors, or indirect clues. Review is a caller-supplied boolean/CLI confirmation, not an authenticated or immutable approval. Future callers must not bypass it or confuse a plain JSON text file with verifiable privacy approval.
- Phase 2 currently reviews standalone UTF-8 excerpts; it is not yet wired to phase 1 JSON passage selection or corpus retrieval. Phase 4 needs local provenance mapping and explicit review of the exact outgoing text.
- Phase 4 is a Python service contract, not an interactive CLI or integrated runner. Callers must deliberately select/minimize tender excerpts, implement an attended callback that shows original and sanitized text with local provenance, and pass through all relevant extraction warnings. Configured-pattern output checks are not complete re-identification detection.
- The Claude adapter and synthetic live-test harness are implemented, but provider terms, approved model selection, local API-key setup, and a live request have not been verified. No real content may be used before those approvals.
- The normalized corpus has paths and unredacted text. SQLite, logs, CLI output, and local data files must not be sent wholesale to Claude or committed. File exclusion rules are not a complete data-loss prevention system.
- Re-indexing an identical document ID skips it; this is not full revision replacement, deletion, or metadata-update support. Approval of delivered proposals is an operator responsibility, not inferred from extraction status `parsed`.
- Vector retrieval currently ranks available candidates without a calibrated relevance cutoff. A returned neighbor is not proof of support or compliance; irrelevant/no-support cases still need evidence assessment. Relevance/conflict handling is not phase 5 implementation.
- Raw SQL metadata-filter construction and the CLI error paths require integration coverage beyond existing tests; unit success is not an end-to-end guarantee. Improve touched paths when extending them, rather than treating the current baseline as production-certified.
- No approved representative corpus, reviewer-labeled real query set, security sign-off, API configuration, or live-provider validation has been recorded.

## Next Task: Phase 5

After user authorization, implement evidence matching, gaps, clarification questions, and risks as a separately testable phase using synthetic proposals and requirements. Preserve equal evidentiary treatment, mark unsupported requirements as gaps, and surface conflicts rather than resolving them by recency. Phase 4 does not itself authorize a live Claude test or the use of real tender content.

## Checkpoint History

- 2026-10-14: Established this handoff checkpoint after phases 0-3; re-ran 45 tests successfully. Added persistent repository instructions to update progress after subsequent phase work and corrected stale MCP guidance in the documentation index.
- 2026-10-14: Implemented Phase 4 review-gated requirement analysis, local source mapping, Claude Messages API adapter, strict structured-response checks, and an opt-in synthetic-only live test. Focused suite passed (13 tests); full suite passed (59 tests, 1 live test skipped). No live API request or real document use.