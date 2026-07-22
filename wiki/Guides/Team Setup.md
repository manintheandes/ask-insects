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

1. Download [Claude Code desktop](https://code.claude.com/docs/en/desktop), [Codex desktop](https://chatgpt.com/codex/), or [OpenCode](https://opencode.ai/download).
2. Open the app and start a new thread.
3. Ask Josh for the current Ask Insects API URL and token.
4. Paste these commands into the thread and ask the agent to run them:

```bash
uv tool install --force "git+https://github.com/manintheandes/ask-insects.git"
ask-insects setup --url "<Ask Insects API URL>" --token "<Ask Insects token>"
```

If the agent says `uv` is not installed, tell it to install `uv` with the Astral installer, add `~/.local/bin` to PATH, and run the install command again.

If Claude Code says `git` is not installed, tell it to install Git first, then run the install command again.

5. Wait for setup to say `status: ready`.
6. Open a fresh Codex, Claude Code, or coding-agent thread.
7. Ask an insect question normally.

`status: ready` means the provided API URL was reachable and the Ask Insects skill was installed and verified for Codex, Claude Code, and OpenCode. Each user must receive a URL that is reachable from that user's computer; Josh's `127.0.0.1` tunnel URL cannot be shared with another machine.

To verify the connection later:

```bash
ask-insects health --hosted
```

Ask Insects works best with a capable current model. The checked-in Codex project configuration uses GPT-5.5 at low reasoning for normal questions because the agent only needs to invoke the hosted source-backed route and return its answer under 60 seconds.

<!-- publish-bump: 2026-05-24T06:51:53-07:00 -->
