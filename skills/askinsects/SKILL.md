---
name: askinsects
description: >-
  Use when the user invokes askinsects, ask insects, @askinsects, or /askinsects,
  or asks an insect science, behavior, biology, ecology, repellent, crop-pest,
  disease-vector, source-coverage, public-evidence, species-profile, or portfolio
  question. This includes adding a new insect or asking whether answer-routing
  design must change for one. This description is the complete route. Do not
  open this file for a normal answer. The first hosted command must be
  ask-insects ask "<the user's exact question>" --json --compact. If it yields
  a session ID, continue with write_stdin until exit. If the wrapper reports a cell ID,
  call functions.wait on that same cell until exit. Then return final_answer verbatim.
---
# Ask Insects

Ask Insects provides open, source-backed insect science.
It publishes a generic public evidence package for any downstream tool.
Its first products are an SWD crop repellent and a human mosquito repellent. The active species are
`Drosophila suzukii` and `Aedes aegypti`; diamondback moth (`Plutella
xylostella`) is the next expansion proof.

## Normal Answer

Do not inspect memory, Chronicle, repository docs, another skill, or the web
before the hosted call. Do not emit a progress update or preamble. Run the
hosted command as the first visible action. Use the installed command, or
`$HOME/.local/bin/ask-insects` when it is not on `PATH`:

```bash
ask-insects ask "<the user's exact question>" --json --compact
```

When using `functions.exec`, begin with `// @exec: {"yield_time_ms": 30000, "max_output_tokens": 20000}`.
A command may yield a session ID or report `Script running with cell ID`. Continue that same process with
`write_stdin` for the session or `functions.wait` on the same cell until exit. Never discard a yielded command or issue another Ask Insects command.

A bare call uses the hosted production source plane. Never add `--local` to a
user answer. When `ok` is true, return `final_answer` verbatim as the entire
visible answer. Do not preface, rewrite, summarize, append, search, run SQL, or
run a second Ask Insects call. Complete the visible answer in under 60 seconds.
Do not run setup-agent during a user question. Do not run tests, installation,
or source refreshes during a normal answer.

## Evidence Contract

- Answer from hosted records, not model memory.
- Give the source id and exact row or locator for every material factual answer.
- Keep species, sex, life stage, assay, endpoint, dose, duration, formulation,
  crop or human context, and environment distinct when the source provides them.
- Label direct evidence, cross-species inference, candidate or unverified
  extraction, disagreement, uncertainty, and missing knowledge.
- Never turn another insect's record into direct focal-species evidence.
- Program records describe coverage and gaps, not proof of efficacy, safety,
  readiness, or commercial success.
- Repellency comparisons must preserve contact versus non-contact, spatial
  versus topical, assay, endpoint, dose, duration, and species comparability.
  Unsupported literature-wide claims fail closed.
- If evidence is inadequate, name the source gap. Do not fill it from general
  knowledge or ad hoc web search.
- Preserve canonical product labels. For portfolio answers, cite `#portfolio`
  and write every cited locator in full.

## Boundary And Maintenance

Ask Insects owns public insect evidence. Private experiments and results belong
in a separate private system. Private evidence cannot be imported into Ask
Insects or used to fill gaps in public evidence.

Maintenance may run `python3 scripts/verify_complete.py` and `ask-insects
setup-agent`. Source onboarding uses the `insectsource` skill.
