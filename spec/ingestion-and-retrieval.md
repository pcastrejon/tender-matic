# Ingestion and Retrieval Design

## MVP Sources

1. **Historical delivered proposals:** the only approved source of solution-capability evidence.
2. **New tender documents:** the source of requirements, evaluation criteria, deadlines, and tender context.

Product specifications, solution designs, and other capability repositories are deferred. Newly generated drafts do not become evidence automatically.

## Historical Proposal Ingestion

1. For the prototype, an operator places approved proposal files in the designated local corpus folder. A later production workflow can add managed uploads and permissions.
2. Originals are retained in company-controlled storage and assigned stable internal identifiers.
3. Text, headings, tables, and page or section locations are extracted locally.
4. Available metadata (such as date, language, document type, and status) is recorded. Customer identity may remain locally available to authorized users but is excluded from outbound Claude context.
5. Parsed passages are indexed locally for lexical and semantic retrieval.
6. Extraction and indexing status is visible; failures can be corrected and reprocessed.

Every passage must map back to its original document and location. Versioning, duplicate handling, permissions, and corpus refresh procedures must be specified before production.

## New Tender Ingestion

1. The operator places the tender files in the designated local input folder and starts the workflow with a prompt. The prompt uses an opaque workspace name and contains no customer identifiers.
2. Originals and parsed text remain in company-controlled storage.
3. Local parsing identifies document structure and candidate requirements, preserving page, section, table, or attachment references.
4. Unsupported formats, extraction failures, and low-confidence sections are reported.
5. The accompanying BID team reviews requirement candidates and extraction warnings. Incomplete extraction must not be presented as complete analysis.

The local tool service, rather than the prompt text, performs file access, parsing, and privacy enforcement. Claude must not receive raw file contents through unrestricted filesystem tools.

## Retrieval and Matching

- Split content into passages that preserve section context and source locations.
- Use local hybrid retrieval: lexical search for exact terms and semantic search for equivalent wording.
- Apply access controls and source filters before returning passages.
- Retrieve evidence per requirement where practical; do not send the whole corpus by default.
- Keep proposals equally valid as evidence. Relevance scores do not confer authority or current validity.
- Retrieve enough context to avoid misleading excerpts, but minimize what is sent to Claude.
- Surface conflicting claims explicitly.

Each evidence record should include stable local document and passage IDs, source type, location, proposal date where available, matched requirement, retrieval score, and de-identification status. IDs sent to Claude must be opaque and must not encode customer identity. Token-to-identity mappings stay local.

## Data Quality and Lifecycle

Detect empty, corrupted, encrypted, or unsupported files; disclose OCR use and low-confidence extraction; preserve table relationships and requirement numbering where possible; and allow correction or exclusion. Support reprocessing and superseding an indexed version while preserving an audit trail. Retention and deletion policies remain open decisions.

## Phase 1 Implementation

The current local intake implementation supports `.txt`, `.md`, text-layer `.pdf`, and `.docx`. It extracts line references for text/Markdown, page references for PDFs, and paragraph/table-cell/header/footer references for DOCX. Each file receives a status (`parsed`, `partial`, `unsupported`, or `failed`) and structured warnings. OCR, legacy `.doc`, language detection, and semantic retrieval are not implemented in this phase.

Install the project and optional test fixture dependency, then run ingestion with separate input and output directories:

```bash
python -m pip install -e '.[test]'
python -m tender_matic.ingest --input /path/to/tender/input --output /path/to/tender/parsed
```

The output directory contains `manifest.json` and `documents/<opaque-document-id>.json`. It must not overlap the source input directory. Ingestion performs no Claude/API or network calls. Artifacts contain parsed source text and relative file paths; keep them inside the company environment and do not send them to Claude before Phase 2 de-identification is implemented and approved.

Run the isolated suite with:

```bash
python -m unittest discover -s tests -v
```

## Phase 3 Local Proposal Corpus

Index only fully parsed proposal artifacts; partial artifacts are rejected as capability evidence. Install local semantic-retrieval support and build the SQLite corpus:

```bash
python -m pip install -e '.[retrieval,test]'
python -m tender_matic.corpus_cli index --documents /path/to/proposals/parsed/documents --database /path/to/local/proposal-corpus.sqlite3 --metadata /path/to/local/proposal-metadata.json
python -m tender_matic.corpus_cli search --database /path/to/local/proposal-corpus.sqlite3 --query "user login and identity management" --limit 5 --language en --proposal-date-from 2020-01-01
```

The optional metadata file is a local JSON map keyed by each phase 1 normalized document's `document_id`; accepted fields are an ISO `proposal_date` and a `language` code. For example: `{"documents":{"<document-id>":{"proposal_date":"2024-02-20","language":"en"}}}`. Do not add customer names or other identifiers to this sidecar. Metadata filters restrict which documents are candidates but never increase a proposal's rank or evidentiary authority.

The index combines SQLite FTS5 lexical search with local `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` vectors using reciprocal-rank fusion. The model weights (about 0.22 GB) are downloaded to the local cache on first use; proposal text and query text are embedded and searched locally, not sent to an embedding API. The SQLite file contains proposal passage text and local paths, so it must remain company-controlled and must not be committed.

Search results include opaque evidence IDs, passage text, and scores. Source path, page/section, date, and language are resolved in a separate local citation lookup; do not pass raw result text to Claude. The phase 2 privacy review must approve any excerpt before it can cross that boundary. Proposal dates are citation context only and do not increase evidence rank. An approved real proposal corpus and reviewer-labeled relevance queries are still needed to assess retrieval quality; synthetic tests do not establish production recall or precision.

## Phase 4 Tender Requirement Analysis

`RequirementAnalyzer` accepts only caller-selected tender excerpts. The local caller is responsible for minimizing the tender content and passing extraction warnings; each excerpt is de-identified and shown alongside its original text and local provenance to an attended reviewer. The analyzer blocks the model request unless every reviewer callback explicitly approves. Claude receives only opaque source IDs and approved text; file paths, document IDs, passage IDs, and page/section locations stay in the local source-reference map.

The Messages API adapter requires a configured model identifier and `ANTHROPIC_API_KEY` in the local environment. Model output must be strict JSON: each requirement has non-empty text, one or more known source IDs, a confidence from 0 to 1, and explicit warning strings. Invalid JSON, unknown or missing source references, incomplete API responses, and detected direct identifiers in returned text are rejected. Ingestion warnings are carried alongside the result; an empty extraction is explicitly warned rather than treated as complete.

Run the isolated tests with `python -m unittest discover -s tests -p 'test_analysis.py' -v`. A live API check is separate and opt-in: set `TENDER_MATIC_RUN_LIVE_CLAUDE_TEST=1`, configure `TENDER_MATIC_CLAUDE_MODEL` and `ANTHROPIC_API_KEY` locally, and run `python -m unittest discover -s tests -p 'test_live_analysis.py' -v`. The live test contains only a synthetic requirement. Neither the synthetic gate nor configured-pattern checks establish privacy approval for real tender material.

## Phase 5 Evidence Matching

`EvidenceMatcher` consumes structured phase 4 requirements plus per-requirement `EvidenceMatch` candidates and their locally resolved `LocalCitation` records. Both tender requirement text and every candidate proposal excerpt are de-identified and presented with local provenance for attended review before the matching model is called. Only opaque requirement/evidence IDs and reviewed text are sent to the model; proposal paths, locations, dates, retrieval scores, and tender source mappings stay local. A separate required reviewer callback sees each model assessment beside its raw candidate passages and local citations; a rejected assessment is not returned as an accepted matrix.

The returned evidence matrix has one validated assessment per requirement (`supported`, `partial`, `gap`, or `conflict`), with rationale, evidence IDs, clarification questions, and evidence-linked risks. IDs must refer to candidates retrieved for that exact requirement. Supported/partial assessments need evidence citations; conflicts need citations from at least two distinct proposal files and a clarification question. A requirement with no retrieved candidates must be a gap. Warnings from requirement extraction and model analysis are retained. Historical dates and retrieval scores are deliberately excluded from model context and never determine evidentiary weight.

This phase is a model-adapter contract with synthetic fake-response tests; it does not itself configure or call Claude and therefore needs no API key or `.env` entry. It does not establish that a retrieved passage semantically supports a claim; the model assessment remains fallible and human review is required. Run `python -m unittest discover -s tests -p 'test_matching.py' -v` for the focused tests.