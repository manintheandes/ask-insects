# Ask Insects Repellency Evidence Workflow

Date: 2026-07-10
Status: accepted for implementation

## Objective

Ask Insects must answer comparative repellency questions from inspectable
evidence, not from the first matching paper or from model memory. The first
milestone is a trustworthy answer to questions such as:

> Does anything in the literature beat this spatial-repellency result?

The workflow must distinguish a supported comparison from an unsupported
superlative. It must also show what evidence was searched, how deeply each
paper was processed, which assay dimensions are comparable, and why a stronger
claim is blocked.

## Product Contract

A repellency-comparison answer has six required parts:

1. `answer`: a direct, calibrated conclusion.
2. `claim`: the requested claim type, status, reasons, and missing target fields.
3. `comparison`: normalized study rows and the dimensions used for comparison.
4. `coverage`: deduplicated paper counts, depth outcomes, source gaps, and searched sources.
5. `evidence`: claim-relevant records with exact provenance.
6. `source_gap`: a normal Ask Insects source gap when no usable repellent evidence exists.

The contract is versioned as `repellency-comparison.v1`.

## Question Routing

The specialized workflow runs only when a question contains both a repellency
concept and a comparison concept. Repellency concepts include repellent,
repellency, spatial repellent, DEET, picaridin, IR3535, and related terms.
Comparison concepts include compare, better, stronger, outperform, beat, best,
most effective, rank, leading, and nothing in the literature.

Simple discovery questions such as "list recent repellent papers" continue to
use the general literature path.

## Comparison Model

Each structured assay row should preserve these dimensions when the source
provides them:

- species, strain, sex, and life stage
- compound and formulation
- dose or concentration
- exposure mode, including contact, non-contact, topical, and spatial/vapor
- assay design and geometry
- endpoint and effect metric
- measured value and unit
- duration or timepoint
- control or comparator
- sample size and statistical result
- extraction confidence and exact provenance

Missing values remain explicit. The workflow must not infer absent experimental
details from a paper title.

## Coverage Ledger

Coverage is tracked as a paper funnel:

`discovered -> deduplicated -> full text available -> depth outcome -> structured assay fact -> human verified`

The first four states can be derived from the source index. Human verification
must remain zero unless a record explicitly says it was verified. Metadata-only
records count as discovered evidence, not comparison-ready evidence.

Papers are deduplicated by DOI, then PMID, then normalized title. Source gaps
from blocked or failed discovery routes remain visible in the answer.
Bookkeeping outcomes such as a missing DOI or a skipped enrichment lookup are
reported separately from material discovery gaps. Gap totals and reason counts
remain complete, while individual gap details are capped at 25 per answer.

## Claim Policy

Ask Insects never automatically asserts a literature-wide superlative.

A superlative request receives `insufficient_evidence` unless all of these are
true:

1. The target result specifies species, exposure mode, assay, endpoint, dose,
   duration, and measured outcome.
2. Every deduplicated candidate paper has a depth outcome.
3. At least one structured assay fact is directly comparable on all required dimensions.
4. Directly comparable facts include numeric outcomes and uncertainty or a statistical result.
5. No unresolved source gap materially limits the claimed literature universe.
6. The decisive facts are explicitly human verified.

When all checks pass, the status is `eligible_for_expert_review`, not
automatically `supported`. A human scientific reviewer owns the final
literature-leading claim.

Ordinary pairwise comparisons may return `comparison_ready` when target and
study dimensions align, but the answer must still distinguish direct evidence,
related evidence, and noncomparable evidence.

## Evidence Extraction

The generic paper-depth miner gains a dedicated `repellency_assay` fact family.
It identifies candidate assay passages and preserves matched dimension terms.
The comparison layer may normalize values found in the preserved evidence text,
but it must report the extraction confidence and never promote candidate text to
human-verified evidence.

## Evaluation Contract

Repository evaluations include real question shapes, especially unsupported
superlatives. Each case specifies expected routing, claim type, minimum answer
fields, prohibited phrases, and expected guardrail reasons. Unit tests use a
small synthetic source index so failures are deterministic. Hosted verification
uses the same questions against the deployed source plane before release.

## Operational Preconditions

The workflow depends on source integrity. Mutation requests must be serialized,
staging must not hardlink files that an ingest can overwrite, and every
literature-depth ingest must produce source status and a receipt atomically.
These are release prerequisites because incorrect source state invalidates the
coverage ledger.

## Non-Goals

- Claiming exhaustive coverage of paywalled or inaccessible literature.
- Using citation count as a proxy for efficacy.
- Ranking metadata-only papers.
- Replacing scientific review with a deterministic claim rule.
- Parsing every insect paper before a real question requires it.
