# 10,000-Researcher Codex Launch Plan

## Objective

Make Ask Insects, also branded Ask-Zero, ready for 10,000 researchers using
the normal saved Ask Insects Codex project within ten hours.

## Frozen Gates

1. One unchanged production revision passes exactly 50 Reality Eval questions:
   40 public development cases and 10 private sealed holdouts.
2. Every question is the sole prompt in its own fresh user-owned Codex task in
   the saved Ask Insects project.
3. Every complete first answer finishes under 60 seconds. The target median is
   under 10 seconds and the target p95 is under 30 seconds.
4. Independent source review passes every answer for accuracy, relevance,
   completeness, usefulness, privacy, and exact underlying provenance.
5. The same revision passes a separate 1,000-concurrent-request hosted load
   test with fewer than 0.1 percent failed requests, no cross-request answer
   mixing, and verified recovery after overload.
6. Repository, saved project, installed skill, and hosted runtime revisions
   match.
7. The complete passing 50-task run is recorded in the Codex app, reviewed,
   and shared with Josh.

## Corpus

- Keep the public development corpus in the repository.
- Keep sealed holdout questions and truth packets outside the repository.
- Add visible Anopheles development coverage without weakening the existing
  SWD, Aedes, and diamondback moth workflows.
- Every truth packet must cite the exact paper, dataset, or official guidance
  with a readable title, stable public URL, source ID, and atomic locator.
- Do not use internal source maps, program ledgers, generic lanes, OpenAlex
  identifiers alone, or machine-local paths as scientific truth sources.

## Execution

1. Validate and freeze the 40 public questions and 10 private holdouts.
2. Assemble and validate the immutable 50-question contract outside the public
   repository.
3. Align the saved Ask Insects project, installed skill, and production
   runtime to one merged revision.
4. Run an unseen canary in one fresh Codex task and verify raw route metadata,
   model, reasoning effort, complete answer, provenance, and latency.
5. Run the 50 counted tasks serially through the Codex app task API.
6. Preserve every first answer, timing, task ID, raw route trace, and revision.
7. Independently grade immutable answers against the underlying sources.
8. On any failure, preserve the failed run, make a general product repair with
   regression coverage, ship it end to end, and restart from question 1.
9. After 50/50 passes, run the separate load and recovery test.
10. Record all 50 passing tasks in Codex, inspect the recording, and share it.

## Completion Rule

Do not declare this launch goal complete from local tests, a partial run,
selected reruns, a structural validator, a deployment, or a load test alone.
All frozen gates must pass on the same unchanged production revision.
