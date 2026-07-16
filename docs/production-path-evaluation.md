# Reality Eval

Reality Eval is the authoritative Ask Insects completion gate. It asks exactly 50
natural questions through the same normal Codex route Josh uses:

`question -> Codex -> installed Ask Insects skill -> hosted public source plane -> complete visible answer`

The contract contains 40 public development cases and 10 sealed holdouts. The
holdout questions and truth packets remain outside Git. Only their exact-byte
receipt is public.

## Passing Rule

Every question must use a fresh task in the real Codex app. Only the complete
first answer counts. Each answer must:

- arrive in strictly under 60 seconds
- use the hosted Ask Insects route and no sibling answer system
- preserve the exact natural-language question
- answer the research question directly and completely
- state uncertainty, inference, disagreement, and source gaps honestly
- include every required public source ID and exact locator
- pass independent review for accuracy, sources, relevance, completeness,
  usefulness, privacy, and provenance
- avoid private Monarch data, unsupported model memory, and substitute routes

The pass threshold is 50 of 50. Any failure ends the counted run. After a
general source, routing, answer, or latency repair, an independent evaluator
must create new holdouts and the entire run starts again.

The passing run must keep the repository commit, installed skill hash, hosted
revision, public corpus hash, holdout receipt hash, and evaluator version
unchanged. Its start and finish times, fresh task IDs, raw traces, complete
answers, timings, independent claim checks, and exact provenance are preserved
in the result artifact.

## Public Corpus

The public development corpus is:

```text
evals/ask_insects_reality_eval_public_v1.json
```

It contains realistic SWD crop-repellent, Aedes human-repellent, and
diamondback-moth expansion questions. Validate it with:

```bash
python3 scripts/eval_reality.py validate-public
```

The 40 public cases are used to find and repair general failures. Passing them
does not satisfy the final gate.

## Sealed Holdouts

The private bundle normally lives at:

```text
~/.local/share/ask-insects/realityeval/ask-insects-holdouts-v1.json
```

Freeze the non-secret receipt without printing or committing holdout content:

```bash
python3 scripts/eval_reality.py freeze-holdouts \
  --holdouts "$HOME/.local/share/ask-insects/realityeval/ask-insects-holdouts-v1.json" \
  --receipt evals/ask_insects_reality_eval_holdout_receipt_v1.json
```

The receipt contains only version, target, creation time, count, and SHA-256.
Assembly rejects any one-byte change to the private bundle after freezing.

## Final Contract And Results

Assemble the private contract outside Git:

```bash
python3 scripts/eval_reality.py assemble \
  --public evals/ask_insects_reality_eval_public_v1.json \
  --holdouts "$HOME/.local/share/ask-insects/realityeval/ask-insects-holdouts-v1.json" \
  --receipt evals/ask_insects_reality_eval_holdout_receipt_v1.json \
  --output artifacts/reality-evals/final/contract.json
```

After the real Codex app run and independent source review:

```bash
python3 scripts/eval_reality.py validate-results \
  --contract artifacts/reality-evals/final/contract.json \
  --results artifacts/reality-evals/final/results.json
python3 scripts/eval_reality.py summary \
  --contract artifacts/reality-evals/final/contract.json \
  --results artifacts/reality-evals/final/results.json
```

The recording must show all 50 complete questions and answers with provenance,
pass privacy review, be reviewed in full, and be shared with Josh.

## Repository Checks

`python3 scripts/verify_complete.py` validates the public corpus, receipt
schema, CLI, source boundaries, authoritative documentation, and repository
tests. Repository verification does not substitute for the private passing
artifact and recording.

The legacy 210-case evaluator in `scripts/eval_production_path.py` remains
optional regression coverage. Smoke subsets, regrading, direct CLI calls, SQL,
unit tests, and that legacy suite cannot satisfy Reality Eval.
