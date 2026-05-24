---
title: Team Setup
type: meta
status: setup
publish: false
tags:
  - insects-wiki
  - setup
  - ask-insects
  - coding-agents
---
# Team Setup

Ask Insects lets a user ask insect questions in natural language from Codex, Claude Code, or another coding agent.

## Install

The packaged team setup flow is not public yet.

On Josh's current machine, Ask Insects is already installed and wired to the hosted server. To check it:

```bash
ask-insects health --hosted
```

If the command is not on PATH, run this from the Ask Insects repo:

```bash
python3 -m askinsects health --hosted
```

After the health check says `ok: true`, ask an insect question normally.

This makes the source-backed Ask Insects path available to the agent.
