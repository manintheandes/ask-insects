# Ask Insects Repellency Evidence Workflow Plan

Date: 2026-07-10
Branch: `codex/repellency-evidence-workflow`

## Acceptance Criteria

- Comparative repellency questions use a dedicated answer path.
- The answer implements `repellency-comparison.v1` and exposes claim,
  comparison, coverage, evidence, and source-gap fields.
- Unsupported literature-wide superlatives are blocked with concrete reasons.
- Comparison rows preserve normalized assay dimensions and provenance.
- Coverage deduplicates papers and reports paper-depth outcomes and source gaps.
- Repellency paper-depth profiles produce `repellency_assay` candidate facts.
- Literature-depth ingests are reachable locally and through the hosted server,
  and write status plus receipts.
- Concurrent hosted ingests cannot overwrite each other's completed source state.
- Writable staging artifacts are independent from live artifacts.
- Deterministic evaluations, focused tests, the full test suite, and
  `scripts/verify_complete.py` pass.

## Work Sequence

1. Add the evaluation corpus and failing contract, routing, comparison, and
   claim-policy tests.
2. Implement `askinsects/repellency.py` with question detection, paper
   deduplication, normalized comparison rows, coverage reporting, and claim
   evaluation.
3. Add a dedicated repellency assay fact family to the relevant paper-depth
   profiles.
4. Route comparative questions through `answer_question` and update CLI text
   rendering for structured answers.
5. Integrate the literature-depth profiles into CLI and hosted ingestion with
   source-grade status and receipts.
6. Serialize hosted mutations and replace writable hardlink staging with an
   independent copy strategy.
7. Add all new production files and tests to the completion gate.
8. Run focused tests, all tests, static checks, package/build checks, completion
   verification, and hosted-facing acceptance probes.

## Evaluation Questions

The first corpus must cover:

- an unqualified "nothing beats it" claim
- a spatial versus topical mismatch
- contact versus non-contact mismatch
- a comparison missing target dose and duration
- a pairwise DEET versus picaridin question
- an SWD repellency question
- a metadata-discovery question that must not use the comparison workflow
- a source-coverage question with unresolved discovery gaps

## Release Rule

Do not ship if any evaluation emits an unqualified superlative, omits evidence
coverage, loses provenance, or treats metadata-only records as comparison-ready.
