# AGENTS.md

Keep this repo focused on Ask Insects: a CLI-first local source plane for `Aedes aegypti` evidence. Other mosquitoes are comparison material unless a repo-local plan says otherwise.

## Read Order

1. `README.md`
2. `docs/superpowers/specs/2026-05-23-ask-insects-mosquito-v1-design.md`
3. `docs/source-lanes.md`
4. `docs/querying-ask-insects.md`
5. `config/source-map.yaml`

## Source Rule

Do not answer mosquito questions from model memory when the local source index can be queried. Use `ask-insects` commands or the SQLite index, cite provenance, and report source gaps honestly.

**Hosted plane is the only answer surface.** The canonical evidence lives on the hosted VM, not in the local checkout. Read commands (`ask`, `search`, `sql`, `summary`, `sources`, `health`) route to the hosted plane **by default** — you do not need (and should not rely on) a local index for answers. A bare `ask-insects sql "..."` hits hosted. The `--local` flag is a dev-only escape that warns loudly and reads the (usually empty) local index; never use it to conclude a source is "not queryable." If a source id shows zero rows locally, re-check on the hosted plane before reporting a gap.

## Completion Gate

Run:

```bash
python3 scripts/verify_complete.py
```

Do not call the repo complete until the gate passes.
