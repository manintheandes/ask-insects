---
name: askinsects
description: Use when the user invokes askinsects, ask insects, @askinsects, or /askinsects, or asks an insect science, behavior, biology, ecology, repellent, crop-pest, disease-vector, source-coverage, or public-evidence question that should be answered through Ask Insects.
---

# Ask Insects

Use Ask Insects as the public scientific evidence layer for Monarch's repellent
work. The first products are an SWD crop repellent and a human mosquito
repellent. `Drosophila suzukii` and `Aedes aegypti` are the first active insect
targets. Diamondback moth, `Plutella xylostella`, is next.

## Normal Answer Path

1. Use the installed `ask-insects` command. If it is not on `PATH`, use
   `$HOME/.local/bin/ask-insects`.
2. Query the hosted production source plane. A bare read command is hosted by
   default. Never add `--local` to a user answer.
3. Start with one targeted call:

```bash
ask-insects ask "<the user's exact question>" --json
```

4. When that call returns `ok: true`, answer immediately from that payload.
   Do not inspect memory, browse the web, run a second Ask Insects call, or
   expand the investigation during a normal answer. The hosted answer is
   deliberately complete for broad program and coverage questions.
5. Use hosted `search` or read-only `sql` only when the first call fails or the
   user explicitly asks to inspect a named record beyond the returned evidence.
6. Return the direct answer first, then the evidence and limitations in plain
   language. For a portfolio answer, cite the exact `#portfolio` locator.
   Never shorten a repeated locator to a fragment such as `#products/1`;
   write every cited locator in full.

Complete the visible answer in under 30 seconds. Do not run repository tests,
source refreshes, installation, or broad exploratory commands during a normal
question. Do not run setup-agent during a user question. A one-call answer does
not need a progress update before the final response.

## Evidence Rules

- Answer from the hosted records, not model memory.
- Give the source id and exact row or locator provenance for every material
  factual answer.
- Keep the focal species, sex, life stage, assay, endpoint, dose, duration,
  formulation, crop or human context, and environment distinct when the source
  provides them.
- Label direct focal-species evidence, cross-species inference, candidate or
  unverified extraction, disagreement, uncertainty, and missing knowledge.
- Never turn a search result about another insect into focal-species evidence.
- Never claim product efficacy, readiness, safety, or a literature-wide
  superlative from a planning record or metadata-only paper.
- If the hosted plane lacks adequate evidence, return the source gap and name
  what is missing. Do not fill the gap from general knowledge or an ad hoc web
  search.

## Product And Species Questions

Use the generic `ask` path for product-program, biology-coverage, and expansion
questions. The queryable source is `insect_intelligence_programs`.

Examples:

```bash
ask-insects ask "what does Ask Insects need to understand about spotted wing drosophila?" --json
ask-insects ask "what is missing from diamondback moth biology coverage?" --json
ask-insects ask "what is the product readiness status of the human mosquito repellent?" --json
```

These records describe evidence coverage and gaps. They do not prove that a
compound or product works.

## Comparative Repellency

Let the specialized hosted comparison path handle questions such as whether a
result beats DEET or anything in the literature. Preserve contact versus
non-contact, spatial versus topical, assay, endpoint, dose, duration, and
species comparability. An unsupported best-in-literature claim must fail
closed.

## Public And Private Boundary

Ask Insects owns public insect evidence. Ask Monarch owns private compounds,
assays, videos, results, decisions, and commercial work. Public Ask Insects
evidence may inform a private Ask Monarch answer. Never copy private Ask
Monarch evidence into the public Ask Insects source plane.

## Maintenance

The canonical repository is `/Users/josh/Documents/ask-insects`. Maintenance
and release work may run `python3 scripts/verify_complete.py`. Install this
repo-owned skill with:

```bash
ask-insects setup-agent
```

For source onboarding, mapping, access, parsing, receipts, or source gaps, use
the `insectsource` skill.
