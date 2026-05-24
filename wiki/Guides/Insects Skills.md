# Insects Skills

Insects skills are reusable instruction packs for Claude Code, Codex, and other coding agents.

Each skill teaches the agent how to do a specific Ask Insects workflow consistently: which insect sources or tools to use, what output to produce, and what proof to include. Users usually do not need to choose a skill. They ask the question normally, and the agent uses the relevant skill when it helps.

## Installed Skills

| Skill | What it does | Example use |
| --- | --- | --- |
| `askinsects` | Answers insect questions using Ask Insects. | "Search Aedes aegypti records and cite the source rows." |
| `source` | Adds, checks, or repairs source coverage when a corpus needs to become queryable. | "Add this public dataset as an Ask Insects source and prove Ask Insects can answer from it." |
| `braintrust` | Inspects traces, spans, evals, and routing behavior when observability is wired. | "Open the trace for this Ask Insects answer and show why it chose that source." |
| `harness-engineering` | Keeps the repo legible for agents through docs, gates, source maps, and validators. | "Make this source lane mechanically verifiable." |

## Example: Source-Backed Answer

A normal question can route through the hosted Ask Insects server and return source-grade evidence:

```text
Can we bulk download CATMAID skeleton IDs for Aedes aegypti?
```

Ask Insects should answer from `aedes_neurobiology_sources`, include the CATMAID skeleton manifest record, and name the remaining whole-brain connectome package gap.
