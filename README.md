# Ask Insects

Ask Insects is a CLI-first local source plane for mosquito evidence.

V1 starts with mosquitoes, then expands to other insect groups. It follows the Ask Monarch pattern:

```text
source artifacts -> mapped lanes -> local parsed indexes -> receipts -> CLI -> answer with provenance or gap
```

## Quick Start

```bash
python3 scripts/build_source_index.py --fixtures
python3 -m askinsects health
python3 -m askinsects summary
python3 -m askinsects sources
python3 -m askinsects ask "what do we know about Aedes aegypti?"
python3 -m askinsects ask "show mosquito observations with images in Brazil"
python3 -m askinsects ask "what should a scientist inspect next for Culex pipiens?"
python3 scripts/verify_complete.py
```

## Contract

Ask Insects answers from local indexed records. Every answer includes provenance or a clear source gap. V1 does not claim to mirror all mosquito knowledge. It proves a bounded mosquito seed source plane end to end.
