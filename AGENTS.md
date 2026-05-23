# AGENTS.md

Keep this repo focused on Ask Insects: a CLI-first local source plane for mosquito evidence.

## Read Order

1. `README.md`
2. `docs/superpowers/specs/2026-05-23-ask-insects-mosquito-v1-design.md`
3. `docs/source-lanes.md`
4. `docs/querying-ask-insects.md`
5. `config/source-map.yaml`

## Source Rule

Do not answer mosquito questions from model memory when the local source index can be queried. Use `ask-insects` commands or the SQLite index, cite provenance, and report source gaps honestly.

## Completion Gate

Run:

```bash
python3 scripts/verify_complete.py
```

Do not call the repo complete until the gate passes.
