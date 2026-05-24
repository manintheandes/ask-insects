# Insects Skills

Insects skills are reusable instruction packs for Claude Code, Codex, and other coding agents.

Each skill teaches the agent how to do a specific Ask Insects workflow consistently: which insect sources or tools to use, what output to produce, and what proof to include. Users usually do not need to choose a skill. They ask the question normally, and the agent uses the relevant skill when it helps.

## Installed Skills

| Skill | What it does | Example use |
| --- | --- | --- |
| `askinsects` | Answers insect questions using Ask Insects. | "Search Aedes aegypti records and cite the source rows." |
| `insectsource` | Adds, checks, or repairs Ask Insects source lanes. | "Add this public dataset as an Ask Insects source and prove Ask Insects can answer from it." |
| `source` | Applies the general source contract when a corpus needs to become queryable. | "Map this API, parse its records, and make the smallest useful units queryable." |
| `braintrust` | Inspects traces, spans, evals, and routing behavior when observability is wired. | "Open the trace for this Ask Insects answer and show why it chose that source." |
| `harness-engineering` | Keeps the repo legible for agents through docs, gates, source maps, and validators. | "Make this source lane mechanically verifiable." |

## Example: Hosted Source Answer

Some skills prove the source plane is working end to end. For example, `askinsects` can ask the hosted server a neurobiology question and return a sourced CATMAID skeleton manifest answer.

![[Assets/skill-proofs/askinsects-hosted-catmaid-proof.png]]

The evidence comes from `aedes_neurobiology_sources` and cites `neuro:connectome:catmaid:skeleton-manifest`.

<!-- publish-bump: 2026-05-24T06:51:53-07:00 -->
