# Open Insects Public Identity Design

## Purpose

Open Insects is the public umbrella for the project. Ask Insects remains the
CLI and hosted query tool.

The naming split should be visible anywhere a new person first meets the work:
the README, GitHub metadata, package metadata, and Obsidian Publish home page.

## Decision

- Public project name: Open Insects
- Public domain: `https://openinsects.org`
- First tool: Ask Insects
- Command name: `ask-insects`
- Current source boundary: Aedes-first, expanding across mosquitoes and then
  the wider insect world

## Public Sentence

Open Insects is an open-source effort to make insect knowledge queryable,
source-backed, and actionable. Its first tool is Ask Insects, a CLI and hosted
source plane for asking evidence-backed questions about insects.

## Pages And Metadata

- `README.md` opens with Open Insects, then explains Ask Insects.
- `wiki/Ask Insects.md` is the Obsidian Publish landing page and should lead
  with Open Insects while preserving install instructions for Ask Insects.
- `wiki/Source Map.md` explains that Ask Insects is the first Open Insects
  source-backed tool.
- `pyproject.toml` declares homepage and source URLs.
- GitHub repo description and homepage point to Open Insects and
  `https://openinsects.org`.

## Verification

The repo completion gate should fail if the Open Insects identity disappears
from the README, wiki home page, package metadata, or source map.
