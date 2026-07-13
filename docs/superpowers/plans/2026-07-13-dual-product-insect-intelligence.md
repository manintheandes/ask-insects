# Dual-Product Insect Intelligence Plan

Date: 2026-07-13
Branch: `codex/dual-product-insect-intelligence`

## Acceptance Criteria

- Ask Insects has one validated program ledger for the SWD crop repellent, the
  human mosquito repellent, and diamondback moth expansion.
- Every species uses the same fourteen biological knowledge domains.
- Every product uses the same eight readiness dimensions.
- Evidence status, directness, verification, uncertainty, disagreement, and
  gaps are explicit.
- The ledger becomes queryable through records with exact JSON locators.
- A generic answer path handles Aedes, SWD, and diamondback moth program and
  coverage questions.
- Adding a fourth insect requires ledger data and sources, not another block of
  species-specific routing code.
- Existing Aedes and SWD answers do not regress.
- Local tests, the full suite, and `scripts/verify_complete.py` pass.
- The hosted source plane ingests the records and passes live questions.
- A minimum 200-question black-box evaluation runs through Josh's normal Codex
  route, achieves 100 percent expected behavior, includes complete provenance,
  and returns every full visible answer in under 30 seconds.

## Work Sequence

1. Add failing tests for ledger validation, record generation, explicit gaps,
   generic species aliases, planner routing, and natural-language answers.
2. Add `config/insect-intelligence-programs.json` with the two products and
   three initial insect profiles.
3. Implement a generic ledger loader, validator, record builder, and ingest
   script.
4. Add generic species and product selection to the planner and answer layer.
5. Wire local CLI ingestion and the hosted HTTP ingest route.
6. Add the source map, repository documentation, and completion-gate checks.
7. Run focused tests, the full test suite, and completion verification.
8. Deploy, ingest the ledger on the hosted plane, and verify representative
   Aedes, SWD, diamondback moth, and product-readiness questions.
9. Build the 200-plus question production-path corpus and runner. Capture exact
   questions, expected route and behavior, visible answers, provenance, elapsed
   time, and failure reasons. Fix every failure until one clean run passes 100
   percent with every answer under 30 seconds.
10. Design and implement the private Ask Monarch context bridge.
11. Run a blinded historical-experiment evaluation against the current Ask
    Monarch baseline.

## First Hosted Questions

- What are the two product programs Ask Insects is supporting?
- What does Ask Insects need to understand about spotted wing drosophila?
- What is missing from diamondback moth biology coverage?
- What is the product readiness status of the human mosquito repellent?
- Which evidence about Aedes is direct, inferred, or still unverified?

## Release Rule

Do not deploy if the new path invents species evidence, hides a gap, treats a
planning status as efficacy proof, changes existing Aedes or SWD coverage
behavior, or cannot show exact ledger provenance.

Do not declare the major goal complete until the 200-plus question black-box
production-path evaluation has one clean 100-percent run and every visible
answer is under 30 seconds with complete provenance.
