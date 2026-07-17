# Ask Insects Reality Eval Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Ask Insects' conflicting 200-question gate and 20-question demo with one authoritative, source-validated, recorded 50-question Reality Eval that uses 40 public development cases and 10 private sealed holdouts.

**Architecture:** Keep evaluation code outside the normal answer path. A small repository module validates public questions, private holdouts, receipts, frozen contracts, and final results; a thin CLI assembles and checks artifacts. The normal Codex app drives the hosted Ask Insects route, while independent truth packets grade captured first-attempt answers after each task completes.

**Tech Stack:** Python 3.11 standard library, JSON manifests, SQLite-backed Ask Insects CLI, `unittest`, the installed `/realityeval` validator, Codex desktop task APIs, and `/codexdemo` for the final recording.

---

## File Map

- Create `askinsects/reality_eval.py`: repository-owned schemas, validation,
  hashing, contract assembly, result validation, and summary calculations.
- Create `scripts/eval_reality.py`: CLI for validating the public corpus,
  freezing a holdout receipt, assembling the private final contract, validating
  results, and printing a release summary.
- Create `tests/test_reality_eval.py`: focused tests for counts, categories,
  holdout custody, contract hashing, strict timing, route evidence, grading,
  recording, and summaries.
- Create `evals/ask_insects_reality_eval_public_v1.json`: exactly 40 public,
  natural scientist questions with independently checked truth packets.
- Create `evals/ask_insects_reality_eval_holdout_receipt_v1.json`: only the
  count, schema version, creation time, and SHA-256 of the private ten-case
  bundle.
- Create outside Git
  `~/.local/share/ask-insects/realityeval/ask-insects-holdouts-v1.json`: ten
  sealed questions and truth packets.
- Create outside Git under a timestamped path such as
  `artifacts/reality-evals/20260716T120000Z/`: the assembled
  private 50-question contract, raw transcripts, immutable results, grading
  evidence, recording, and contact sheet.
- Modify `AGENTS.md`, `README.md`,
  `docs/production-path-evaluation.md`, the July 13 design, and the July 15
  plan: make the 50-question gate authoritative and mark 210 cases as optional
  regression coverage.
- Modify `scripts/verify_complete.py`: verify the new repository contract and
  reject stale 200-plus-20 completion language.
- Modify `askinsects/answer.py`, `askinsects/index.py`, and
  `tests/test_index.py`: remove the canned scientist-answer spike while keeping
  the general bounded-search protection only if its focused tests pass.
- Delete the uncommitted 20-case spike:
  `askinsects/scientist_rnd.py`,
  `scripts/eval_scientist_rnd_demo.py`,
  `evals/ask_insects_scientist_rnd_demo_v1.json`,
  `tests/test_scientist_rnd_answers.py`,
  `tests/test_scientist_rnd_eval.py`, and
  `docs/superpowers/plans/2026-07-16-scientist-rd-evaluation.md`.

## Task 1: Remove The Canned 20-Question Spike

**Files:**
- Modify: `askinsects/answer.py`
- Modify: `README.md`
- Modify: `docs/production-path-evaluation.md`
- Modify: `scripts/verify_complete.py`
- Delete: `askinsects/scientist_rnd.py`
- Delete: `scripts/eval_scientist_rnd_demo.py`
- Delete: `evals/ask_insects_scientist_rnd_demo_v1.json`
- Delete: `tests/test_scientist_rnd_answers.py`
- Delete: `tests/test_scientist_rnd_eval.py`
- Delete: `docs/superpowers/plans/2026-07-16-scientist-rd-evaluation.md`

- [ ] **Step 1: Write the failing no-canned-route test**

Add this test to `tests/test_answer.py`:

```python
def test_normal_answer_path_does_not_import_an_evaluation_answer_module(self):
    source = (Path(__file__).parents[1] / "askinsects" / "answer.py").read_text(
        encoding="utf-8"
    )
    self.assertNotIn("scientist_rnd", source)
    self.assertNotIn("build_scientist_rnd_answer", source)
```

- [ ] **Step 2: Run the test and confirm the spike fails it**

Run:

```bash
python3 -m pytest tests/test_answer.py -k evaluation_answer_module -q
```

Expected: failure because `askinsects/answer.py` imports and calls
`build_scientist_rnd_answer`.

- [ ] **Step 3: Remove the case-specific route and spike files**

Remove the import and early return from `askinsects/answer.py`. Delete the six
untracked code, corpus, test, and plan files listed above. Remove their
references from `README.md`, `docs/production-path-evaluation.md`, and the
required-file and test-module lists in `scripts/verify_complete.py`.

- [ ] **Step 4: Prove the normal answer path is clean**

Run:

```bash
python3 -m pytest tests/test_answer.py -k evaluation_answer_module -q
```

Expected: pass.

- [ ] **Step 5: Commit the removal**

```bash
git add README.md askinsects/answer.py docs/production-path-evaluation.md scripts/verify_complete.py tests/test_answer.py
git add -u askinsects scripts evals tests docs/superpowers/plans
git commit -m "refactor: remove canned scientist eval route"
```

## Task 2: Keep Only The General Search-Time Bound

**Files:**
- Modify: `askinsects/index.py`
- Modify: `askinsects/answer.py`
- Modify: `tests/test_index.py`
- Modify: `tests/test_answer.py`

- [ ] **Step 1: Keep the existing failing closed index test**

Retain `IndexTests.test_search_fails_closed_when_the_fts_budget_expires` from
the current worktree. It must patch `SEARCH_TIMEOUT_SECONDS` to zero and assert
both an empty result and `last_search_timed_out is True`.

- [ ] **Step 2: Add an answer-level timeout regression test**

Use a temporary initialized index and patch `SourceIndex.search` to set
`last_search_timed_out` before returning no records:

```python
def test_bounded_full_text_timeout_returns_an_explicit_source_gap(self):
    def timed_out_search(index, query, lane=None, limit=10):
        index.last_search_timed_out = True
        return []

    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir) / "mosquito-v1"
        index = SourceIndex(artifact_dir / "source_index.sqlite")
        index.initialize()
        with patch.object(SourceIndex, "search", timed_out_search):
            answer = answer_question(
                "How does an unfamiliar volatile alter mosquito orientation?",
                artifact_dir=artifact_dir,
            )
    self.assertFalse(answer["ok"])
    self.assertIn("search budget", answer["source_gap"]["reason"].casefold())
```

- [ ] **Step 3: Run the focused tests**

Run:

```bash
python3 -m pytest tests/test_index.py -k fts_budget tests/test_answer.py -k bounded_full_text_timeout -q
```

Expected: the index test passes with the current worktree change; the
answer-level test initially fails until the timeout is propagated correctly.

- [ ] **Step 4: Finish the smallest general implementation**

Keep these public behaviors:

```python
SEARCH_TIMEOUT_SECONDS = 8.0
SEARCH_PROGRESS_STEPS = 1_000
```

`SourceIndex.search()` resets `last_search_timed_out`, installs a SQLite
progress handler, converts only interrupted/expired searches to an empty result,
and always clears the handler. `answer_question()` returns an explicit source
gap only when the fallback timed out before any evidence record was found.

- [ ] **Step 5: Run the complete index and answer suites**

Run:

```bash
python3 -m pytest tests/test_index.py tests/test_answer.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit the general protection**

```bash
git add askinsects/index.py askinsects/answer.py tests/test_index.py tests/test_answer.py
git commit -m "fix: bound full text fallback searches"
```

## Task 3: Add The Repository-Owned Reality Eval Contract

**Files:**
- Create: `askinsects/reality_eval.py`
- Create: `tests/test_reality_eval.py`

- [ ] **Step 1: Write contract validation tests**

Create helpers that build 40 public and 10 holdout cases. Add tests asserting:

```python
def test_public_manifest_requires_exactly_40_non_holdout_domain_questions(self):
    manifest = public_manifest()
    self.assertEqual(len(validate_public_manifest(manifest)["questions"]), 40)

    manifest["questions"].pop()
    with self.assertRaisesRegex(RealityEvalError, "exactly 40"):
        validate_public_manifest(manifest)


def test_final_contract_requires_exactly_50_cases_and_ten_holdouts(self):
    contract = assemble_contract(public_manifest(), holdout_bundle())
    validated = validate_contract(contract)
    self.assertEqual(len(validated["questions"]), 50)
    self.assertEqual(sum(case["holdout"] for case in validated["questions"]), 10)
    self.assertGreaterEqual(
        sum(case["kind"] == "domain" for case in validated["questions"]),
        40,
    )
```

Each test case includes this complete truth-packet shape:

```python
"truth_packet": {
    "required_claims": ["The answer must state the measured observation."],
    "forbidden_claims": ["The observation proves commercial efficacy."],
    "reasoning_boundaries": ["Separate observation from mechanism."],
    "sources": [
        {
            "source_id": "public-source",
            "locator": "records#public-source:1",
            "public_url": "https://example.org/source",
            "supports": "The measured observation."
        }
    ]
}
```

- [ ] **Step 2: Run the tests and confirm the module is missing**

Run:

```bash
python3 -m pytest tests/test_reality_eval.py -q
```

Expected: import failure for `askinsects.reality_eval`.

- [ ] **Step 3: Implement the schema module**

Define these constants and the two basic helpers in
`askinsects/reality_eval.py`:

```python
PUBLIC_MANIFEST_VERSION = "ask-insects-reality-public.v1"
HOLDOUT_BUNDLE_VERSION = "ask-insects-reality-holdouts.v1"
HOLDOUT_RECEIPT_VERSION = "ask-insects-reality-holdout-receipt.v1"
CONTRACT_VERSION = "realityeval.v1"
RESULTS_VERSION = "realityeval-results.v1"
TARGET = "ask-insects"
PUBLIC_QUESTION_COUNT = 40
HOLDOUT_QUESTION_COUNT = 10
QUESTION_COUNT = 50
MAXIMUM_SECONDS = 60.0
MINIMUM_CATEGORY_COUNT = 6

class RealityEvalError(ValueError):
    pass

def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RealityEvalError(f"could not read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RealityEvalError(f"{path} must contain a JSON object")
    return payload
```

Add these exact typed public interfaces, keeping repeated string/list/object
checks in private helpers so public and holdout cases use one validator:

- `validate_public_manifest(payload: object) -> dict[str, object]`
- `validate_holdout_bundle(payload: object) -> dict[str, object]`
- `build_holdout_receipt(bundle_bytes: bytes) -> dict[str, object]`
- `validate_holdout_receipt(payload: object, *, bundle_bytes: bytes | None = None) -> dict[str, object]`
- `assemble_contract(public_manifest: object, holdout_bundle: object) -> dict[str, object]`
- `validate_contract(payload: object) -> dict[str, object]`
- `validate_results(payload: object, *, contract: dict[str, object], contract_sha256: str) -> dict[str, object]`
- `summarize_results(results: dict[str, object]) -> dict[str, object]`

Validation must reject duplicate IDs/questions, missing truth fields, fewer
than six categories, public holdouts, non-holdout private cases, meta questions
marked as domain work, an elapsed time of exactly 60.0 seconds, missing route
trace, alternate answer systems, any non-pass verdict, missing provenance, or
incomplete recording metadata.

- [ ] **Step 4: Run the contract tests**

Run:

```bash
python3 -m pytest tests/test_reality_eval.py -q
```

Expected: all current schema tests pass.

- [ ] **Step 5: Commit the contract module**

```bash
git add askinsects/reality_eval.py tests/test_reality_eval.py
git commit -m "feat: add reality eval artifact contract"
```

## Task 4: Build The 40 Public Scientist Questions

**Files:**
- Create: `evals/ask_insects_reality_eval_public_v1.json`
- Modify: `tests/test_reality_eval.py`

- [ ] **Step 1: Add the canonical-manifest test**

```python
def test_canonical_public_manifest_is_realistic_and_complete(self):
    manifest = load_json_object(DEFAULT_PUBLIC_MANIFEST)
    validate_public_manifest(manifest)
    questions = manifest["questions"]
    self.assertEqual(len(questions), 40)
    self.assertTrue(all(case["kind"] == "domain" for case in questions))
    self.assertTrue(all(case["holdout"] is False for case in questions))
    self.assertGreaterEqual(len({case["category"] for case in questions}), 6)
    self.assertTrue(
        all("ask insects" not in case["question"].casefold() for case in questions)
    )
```

- [ ] **Step 2: Run the test and confirm the manifest is absent**

Run:

```bash
python3 -m pytest tests/test_reality_eval.py -k canonical_public_manifest -q
```

Expected: file-not-found failure.

- [ ] **Step 3: Freeze these 40 public questions**

Use the 20 existing scientist questions as the first half, recategorized into
the shared categories below. Add these 20 adjacent questions as the second
half:

1. How strong is the evidence that specific odorant or ionotropic receptors drive SWD avoidance, rather than merely responding to an odor?
2. Could visual contrast or fruit color confound an SWD assay intended to measure odor-mediated repellency?
3. After a volatile is removed, what recovery measurements would show whether SWD avoidance persists, habituates, or rapidly disappears?
4. How could age, mating status, hunger, or prior egg laying change an SWD repellent result?
5. What changes when an SWD volatile that works in a still-air chamber is moved into a windy crop canopy?
6. Which non-target and crop-safety measurements should accompany an SWD repellent field trial?
7. What evidence would distinguish learned habituation from inherited resistance to an SWD repellent?
8. Which endpoints connect fewer SWD eggs on fruit to fewer surviving larvae and less marketable crop loss?
9. How redundant are carbon dioxide, human odor, heat, humidity, and visual cues during Aedes aegypti host seeking?
10. How should time of day and mosquito circadian state be controlled in a human-repellent assay?
11. Can prior odor or host experience change how Aedes aegypti responds to a repellent?
12. How much can mosquito population, genotype, age, or insecticide-resistance background change a repellent result?
13. How should dose, evaporation rate, air concentration, and distance be reported for an Aedes spatial repellent?
14. What can an arm-in-cage landing assay establish, and what can it not establish about actual bite prevention?
15. Which sweat, washing, abrasion, sunlight, and temperature tests are needed to estimate how long a skin repellent protects a person?
16. How do we distinguish physiological resistance to a mosquito repellent from ordinary behavioral avoidance or reduced sensitivity?
17. Which plant cues guide diamondback moth host finding and egg laying, and which evidence is direct for Plutella xylostella?
18. For diamondback moth, which life stage and crop-damage endpoints should a repellent program measure first?
19. What can SWD or mosquito spatial-repellency evidence legitimately suggest for diamondback moth, and what must be tested directly?
20. Before screening diamondback moth repellents, what is the most important public-evidence gap to close and what experiment would close it?

The final category set must include at least:

```text
swd-sensory-behavior
swd-oviposition-ecology
swd-assay-interpretation
swd-product-translation
aedes-sensory-behavior
aedes-physiology-ecology
aedes-assay-interpretation
aedes-product-translation
diamondback-expansion
```

- [ ] **Step 4: Independently verify every truth packet**

For each question:

1. Locate candidate public evidence through the hosted Ask Insects source plane.
2. Open the cited original paper, dataset, or official public guidance after
   retrieval; do not accept an Ask Insects summary as the judge.
3. Record only claims directly supported by the original source.
4. Record source IDs and exact locators that the normal answer must expose.
5. Mark cross-species reasoning as inference and verified absence as a source
   gap.
6. Add a one-sentence `why_realistic`, an `expected_behavior`, a
   human-readable `truth_source`, and the complete `truth_packet` object.

No case may use a fabricated URL, a keyword-only expectation, or a private
Monarch source.

- [ ] **Step 5: Validate the public corpus**

Run:

```bash
python3 -m pytest tests/test_reality_eval.py -k canonical_public_manifest -q
```

Expected: pass with exactly 40 unique non-holdout domain questions and at least
six categories.

- [ ] **Step 6: Commit the public corpus**

```bash
git add evals/ask_insects_reality_eval_public_v1.json tests/test_reality_eval.py
git commit -m "test: add realistic Ask Insects question corpus"
```

## Task 5: Add Holdout Receipt And Contract Assembly Commands

**Files:**
- Create: `scripts/eval_reality.py`
- Modify: `tests/test_reality_eval.py`

- [ ] **Step 1: Write CLI tests against a temporary private bundle**

Test all of these commands through `scripts.eval_reality.main()`:

```text
validate-public --public /tmp/realityeval/public.json
freeze-holdouts --holdouts /tmp/realityeval/holdouts.json --receipt /tmp/realityeval/receipt.json
assemble --public /tmp/realityeval/public.json --holdouts /tmp/realityeval/holdouts.json --receipt /tmp/realityeval/receipt.json --output /tmp/realityeval/contract.json
validate-contract --contract /tmp/realityeval/contract.json
validate-results --contract /tmp/realityeval/contract.json --results /tmp/realityeval/results.json
summary --contract /tmp/realityeval/contract.json --results /tmp/realityeval/results.json
```

Assert that `freeze-holdouts` writes no questions or truth data to the receipt,
and that `assemble` rejects a one-byte change to the private bundle after the
receipt was frozen.

- [ ] **Step 2: Run the CLI tests and confirm the script is missing**

Run:

```bash
python3 -m pytest tests/test_reality_eval.py -k cli -q
```

Expected: import failure for `scripts.eval_reality`.

- [ ] **Step 3: Implement the thin CLI**

Use `argparse` subcommands. Keep all schema logic in
`askinsects.reality_eval`; the script only reads bytes, invokes the public
functions, writes pretty JSON with a trailing newline, and reports errors to
stderr with exit code 2.

Default paths:

```python
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBLIC = REPO_ROOT / "evals" / "ask_insects_reality_eval_public_v1.json"
DEFAULT_RECEIPT = REPO_ROOT / "evals" / "ask_insects_reality_eval_holdout_receipt_v1.json"
DEFAULT_HOLDOUTS = (
    Path.home()
    / ".local/share/ask-insects/realityeval/ask-insects-holdouts-v1.json"
)
```

- [ ] **Step 4: Run the CLI tests**

Run:

```bash
python3 -m pytest tests/test_reality_eval.py -k cli -q
```

Expected: all CLI tests pass.

- [ ] **Step 5: Commit the tooling**

```bash
git add scripts/eval_reality.py tests/test_reality_eval.py
git commit -m "feat: add reality eval freeze and validation CLI"
```

## Task 6: Enforce Immutable App Results And Independent Grading

**Files:**
- Modify: `askinsects/reality_eval.py`
- Modify: `tests/test_reality_eval.py`

- [ ] **Step 1: Add strict result tests**

Create one complete synthetic 50-result document and mutate one field at a
time. Assert rejection for:

```python
def test_results_fail_closed(self):
    mutations = (
        (("results", 0, "elapsed_seconds"), 60.0, "strict time limit"),
        (("results", 0, "attempt"), 2, "first attempt"),
        (("results", 0, "fresh_task"), False, "fresh task"),
        (("results", 0, "complete_answer_visible"), False, "complete"),
        (("results", 0, "answer_systems"), ["ask-monarch"], "alternate"),
        (("results", 0, "content_verdict"), "fail", "content_verdict"),
        (("recording", "question_count"), 49, "question_count"),
        (("recording", "shared_with_josh"), False, "shared"),
    )
    for path, value, message in mutations:
        with self.subTest(path=path):
            payload = passing_results()
            cursor = payload
            for component in path[:-1]:
                cursor = cursor[component]
            cursor[path[-1]] = value
            with self.assertRaisesRegex(RealityEvalError, message):
                validate_results(
                    payload,
                    contract=passing_contract(),
                    contract_sha256=passing_contract_sha256(),
                )
```

Also require each result to include:

```json
{
  "route_trace": {
    "thread_id": "codex-thread-id",
    "submitted_at": "2026-07-16T12:00:00Z",
    "completed_at": "2026-07-16T12:00:20Z",
    "answer_command_count": 1,
    "hosted_route": true,
    "raw_trace_path": "/absolute/private/artifact/trace.json"
  },
  "scientific_grade": {
    "judge": "independent-source-review",
    "truth_packet_sha256": "64 lowercase hex characters",
    "claim_checks": [
      {"claim": "Measured observation", "verdict": "pass", "evidence": "Source locator"}
    ]
  }
}
```

Top-level `run_manifest` must identify repository commit, installed skill hash,
hosted revision, public corpus hash, holdout receipt hash, evaluator version,
and the unchanged-run start and finish timestamps.

- [ ] **Step 2: Run the new tests and confirm validation gaps**

Run:

```bash
python3 -m pytest tests/test_reality_eval.py -k results -q
```

Expected: failures for fields not yet enforced.

- [ ] **Step 3: Complete result validation and summary statistics**

`validate_results()` must preserve exact question wording, require each ID once,
verify the exact contract-byte SHA-256, require every verdict to equal `pass`,
and reject any elapsed time greater than or equal to the contract maximum.

`summarize_results()` returns:

```python
{
    "question_count": 50,
    "passed_count": 50,
    "failed_count": 0,
    "p50_seconds": 0.0,
    "p95_seconds": 0.0,
    "maximum_seconds": 0.0,
    "reality_eval_passed": True,
}
```

Use nearest-rank p95 and the median from `statistics.median`.

- [ ] **Step 4: Prove compatibility with the installed RealityEval validator**

Run the repository tests, then validate the synthetic final fixture with:

```bash
python3 /Users/josh/.codex/skills/realityeval/scripts/validate_eval.py \
  --contract /tmp/realityeval/synthetic-contract.json \
  --results /tmp/realityeval/synthetic-results.json
```

Expected: both validators accept the passing fixture; repository validation is
the stricter superset.

- [ ] **Step 5: Commit immutable-result validation**

```bash
git add askinsects/reality_eval.py tests/test_reality_eval.py
git commit -m "test: enforce complete reality eval results"
```

## Task 7: Replace The Repository Completion Rule

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/production-path-evaluation.md`
- Modify: `docs/superpowers/specs/2026-07-13-dual-product-insect-intelligence-design.md`
- Modify: `docs/superpowers/plans/2026-07-15-broad-natural-language-production-readiness.md`
- Modify: `scripts/verify_complete.py`
- Modify: `tests/test_reality_eval.py`

- [ ] **Step 1: Add source-of-truth documentation tests**

```python
def test_authoritative_docs_name_one_reality_eval_gate(self):
    root = Path(__file__).parents[1]
    paths = [
        root / "AGENTS.md",
        root / "README.md",
        root / "docs/production-path-evaluation.md",
        root / "docs/superpowers/specs/2026-07-13-dual-product-insect-intelligence-design.md",
        root / "docs/superpowers/plans/2026-07-15-broad-natural-language-production-readiness.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    self.assertIn("exactly 50", text)
    self.assertIn("10 sealed holdouts", text)
    self.assertIn("real Codex app", text)
    self.assertNotIn("minimum 200-question", text)
    self.assertNotIn("20-question demonstration", text)
```

- [ ] **Step 2: Run the test and confirm stale language fails**

Run:

```bash
python3 -m pytest tests/test_reality_eval.py -k authoritative_docs -q
```

Expected: failure on the old 200-plus-20 text.

- [ ] **Step 3: Update every authoritative document**

State in plain language that:

- exactly 50 natural questions use normal Codex
- 40 are public development cases and 10 are sealed holdouts
- every complete first answer must arrive in under 60 seconds
- every answer must pass independent accuracy, source, relevance,
  completeness, usefulness, privacy, and provenance review
- any failure restarts the counted run after a general repair and new holdouts
- the complete passing run must be recorded in the real Codex app and shared
- the old 210 cases are optional regression coverage, not completion evidence

Mark the superseded sections rather than leaving contradictory prose.

- [ ] **Step 4: Replace `check_production_path_evaluation()`**

Rename it to `check_reality_evaluation()` and make it:

1. load and validate the canonical 40-case public manifest
2. load and validate the committed receipt schema without requiring the private
   holdout file in a public clone
3. inspect `scripts/eval_reality.py` for all six required subcommands
4. verify the installed `realityeval` skill file exists on Josh's machine when
   running the full local completion gate
5. verify no normal answer module imports an eval corpus or special-case module
6. verify the authoritative documents contain the new completion language
7. explicitly report that repository verification does not substitute for the
   private passing artifact and recording

Add the new module, CLI, manifests, plan, spec, and tests to `REQUIRED_FILES`
and `UNIT_TEST_MODULES`. Remove all scientist-demo requirements. Keep the old
210-case evaluator only as optional regression tooling.

- [ ] **Step 5: Run focused documentation and completion checks**

Run:

```bash
python3 -m pytest tests/test_reality_eval.py -k authoritative_docs -q
python3 scripts/verify_complete.py
```

Expected: the documentation test passes. `verify_complete.py` may still fail
only because the real holdout receipt has not yet been frozen; no old 200 or
20-case requirement may remain.

- [ ] **Step 6: Commit the new completion rule**

```bash
git add AGENTS.md README.md docs/production-path-evaluation.md \
  docs/superpowers/specs/2026-07-13-dual-product-insect-intelligence-design.md \
  docs/superpowers/plans/2026-07-15-broad-natural-language-production-readiness.md \
  scripts/verify_complete.py tests/test_reality_eval.py
git commit -m "docs: make reality eval the completion gate"
```

## Task 8: Run The Public 40-Case Development Loop

**Files:**
- Modify only the general source, retrieval, routing, answer-construction, and
  focused test files implicated by real failures.
- Write artifacts outside Git under `artifacts/reality-evals/development-*`.

- [ ] **Step 1: Freeze the development environment**

Record current repository commit, installed Ask Insects skill SHA-256, hosted
health response/revision, and public manifest SHA-256. Confirm the installed
normal route uses one hosted `ask-insects ask "$QUESTION" --answer-only`
call.

- [ ] **Step 2: Ask all 40 public questions through fresh Codex tasks**

Use the exact committed wording once per fresh normal task. Preserve full
answers, elapsed time, task IDs, raw traces, and complete provenance. This is a
diagnostic run and does not satisfy the final 50-case gate.

- [ ] **Step 3: Grade against original public sources**

Check every answer after capture. Do not grade from required words or Ask
Insects' own summary. Preserve `PASS`, `FAIL`, `GAP`, or `NOT VALIDATED` plus
specific evidence for each claim.

- [ ] **Step 4: Repair only general failures**

For each failure, add a focused regression test, implement the smallest
general fix, run neighboring unseen paraphrases, and preserve the failed
artifact. Never import the manifest or match exact question text in product
code.

- [ ] **Step 5: Repeat until the unchanged public route is 40 of 40**

After every code change, run focused tests, the full repository gate, merge,
deploy, refresh the installed skill if relevant, and restart the 40 cases from
question 1. Do not create sealed holdouts until this development loop is green.

## Task 9: Freeze Ten Genuine Holdouts And Their Receipt

**Files:**
- Create outside Git:
  `~/.local/share/ask-insects/realityeval/ask-insects-holdouts-v1.json`
- Create: `evals/ask_insects_reality_eval_holdout_receipt_v1.json`

- [ ] **Step 1: Have an independent evaluator create ten cases privately**

The evaluator must use the same user and product scope but must not copy or
paraphrase the 40 public questions. It writes ten complete cases with truth
packets directly to the private path and returns only the bundle path, count,
and hash to the implementation agent.

- [ ] **Step 2: Freeze the public receipt without exposing questions**

Run:

```bash
python3 scripts/eval_reality.py freeze-holdouts \
  --holdouts "$HOME/.local/share/ask-insects/realityeval/ask-insects-holdouts-v1.json" \
  --receipt evals/ask_insects_reality_eval_holdout_receipt_v1.json
```

Expected: receipt reports version, target, count 10, creation time, and one
SHA-256. It contains no `question`, `expected_behavior`, `truth_packet`, source
locator, or scientific claim.

- [ ] **Step 3: Assemble and validate the private final contract**

```bash
python3 scripts/eval_reality.py assemble \
  --public evals/ask_insects_reality_eval_public_v1.json \
  --holdouts "$HOME/.local/share/ask-insects/realityeval/ask-insects-holdouts-v1.json" \
  --receipt evals/ask_insects_reality_eval_holdout_receipt_v1.json \
  --output artifacts/reality-evals/final-candidate/contract.json
python3 /Users/josh/.codex/skills/realityeval/scripts/validate_eval.py \
  --contract artifacts/reality-evals/final-candidate/contract.json
```

Expected: exactly 50 questions, at least 40 domain cases, exactly 10 holdouts,
at least six categories, and no schema errors.

- [ ] **Step 4: Commit only the non-secret receipt**

```bash
git add evals/ask_insects_reality_eval_holdout_receipt_v1.json
git commit -m "test: freeze Ask Insects reality eval holdouts"
```

## Task 10: Verify, Merge, And Ship The Frozen Revision

**Files:**
- No new product behavior unless verification exposes a real defect.

- [ ] **Step 1: Run focused tests**

```bash
python3 -m pytest tests/test_reality_eval.py tests/test_index.py tests/test_answer.py -q
```

Expected: pass.

- [ ] **Step 2: Run the full repository completion gate**

```bash
python3 scripts/verify_complete.py
```

Expected: pass, while explicitly stating that the final app run and recording
remain external completion evidence.

- [ ] **Step 3: Review the complete diff and repository status**

```bash
git diff origin/main...HEAD --check
git status --short --branch
```

Expected: no whitespace errors and no accidental holdout or result files in
Git.

- [ ] **Step 4: Push, open a pull request, pass CI, and merge**

Use the repository's normal GitHub flow. Do not merge if required checks fail.

- [ ] **Step 5: Deploy and refresh installed runtime surfaces**

Load `/Users/josh/.codex/skills/ship/SKILL.md`. Deploy the hosted Ask Insects
revision, refresh the installed Ask Insects skill when owned files changed,
and verify hosted health plus one unseen natural-language smoke question.

- [ ] **Step 6: Re-freeze if shipping changed any evaluated fingerprint**

If the merge, deployment, or installed skill differs from the candidate run
manifest, update the run manifest before question 1. Never patch after the
counted run starts.

## Task 11: Run And Record The Final 50 Questions

**Files:**
- Create outside Git under one timestamped directory such as
  `artifacts/reality-evals/20260716T120000Z/`: contract, transcripts, traces,
  results, grading notes, recording, contact sheet, and privacy review.

- [ ] **Step 1: Start the real Codex-app recording**

Load `/Users/josh/.codex/skills/codexdemo/SKILL.md`. Record the actual Codex app
before submitting question 1. Keep unrelated private apps and notifications out
of frame.

- [ ] **Step 2: Ask all 50 exact questions once**

For each case, create a fresh normal Codex task, submit only the frozen natural
question, and wait for the complete visible answer. Record submission and
completion times. Do not warm, retry, rephrase, preflight, inspect the truth
packet, or change the deployed revision between cases.

- [ ] **Step 3: Preserve full app evidence**

Store the task ID, exact question, full visible answer, elapsed time, raw route
trace, source IDs, locators, and errors. The recording must show the exact
question and complete answer for every case, including long answers that
require scrolling.

- [ ] **Step 4: Grade only after capture**

An independent source reviewer checks the frozen truth packet and original
sources. Record pass/fail for route, time, content, source, privacy, and
usefulness plus claim-level evidence. A missing independent check is
`NOT VALIDATED`, not a pass.

- [ ] **Step 5: Restart fully after any failure**

Preserve the failed artifact and recording, diagnose the general cause, add a
focused test, repair and ship end to end, burn all ten exposed holdouts, create
ten replacements, freeze a new receipt, and restart at question 1.

- [ ] **Step 6: Validate the passing artifact**

Set `PASSING_RUN` to the absolute timestamped passing artifact directory, then
run:

```bash
python3 scripts/eval_reality.py validate-results \
  --contract "$PASSING_RUN/contract.json" \
  --results "$PASSING_RUN/results.json"
python3 /Users/josh/.codex/skills/realityeval/scripts/validate_eval.py \
  --contract "$PASSING_RUN/contract.json" \
  --results "$PASSING_RUN/results.json"
python3 scripts/eval_reality.py summary \
  --contract "$PASSING_RUN/contract.json" \
  --results "$PASSING_RUN/results.json"
```

Expected: `question_count: 50`, `passed_count: 50`, `failed_count: 0`,
`reality_eval_passed: true`, and `maximum_seconds` strictly below 60.

- [ ] **Step 7: Review and share the recording**

Create a contact sheet, inspect every question-answer segment for complete text
and provenance, perform the privacy review, and confirm the recording matches
the immutable results artifact. Share the absolute recording path or approved
private share with Josh.

## Task 12: Completion Audit

**Files:**
- Read-only audit of repository, deployment, installed skill, final artifacts,
  and recording.

- [ ] **Step 1: Audit every design acceptance criterion**

For each criterion in
`docs/superpowers/specs/2026-07-16-ask-insects-reality-eval-integration-design.md`,
record the exact proving file, command output, deployed revision, result field,
or recording segment. Missing or indirect evidence is incomplete.

- [ ] **Step 2: Confirm public/private separation**

Verify Git history, the public branch, hosted public source plane, result share,
and recording contain no private Ask Monarch data and no private holdout truth
packets.

- [ ] **Step 3: Confirm one unchanged live revision passed**

Match the repository commit, installed skill hash, hosted revision, public
manifest hash, holdout receipt hash, and evaluator version in the final run
manifest to the deployed state.

- [ ] **Step 4: Complete the goal only after Josh can open the recording**

Report the 50/50 result, p50, p95, maximum time, source-validation method,
artifact path, deployed revision, and recording path. Do not call the goal
complete before the passing artifact and reviewed recording are shared.
