# AGENTS.md

Keep this repo focused on Ask Insects: the public, source-backed insect intelligence plane for Monarch's repellent work. The first product targets are spotted wing drosophila crop protection and human mosquito protection. `Aedes aegypti` is the first deep mosquito model, and diamondback moth is the next expansion proof.

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

For a normal user-facing insect question, this repo instruction already contains the complete answer route. Do not open or read the Ask Insects skill file. The first and only operational command must be `ask-insects ask "<the user's exact question>" --json --compact`. Do not inspect memory, Chronicle, repository docs, skills, or any other file first. When the call returns `ok: true`, answer
immediately without another command by returning `final_answer` verbatim.
Do not rewrite, preface, or append to it. Preserve canonical labels such as
`SWD crop repellent` and `Human mosquito repellent`, plus every source ID and
locator exactly as returned.

**Hosted plane is the only answer surface.** The canonical evidence lives on the hosted VM, not in the local checkout. Read commands (`ask`, `search`, `sql`, `summary`, `sources`, `health`) route to the hosted plane **by default** — you do not need (and should not rely on) a local index for answers. A bare `ask-insects sql "..."` hits hosted. The `--local` flag is a dev-only escape that warns loudly and reads the (usually empty) local index; never use it to conclude a source is "not queryable." If a source id shows zero rows locally, re-check on the hosted plane before reporting a gap.

Normal user questions must not run repository tests, install or refresh skills, or refresh sources. Release work refreshes the local runtime and repo-owned skill with `bash scripts/install_local_runtime.sh`; `ask-insects setup-agent` refreshes only the skill.

## Completion Gate

Run:

```bash
python3 scripts/verify_complete.py
```

Do not call the repo complete until the gate passes.
