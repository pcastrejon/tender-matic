# Phase 7 Rehearsal Runbook

## Current rehearsal status

The local synthetic end-to-end replay is implemented and covered by automated tests. This is not an attended BID rehearsal, a live Claude test, or approval to process customer material. No reviewer feedback, representative-result comparison, live cost/latency measurement, or security/provider approval has been recorded.

**Recommendation:** conditional go for reviewing the synthetic integration; no-go for live Claude processing or customer material until all gates below are documented and approved.

## Preconditions for an attended rehearsal

Before using representative material, the BID lead, security/privacy owner, and provider owner must document approval for the narrowly scoped workflow, chosen Claude model, provider processing and retention terms, local API-key handling, and the specific material. Use only material cleared through company-local procedures. Do not copy source documents, corpus data, identity maps, credentials, or run artifacts into chat or Git.

The current runner has no interactive review interface. The caller must supply attended callbacks that show the original excerpt and sanitized text with local provenance, obtain explicit approval for each outbound excerpt, and obtain explicit human acceptance for every evidence assessment. If such review cannot be performed, do not run the workflow.

No `.env` placeholder or API key is needed for synthetic replay. Add credentials only through an approved company-local secret mechanism after the provider and security gates are satisfied; never commit them.

## Synthetic replay

Use the project environment and synthetic fixtures:

```bash
.venv/bin/python -B -m unittest discover -s tests -p 'test_rehearsal.py' -v
```

The suite exercises successful orchestration and local traceability, a denied privacy review, incomplete extraction, overlapping-directory rejection, and an empty-corpus gap. It uses deterministic model and embedding fakes, does not access the network, and does not need credentials.

## Attended execution procedure

`LocalRehearsal` is currently a Python service, not a CLI. An approved caller must construct it with the local corpus, approved model adapters, `LocalDeidentifier`, and attended review callbacks, then call `run` with separate tender, artifact, and draft roots. Reviewers must be present throughout; the returned draft is not approved for submission.

Keep the tender input, run artifacts, corpus, and draft inside approved company-controlled storage. The runner rejects overlapping tender, artifact, and draft roots and refuses to overwrite the Markdown draft. The `parsed/` artifacts contain extracted source text and local paths; requirement/evidence artifacts and the draft can also contain sensitive local content. Protect and retain them under the same controls as the source material.

On success, inspect `rehearsal-report.json`, the versioned requirement-analysis and evidence-matrix JSON artifacts, the parsed manifest, and the Markdown draft. Verify extraction warnings and incomplete files, requirement source traceability, evidence citations, gaps/conflicts, and reviewer decisions. Record corrections against a BID-prepared reference result, elapsed time, and any approved provider usage/cost measurements outside the source repository.

The report is written only for completed runs. If execution fails after parsing, the `parsed/` directory may remain without a completion report or draft; treat that run as incomplete, retain the artifacts securely for diagnosis, and do not treat partial output as a proposal. The runner currently has no resumable-run or interactive failure-report mechanism.

## Evidence and go/no-go record

For a real rehearsal, attach the approved scope, model and provider decision, security/privacy approval, BID attendees, cleared-material reference (not the material itself), reviewer feedback, comparison against the BID reference, incomplete-processing observations, duration, cost, and decision to proceed or stop. The synthetic replay alone does not satisfy these gates.

Current evidence is limited to automated synthetic tests. Live API behavior, provider cost/latency, representative extraction quality, reviewer feedback, BID acceptance, and production suitability remain unverified.
