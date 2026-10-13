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