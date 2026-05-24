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

Open Insects is the public project. Ask Insects is the CLI and hosted query tool that lets a user ask insect questions in natural language from Codex, Claude Code, or another coding agent.

## Install

Each user should do this once on their own computer:

1. Open Codex, Claude Code, or another coding-agent app.
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
6. Open a fresh Codex, Claude Code, or coding-agent thread.
7. Ask an insect question normally.

This makes the new skills show up and makes the source-backed Ask Insects path available to the agent.

<!-- publish-bump: 2026-05-24T06:51:53-07:00 -->
