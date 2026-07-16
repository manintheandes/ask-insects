# Broad Natural-Language Production Readiness Plan

Date: 2026-07-15
Branch: `codex/ask-insects-router-60s`

Gate status: the corpus-size rule in the original plan is superseded by Reality
Eval. The legacy 210-case suite remains optional regression coverage.

## Objective

Make the hosted `ask-insects ask` route reliable for the ordinary questions
Josh types in Codex. A passing source index or direct SQL result is not enough.
The complete visible answer must use the intended public evidence, preserve
exact provenance, fail closed when evidence is absent, and arrive in under 60
seconds without retries or route substitution.

## Confirmed Failures

1. "What public evidence does Ask Insects have for non-contact repellency in
   spotted wing drosophila?" fell through to species identity because the
   planner recognized `repellent` but not the ordinary noun `repellency` in the
   broad behavior route.
2. "What genome assembly does Ask Insects have for Aedes aegypti?" timed out
   after the answer layer fell back to a full-text search for the common phrase
   `Aedes aegypti` across the million-row index. An indexed source-and-lane
   lookup returned the assembly in under one second.
3. The legacy deterministic corpus is dominated by program
   ledger questions. It does not prove that broad R&D questions use the right
   lane or finish on time.
4. `--compact` only emits `final_answer` for two answer shapes, although the
   installed Codex route expects a ready-to-display `final_answer` for every
   successful question.

## Acceptance Criteria

- Broad SWD wording for non-contact, spatial, odor-mediated, and oviposition
  repellency routes to calibrated SWD behavior evidence, never taxonomy.
- Cross-species records that entered an SWD discovery corpus are not promoted
  as direct SWD evidence.
- Aedes reference-genome and assembly questions use the indexed
  `ncbi_datasets_genome` source directly and do not invoke broad species FTS.
- Every `ask-insects ask --json --compact` response has `final_answer`, exact
  source IDs, and exact locators, including source-gap responses.
- No Ask Monarch source, private experiment, compound, video, result, or
  decision can appear on the public answer path.
- The authoritative gate asks exactly 50 natural questions through normal
  Codex: 40 public development cases and 10 sealed holdouts. Each first,
  complete answer uses a fresh task in the real Codex app and arrives in
  strictly under 60 seconds.
- Independent review passes accuracy, sources, relevance, completeness,
  usefulness, privacy, and exact provenance for every answer.
- Live grading does not preflight, retry, rephrase, or substitute SQL/search for
  the normal hosted `ask` route. Direct source queries are allowed only after
  the visible answer, as independent grading evidence.
- Targeted tests, the full suite, and `python3 scripts/verify_complete.py` pass.
- The fix is merged, deployed, installed locally, and verified against the live
  hosted plane.
- One unchanged 50-question run reports 100 percent expected behavior,
  complete provenance, no private-data leakage, and every response under 60
  seconds. The complete recording is reviewed and shared with Josh.

## Work Sequence

1. Add failing planner, answer, compact-payload, evaluator, and privacy tests
   for the confirmed failures and the 60-second contract.
2. Expand the broad vocabulary and add source-scoped fast paths for focal
   queries whose canonical sources are known.
3. Add a direct-species filter for SWD repellency candidates and calibrated
   wording that distinguishes candidate extraction from verified efficacy.
4. Make the compact response contract uniform across every answer shape and
   source gap.
5. Build and independently source-grade 40 public natural-language questions,
   then have a separate evaluator create 10 private holdouts.
6. Run focused tests, then the full repository completion gate.
7. Deploy the hosted application and refresh the installed CLI and skill.
8. Run live smoke cases for the original failures plus representative source
   gaps and privacy-boundary questions.
9. Run exactly 50 questions in fresh normal Codex tasks without retries. Save
   the exact questions, complete visible answers, commands, timings,
   provenance, independent grades, and real Codex app recording.
10. Fix every general failure, replace the holdouts, and repeat the full run
    until one fresh run passes every case. Prior failed runs remain preserved.

## Release Rule

Do not ship or complete the goal if direct SQL is the only fast path, if a
generic question can still fall into taxonomy, if an SWD answer silently uses
another species, if compact output lacks provenance, if any private Monarch
data appears, or if a production-path case reaches 60 seconds.
The legacy 210-case runner may support optional regression work, but it cannot
complete the goal.
