# Ask Insects Mosquito V1 Design

Date: 2026-05-23

## Purpose

Ask Insects is a CLI-first source plane for communicating with the insect world through evidence.

V1 starts with mosquitoes. The goal is not to build a general chatbot about insects. The goal is to build a local, source-backed tool that can answer mosquito questions from indexed records, cite the evidence, and say plainly when the local source plane does not know enough.

The product should feel like Ask Monarch in shape:

```text
source artifacts -> mapped lanes -> local parsed indexes -> receipts -> CLI -> answer with provenance or gap
```

## User Experience

A scientist should be able to run commands like:

```bash
ask-insects health
ask-insects summary
ask-insects sources
ask-insects ask "what do we know about Aedes aegypti?"
ask-insects ask "show mosquito observations with images in Brazil"
ask-insects ask "what papers discuss mosquito host seeking?"
ask-insects ask "what should a scientist inspect next for Culex pipiens?"
ask-insects search observations "Aedes aegypti Brazil" --limit 10
ask-insects search papers "mosquito host seeking" --limit 10
ask-insects sql "select species, count(*) from observations group by species"
```

Each answer should include:

- a short plain-language answer
- cited evidence rows
- provenance locators
- source gaps when evidence is missing
- careful next actions when the evidence supports them

## V1 Boundary

V1 indexes mosquitoes first, then expands to other insect groups later.

The first boundary should include:

- mosquito taxonomy and names
- mosquito observations and images
- mosquito-linked public media records, including video when available
- mosquito papers and literature metadata
- source-backed action notes derived from indexed evidence

V1 does not claim to locally mirror every insect image, video, paper, or observation in the world. It should make the mosquito boundary explicit and report coverage honestly.

## Source Lanes

### Taxonomy

The taxonomy lane stores mosquito names, synonyms, rank, family, genus, species, and external identifiers. This lane helps the CLI understand that user wording may refer to common names, old names, or scientific names.

### Observations And Images

The observations lane stores public mosquito occurrence and observation records. Initial sources should include GBIF and iNaturalist-style records where licensing and API terms allow local indexing.

Records should preserve species name, date, place fields, coordinates when available, media URL, license, source URL, source identifier, and retrieval timestamp.

### Videos And Media

The media lane stores public records that expose moving-image media or other inspectable mosquito media. V1 should treat video coverage as scarce and report that honestly.

If a query finds images but no indexed videos, the answer should say that directly.

### Papers And Literature

The literature lane stores mosquito-related paper metadata and open access links. Initial sources should include OpenAlex. Biodiversity Heritage Library can be included when a key is configured.

The lane should support questions about behavior, ecology, host seeking, disease-vector context, conservation, control methods, and field or lab methods.

### Action Notes

The action lane turns source-backed evidence into careful next steps. It should not invent protocols. It should point scientists toward observations to inspect, papers to read, taxa to compare, and source gaps to fill.

## Architecture

The repository should be organized around small, inspectable parts:

- `askinsects/cli.py`: command-line entry point
- `askinsects/planner.py`: routes questions to answer shapes and source lanes
- `askinsects/sources/`: source fetchers and parsers
- `askinsects/index.py`: SQLite schema and index helpers
- `askinsects/answer.py`: answer assembly and gap reporting
- `config/source-map.yaml`: source boundary and lane contract
- `docs/querying-ask-insects.md`: how to query and cite evidence
- `docs/source-lanes.md`: mosquito V1 lane details and expansion path
- `scripts/build_source_index.py`: builds local indexes and receipts
- `scripts/verify_complete.py`: mechanical completion gate
- `tests/`: focused parser, CLI, planner, and answer-contract tests

The local index is the answer source of record. Live APIs are upstream source inputs, not the ordinary answer path.

## Data Flow

1. Source map declares mosquito V1 lanes and allowed upstream sources.
2. Build script fetches bounded source records for mosquitoes.
3. Parsers normalize records into atomic units.
4. SQLite indexes are written locally.
5. Receipts record counts, timestamps, source parameters, and gaps.
6. CLI reads local indexes.
7. Planner chooses an answer shape: identity, evidence, action, or source gap.
8. Answer layer returns evidence-backed output with provenance.

## Error Handling

Ask Insects should fail honestly.

If a source is not mapped, say the source is not in the local mosquito index yet.

If the source was mapped but not fetched, say the lane has no current receipt.

If records exist but no videos match, say images or observations were found but no indexed moving-image records matched.

If the user asks for action guidance and the indexed evidence is too thin, return a source gap and suggest the next evidence to add or inspect.

Do not answer from general model memory when the local source plane can be queried.

## Testing And Completion

The repo should include one completion gate:

```bash
python3 scripts/verify_complete.py
```

The gate should prove:

- the source map exists and names the mosquito V1 boundary
- local parsers can build SQLite indexes and receipts
- `ask-insects health`, `summary`, and `sources` work
- the CLI can answer one identity question
- the CLI can answer one evidence question
- the CLI can answer one action question
- every answer includes provenance or a clear source gap

Focused tests should cover:

- taxonomy normalization
- observation and media parsing
- literature parsing
- planner routing
- read-only SQL guardrails
- answer provenance requirements
- honest negative answers

## Expansion Path

After mosquitoes, Ask Insects can add more insect groups by repeating the same lane pattern:

```text
taxonomy -> observations/images -> media -> papers -> action notes
```

The expansion should preserve one rule: no group is called queryable until it is mapped, locally indexed, receipted, and reachable through the CLI with provenance.

## Open Decision For Implementation

The first implementation plan should choose a bounded mosquito seed set. A practical seed is a small list of high-value taxa such as `Aedes aegypti`, `Aedes albopictus`, `Anopheles gambiae`, and `Culex pipiens`. The seed can grow after the first verified local index works end to end.
