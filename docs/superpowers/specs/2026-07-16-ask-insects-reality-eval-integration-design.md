# Ask Insects Reality Eval Integration

Date: 2026-07-16
Status: approved for implementation

## Objective

Make `/realityeval` the single authoritative completion gate for the current
Ask Insects goal. Completion must be based on the experience Josh and a
scientist actually have in Codex, not on direct database probes, local-only
tests, canned answers, or questions about the system itself.

The final proof is one 50-question black-box evaluation through the normal
Codex route. All 50 first-attempt answers must pass, every complete answer must
arrive in less than 60 seconds, and the complete run must be recorded and
shared with Josh.

This design supersedes the production-evaluation sections of the July 13
dual-product design and the July 15 broad-language plan where they require a
minimum 200-question completion run or a separate 20-question scientist demo.
The existing 210-case corpus remains useful regression coverage, but it is not
the completion gate.

## Goal Contract

The Ask Insects goal is incomplete until one final evaluation proves all of
the following on the same deployed revision:

1. Exactly 50 natural-language questions are asked through the normal Codex
   experience and installed Ask Insects route.
2. At least 40 questions ask about insect science, R&D, product translation,
   or a scientifically important source gap rather than Ask Insects itself.
3. Exactly 10 questions are sealed holdouts that were not used to develop,
   repair, rehearse, or tune the evaluated revision.
4. Every answer shown to the user is complete on the first attempt and arrives
   in strictly less than 60 seconds.
5. Every applicable factual claim is accurate, relevant, useful, and supported
   by exact public-source provenance.
6. Direct evidence, inference, disagreement, uncertainty, and source gaps are
   kept distinct.
7. No private Ask Monarch data enters the public Ask Insects answer path,
   artifacts, or recording.
8. All 50 questions and complete answers are recorded in the real Codex app.
9. The recording is reviewed for completeness and privacy, then shared with
   Josh.

The threshold is 50 of 50. A retry, average, percentile, partial rerun, or
direct-source check cannot turn a failed final run into a pass.

## Alternatives Considered

### Selected: 40 public cases and 10 private sealed holdouts

Forty committed cases provide repeatable development coverage. Ten private
cases preserve a meaningful final test. The final result combines both sets
into one 50-question artifact and one recording.

### Rejected: publish all 50 cases

This is simpler, but the ten holdouts would no longer be unseen and could not
test whether the system handles questions it was not tuned to answer.

### Rejected: require both the old 200-case gate and the new 50-case gate

This preserves more volume but creates two competing definitions of done and
contradicts the decision to use one realistic 50-question evaluation. The old
corpus can continue to run as non-gating regression coverage.

## Evaluation Corpus

The committed development corpus contains exactly 40 questions. The private
holdout bundle contains exactly 10. Together they cover at least six scientific
categories and include both active product programs plus the next insect:

- SWD sensory biology, brain, behavior, reproduction, and egg laying
- SWD ecology, crop context, assay interpretation, and repellent translation
- `Aedes aegypti` sensory biology, brain, host seeking, feeding, and behavior
- mosquito repellency, human-use protection, assay interpretation, and safety
- diamondback moth and carefully labeled cross-species inference
- uncertainty, conflicting evidence, false premises, and meaningful source
  gaps

Question wording must sound like a scientist asking Codex for help. At least
80 percent of the corpus must be domain questions. System-coverage, routing,
and evaluator questions cannot dominate the set.

The corpus may include comparison questions only when the comparison would
help R&D or commercialization. It must not contain case-specific trigger
phrases, hidden commands, expected-answer hints, or canned response routes.

## Sealed Holdout Custody

The ten holdout questions and their truth packets live outside the public Git
repository at:

`~/.local/share/ask-insects/realityeval/ask-insects-holdouts-v1.json`

The repository stores only a receipt containing the holdout count, schema
version, SHA-256 fingerprint, and creation time. The holdout file is excluded
from commits, public artifacts, logs, and recordings until each question is
asked during the final run.

The evaluated Ask Insects route receives only the natural-language question.
It never receives the truth packet or expected answer. Grading happens after
the visible answer has been captured.

If any final-run case fails, all ten holdouts from that run are considered
exposed. The failed artifact and recording are preserved, the underlying
general problem is repaired, and ten new holdouts are created before another
counted run. Failed questions must not be converted into special-case answer
rules.

## Independent Truth Packets

Ask Insects cannot be its own scientific judge. Every case has a frozen truth
packet prepared from original public sources such as papers, datasets,
official guidance, or an explicit verified source-gap search.

Each packet contains:

- the exact question
- the scientific category and focal species or product
- required claims or expected source-gap behavior
- forbidden overclaims or known false premises
- acceptable uncertainty and inference boundaries
- original source identifiers and exact locators
- a short explanation of what makes the answer useful to the scientist

Truth packets are evaluation evidence, not text that the product should copy.
They are versioned and fingerprinted before the counted run.

## Production Route

Every final question uses a fresh normal Codex task and the installed Ask
Insects skill:

`natural question -> Codex -> installed Ask Insects skill -> hosted public source plane -> complete visible answer`

The final run freezes and records:

- repository commit
- installed skill fingerprint
- hosted deployment or source-plane revision
- public corpus fingerprint
- sealed holdout receipt fingerprint
- evaluator version
- start and finish time

No repository edits, source refreshes, skill refreshes, deployment changes, or
answer retries are allowed between the first and fiftieth question.

## Grading

The evaluator has two independent layers.

### Mechanical checks

These checks prove that the correct production route was used and that the
answer is eligible for scientific review:

- exact question preserved
- one first-attempt answer
- complete answer visible
- elapsed time strictly below 60 seconds
- hosted Ask Insects route used
- no local index, web-search substitute, unsupported model-memory fallback, or
  Ask Monarch route
- exact source identifiers and locators preserved
- no private data or secrets disclosed
- full artifact fields and recording metadata present

### Scientific checks

The captured answer is graded against the frozen truth packet for:

- factual accuracy
- source support
- focal species, life stage, sex, assay, and context correctness when relevant
- correct handling of uncertainty, inference, disagreement, and missing data
- relevance to the actual question
- completeness without unsupported overclaiming
- usefulness to R&D or commercialization

Every dimension must pass. Keyword presence alone is insufficient evidence of
scientific correctness.

## Artifacts And Recording

Each run writes an immutable artifact containing all 50 cases, complete visible
answers, elapsed times, provenance, grader evidence, verdicts, revision
fingerprints, and failure reasons. Failed full runs are retained.

The passing run is recorded in the real Codex app. The recording must visibly
show all 50 exact questions and all 50 complete answers, not a summary such as
"Ask Insects found." It may scroll through the preserved real Codex task
transcripts when needed to make long answers legible, but it may not recreate,
replace, shorten, or rewrite the answers.

Before sharing, the recording is checked for:

- all 50 question-and-answer pairs
- readable complete answers and provenance
- no skipped, clipped, substituted, or duplicate cases
- no private Ask Monarch data, credentials, or unrelated private material
- consistency with the passing machine-readable artifact

## Failure And Repair Loop

A failing final run is diagnostic evidence, not a near-pass. For each failure:

1. Preserve the answer, timing, route trace, grader evidence, and recording.
2. Classify the general cause: source gap, retrieval, routing, answer synthesis,
   provenance, scientific overclaim, latency, privacy, or evaluator defect.
3. Repair the general system or source mapping without adding a case-specific
   answer.
4. Add or update focused tests that prove the general repair.
5. Run local tests and the public 40-case development set.
6. Merge, deploy, refresh the installed skill when relevant, and verify the live
   revision.
7. Replace all exposed holdouts and restart a new 50-question final run.

This loop continues until one unchanged live revision passes 50 of 50.

## Repository Integration

Implementation updates these ownership points so they agree:

- `AGENTS.md` and `README.md`: state the Reality Eval goal in plain language.
- the dual-product design and active evaluation plan: mark the old 200-plus-20
  gate as superseded.
- `docs/production-path-evaluation.md`: document the 50-question workflow,
  holdout custody, grading, repair loop, and recording requirement.
- a new public 40-case manifest and holdout receipt: define the corpus boundary.
- the production evaluator: enforce exactly 50 cases, ten sealed holdouts,
  strict timing, source/provenance checks, scientific grading, revision freeze,
  and recording metadata.
- `scripts/verify_complete.py`: verify the new contract and reject stale or
  contradictory completion criteria.
- focused tests: prove corpus counts, category balance, sealed-holdout handling,
  strict timing, grading, recording fields, and failure behavior.

The unfinished 20-question scientist-demo implementation and any case-specific
answer code are removed. General runtime improvements from that spike may be
kept only when they are independently justified and tested.

## Compatibility And Public Boundary

The hosted source plane remains the only answer surface. Existing source lanes,
record identifiers, CLI behavior, and the public Ask Insects to private Ask
Monarch boundary remain intact.

This integration changes how completion is proved. It does not itself claim
that any repellent works, move Monarch evidence into Ask Insects, or make the
50 evaluation questions part of normal answer routing.

## Acceptance Criteria

The integration is complete only when:

- all repository goal and evaluation documents name the same 50-question gate
- no authoritative document still presents 200-plus-20 as the completion rule
- the committed corpus has 40 valid public development cases
- a private ten-case holdout bundle matches its public receipt
- the evaluator and tests enforce every goal-contract requirement
- case-specific scientist-answer code has been removed
- focused tests and `python3 scripts/verify_complete.py` pass
- changes are merged, the relevant hosted/runtime surfaces are deployed, and
  the installed skill is refreshed when required
- one unchanged production revision passes 50 of 50 with every complete answer
  under 60 seconds
- the full Codex-app recording is reviewed and shared with Josh

Passing unit tests or the public 40-case set alone does not complete the goal.

## Non-Goals

- publishing the sealed holdout questions before the final run
- importing private Monarch evidence into Ask Insects
- adding canned responses for evaluation cases
- treating source presence as proof that a scientific answer is correct
- requiring the old 210-case corpus as a second completion gate
- declaring a product effective or commercially ready from this evaluation
