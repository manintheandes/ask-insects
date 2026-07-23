# Public Repellent Evidence Comparison Plan

## Goal

Publish reviewed, structured repellent evidence that supports private
compound-to-literature comparisons without receiving private compound data.

## Work

1. Add failing tests for chemical identity, reviewed claim validation, exact
   upstream provenance, privacy, and evidence-package export.
2. Add a machine-readable reviewed repellent evidence catalog and strict loader.
3. Ingest one atomic source record per reviewed public claim.
4. Add the generic `repellent_compound_comparison` context and selectors to the
   existing v3 evidence package.
5. Preserve `payload.evidence`, including exact supporting public provenance.
6. Add source-map, query, and README documentation.
7. Run focused tests and `python3 scripts/verify_complete.py`.
8. Deploy the Ask Insects code revision without rebuilding unrelated sources.
9. Ingest the reviewed public lane on the hosted source plane.
10. Build, validate, commit, and deploy a new immutable evidence-package release.
11. Prove the hosted endpoint serves the exact committed package.

## Acceptance

- No private field or consumer-specific mapping exists in Ask Insects.
- Every exported efficacy claim has an exact public source id and locator.
- Exact compounds, aliases, oils, constituents, mixtures, and products remain
  mechanically distinguishable.
- Missing evidence produces a bounded catalog gap, not a keyword-based claim.
- The private consumer can compare every requested compound locally.
