# AGENTS.md

## Normal Question Fast Path

For a normal user-facing insect question, the route is already decided. Do not send commentary, a status update, or a routing preamble. The turn must contain exactly one visible assistant message: the command's complete stdout as the final answer. Do not spend a reasoning turn deciding how to route it. As the first action, run the preferred first and only operational command using this exact literal here-document shape:

```bash
ask-insects ask --question-stdin --answer-only <<'ASK_INSECTS_QUESTION'
USER QUESTION
ASK_INSECTS_QUESTION
```

Replace `USER QUESTION` with the user's exact complete question. In a delegated Codex task, that question is the decoded text inside its single `<input>...</input>` element. Never copy `<codex_delegation>`, `<source_thread_id>`, `<input>`, `</input>`, or any other handoff tag into the command. Do not quote, escape, rewrite, or interpolate the question body. The single-quoted here-document marker makes apostrophes, quotation marks, dollar signs, backticks, and backslashes literal. Do not put any command, comment, or text after the closing marker. If the command yields a session ID, continue the same process with `write_stdin` until it exits and return the accumulated output; this is continuation of the one command, not a second command. Do not load the installed skill; its description and this file already provide the complete route. No other command may precede or follow the hosted call. Never call image generation, `imagegen`, `justsee`, visualization, screenshot, or any other visual helper unless the user explicitly asks for a visual. Do not inspect memory, Chronicle, repository docs, other skills, or any other file first. The command's stdout is already the complete sourced answer. Return it immediately and verbatim without another reasoning turn or command. The visible answer must be byte-for-byte identical to stdout. Never add or remove whitespace, including invisible trailing spaces or Markdown hard-break spaces. Do not parse, rewrite, preface, or append to it. Preserve canonical labels such as `SWD crop repellent` and `Human mosquito repellent`, plus every source ID and locator exactly as returned.

The invocation line must begin with `ask-insects` and contain exactly `ask --question-stdin --answer-only` before the literal here-document marker. Do not add comments, timing directives, or wrapper text to the shell command. If the execution tool returns a continuation handle, continue that same process until it exits; never issue the Ask Insects command again.

The checked-in `.codex/config.toml` uses a reliable Codex routing model at low reasoning because normal answers are latency-sensitive hosted lookups and the model only needs to invoke the hosted route and return its answer. Do not change that project default without rerunning the complete Reality Eval. Select a higher effort explicitly for complex implementation work when needed.

Questions about adding a new insect, species profiles, portfolio expansion, or whether answer-routing design must change are normal Ask Insects questions. Do not emit a progress update or preamble before their hosted call. Run the single command immediately so the complete visible answer remains under 60 seconds.

Keep this repo focused on Ask Insects: open, source-backed insect science and a generic public evidence package for any downstream tool. The objective is to deeply understand insects and accelerate effective, safe repellents that protect people and crops without killing insects. The first product targets are spotted wing drosophila crop protection and human mosquito protection. `Aedes aegypti` is the first deep mosquito model, and diamondback moth is the next expansion proof.

## Read Order

1. `README.md`
2. `docs/superpowers/specs/2026-07-13-dual-product-insect-intelligence-design.md`
3. `docs/superpowers/specs/2026-05-23-ask-insects-mosquito-v1-design.md`
4. `docs/source-lanes.md`
5. `docs/querying-ask-insects.md`
6. `config/insect-intelligence-programs.json`
7. `config/source-map.yaml`

## Source Rule

Do not answer insect questions from model memory when the source index can be queried. Use `ask-insects` commands or the SQLite index, cite provenance, distinguish direct evidence from cross-species inference, and report source gaps honestly.

**Hosted plane is the only answer surface.** The canonical evidence lives on the hosted VM, not in the local checkout. Read commands (`ask`, `search`, `sql`, `summary`, `sources`, `health`) route to the hosted plane **by default** — you do not need (and should not rely on) a local index for answers. A bare `ask-insects sql "..."` hits hosted. The `--local` flag is a dev-only escape that warns loudly and reads the (usually empty) local index; never use it to conclude a source is "not queryable." If a source id shows zero rows locally, re-check on the hosted plane before reporting a gap.

Normal user questions must not run repository tests, install or refresh skills, or refresh sources. Release work refreshes the local runtime and repo-owned skill with `bash scripts/install_local_runtime.sh`; `ask-insects setup-agent` refreshes only the skill.

## Completion Gate

The authoritative Reality Eval asks exactly 50 natural questions through
normal Codex: 40 public development cases and 10 sealed holdouts. Every first,
complete answer must arrive in under 60 seconds and pass independent review for
accuracy, sources, relevance, completeness, usefulness, privacy, and exact
provenance. Any failure requires a general repair, new holdouts, and a fresh
counted run. The complete passing run must be recorded in the real Codex app
and shared with Josh. The legacy 210-case suite is optional regression
coverage, not completion evidence.

Run:

```bash
python3 scripts/verify_complete.py
```

Do not call the repo complete until the gate passes.
