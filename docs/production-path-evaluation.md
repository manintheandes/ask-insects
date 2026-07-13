# Production-Path Evaluation

The release gate asks questions the same way Josh does:

`question -> Codex -> installed Ask Insects skill -> hosted source plane -> visible answer`

It does not count a direct CLI, SQL query, unit test, or hidden source check as a
passing answer.

## Full Gate

```bash
python3 scripts/eval_production_path.py
```

The committed corpus is
`evals/ask_insects_production_path_v1.json`. It contains 200 explicit questions
covering species biology, both product programs, portfolio expansion,
repellency comparisons, uncertainty, false premises, source gaps, and the
public/private boundary.

A full run passes only at 100 percent, when all 200 questions pass in one run. Every question
must:

- use the installed Ask Insects skill and the hosted `ask-insects ask --compact` path
- preserve Josh's exact question in the hosted call
- finish the complete visible Codex answer in under 30 seconds
- match the expected subject and evidence behavior
- show the expected source ID and exact row or locator in the final answer
- avoid local-index, memory, web, Ask Monarch, setup, refresh, and test fallbacks
- avoid unsupported efficacy, readiness, and best-in-literature claims

Scientific/common species names and configured domain or product aliases count
as the same expected term. Punctuation and status formatting do not matter, so
`partial_source_grade` and `partial source grade` are equivalent. Source IDs
and locators remain exact, and a negated warning such as "not ready for market"
is not misgraded as a readiness claim.

The compact agent payload removes duplicated internal rows and long evidence
text only after the hosted answer is complete. Its ready-to-use `final_answer`
retains the deterministic conclusion, claim reasons and coverage counts, plus
the source ID and exact locator for every returned evidence row. The installed
skill returns that value verbatim.

The runner writes the exact question, expected behavior, visible answer,
commands, elapsed time, provenance, pass/fail decision, and failure reasons to
`artifacts/production-path-evals/<timestamp>/results.json`.

## Smoke Run

Use a non-gating subset while fixing a failure:

```bash
python3 scripts/eval_production_path.py \
  --smoke \
  --case-id portfolio-products-01
```

A smoke run can show that selected cases pass. It can never satisfy the full
production gate. Retries do not erase a failed full run.

## Other Checks

`python3 scripts/verify_complete.py` validates the corpus, evaluator, source
contracts, and repository tests. It deliberately does not replace the live
200-question run. The major Ask Insects goal remains incomplete until a saved
full result reports `production_gate_passed: true`.
