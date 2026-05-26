---
title: Ask Insects
type: home
status: guided
tags:
  - open-insects
  - insects-wiki
  - ask-insects
  - codex
aliases:
  - Open Insects
  - Ask Insects Wiki
  - Ask Insects
sources:
  - ../README.md
  - ../config/source-map.yaml
  - ../docs/source-lanes.md
---
# Open Insects

Open Insects is an open-source effort to make insect knowledge queryable, source-backed, and actionable.

Its first tool is Ask Insects: a CLI and hosted source plane that brings together observations, images, videos, papers, genomes, behavior records, neurobiology, public-health evidence, and source gaps, then uses what it knows to answer questions and take action for insects.

The command is still simple:

```bash
ask-insects ask "where has Aedes aegypti been spotted this year?"
```

What's inside:

- **1,423,462 hosted source records:** [[Source Map|Aedes aegypti source lanes]] across public biodiversity, genomics, behavior, neurobiology, literature, public health, surveillance, images, videos, repellents, and media evidence
- **100,736 observations / 26,208 media records:** [[Sources/Observations and Images|GBIF, iNaturalist, Mosquito Alert, licensed images, and media locators]]
- **1,059,215 genomics records:** [[Sources/Genome and BioSample Evidence|genes, transcripts, proteins, genome features, BioSamples, DNA barcodes, expression metadata, traits, and assembly records]]
- **100,018 neurobiology records:** [[Sources/Neurobiology and Connectome Evidence|brain atlas, cell atlas, CATMAID skeleton metadata, voxel access, SRA workflow records, and connectome gaps]]
- **Scientific intelligence lanes:** [[Sources/Research Papers|papers and legal full text]], [[Sources/Repellent Discovery|repellent articles, datasets, preprints, patents, and source gaps]], [[Sources/Behavior Media and Datasets|behavior datasets and videos]], [[Sources/Vector Competence and Pathogens|pathogen/vector competence evidence]], [[Sources/Resistance and Control Evidence|resistance evidence]], [[Sources/Ecology and Occurrence Summaries|ecology summaries]], and [[Sources/Public Health and Surveillance|official public-health guidance and dengue surveillance]]

What it does:

- **Answers and analyzes:** species, observation, genomics, behavior, neurobiology, ecology, and public-health questions with source provenance
- **Searches public insect memory:** papers, images, observation records, datasets, genes, proteins, and source receipts
- **Inspects media:** public still images, supplementary videos, behavior datasets, OSF manifests, Dryad manifests, and Mendeley media records
- **Acts on sources:** ingests new public lanes, parses artifacts into SQLite, refreshes hosted evidence, and tracks missing source coverage
- **Improves over time:** starts with Aedes aegypti, then expands across mosquitoes and the wider insect world

## Get Started

Each user should do this once on their own computer:

1. Download [Claude Code desktop](https://code.claude.com/docs/en/desktop), [Codex desktop](https://chatgpt.com/codex/), or [another coding-agent app](https://opencode.ai/download).
2. Start a new thread.
3. Ask Josh for the current Ask Insects API URL and token.
4. Paste these commands into the thread and run them:

```bash
uv tool install "git+ssh://git@github.com/manintheandes/ask-insects.git"
ask-insects setup --url "<Ask Insects API URL>" --token "<Ask Insects token>"
```

If the agent says `uv` is not installed, tell it to install `uv` with the Astral installer, add `~/.local/bin` to PATH, and run the install command again.

If Claude Code says `git` is not installed, tell it to install Git first, then run the install command again.

5. Wait for setup to say `status: ready`.
6. Open a new thread.
7. Ask an insect question normally.

\*Ask Insects works best with Claude Opus 4.7 in Claude Code or GPT-5.5 in Codex, with thinking effort set to high.

```bash
ask-insects health --hosted
```

## Explore Ask Insects

- Want to see what is inside: use [[Source Map]].
- Looking for example questions: use [[Question Cookbook]].
- Need a deeper research memo: use [[Insects Deep Research]].
- Want to know what skills are installed: use [[Insects Skills]].
- Want to know what changed: use [[Ask Insects Updates]].

<!-- publish-bump: 2026-05-26T12:05:00-07:00 -->
