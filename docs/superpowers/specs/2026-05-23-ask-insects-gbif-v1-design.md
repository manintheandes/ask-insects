# Ask Insects GBIF V1 Design

## Purpose

GBIF V1 makes Ask Insects pull a small, real, public mosquito source lane instead of only using repo fixtures.

The goal is not to mirror all GBIF data. The goal is to prove that Ask Insects can map an external biodiversity source, fetch bounded records, normalize them into the local index, write receipts, and answer with GBIF provenance.

## Source Boundary

GBIF is the taxonomy and occurrence source for V1.

Ask Insects will use:

- GBIF species match for scientific names.
- GBIF occurrence search for a small number of occurrence records per matched taxon.

V1 will not use GBIF bulk downloads, authenticated downloads, occurrence cubes, or every mosquito species. Those belong after the small source lane is proven.

## Default Species

The first GBIF pull covers the same species shape as the fixture plane:

- `Aedes aegypti`
- `Culex pipiens`
- `Anopheles gambiae`

The command also accepts explicit species names so the lane can grow without code changes.

## Data Flow

The GBIF source loader fetches raw JSON, writes raw response files under `artifacts/mosquito-v1/raw/gbif/`, then converts records into `EvidenceRecord` rows.

Taxonomy records use lane `taxonomy`. Occurrence records use lane `observations`. GBIF media URLs, when present, are copied into `media_url`; records without media still remain valid observations.

The builder writes one SQLite index that can contain both fixture and GBIF records. It also writes:

- `source_status.json`
- `source_receipt.json`
- `gaps.json`

The receipt records source ids, species requested, GBIF taxon keys, occurrence counts, raw artifact paths, and generated time.

## CLI

The build command gains a GBIF mode:

```bash
python3 scripts/build_source_index.py --fixtures --gbif --species "Aedes aegypti" --species "Culex pipiens" --occurrence-limit 3
```

`--fixtures` remains deterministic and offline. `--gbif` requires network access. When both are present, the index includes both lanes.

The normal query commands do not need separate GBIF syntax. Users ask the same questions:

```bash
python3 -m askinsects sources
python3 -m askinsects ask "what do we know about Aedes aegypti?"
python3 -m askinsects search observations "Brazil"
python3 -m askinsects sql "select source, lane, count(*) from records group by source, lane"
```

## Error Handling

GBIF failures must not look like evidence.

If a species cannot be matched, the builder records a source gap and continues with other species. If the GBIF API request fails, the build exits nonzero with a plain error. If GBIF returns no occurrence records for a matched species, the builder records that as a gap.

## Testing

Unit tests use fake GBIF responses. They must not depend on the live GBIF service.

The completion gate continues to prove the deterministic fixture source plane. It also verifies that the GBIF code exists and that mocked GBIF normalization works. Live GBIF pulls stay opt-in because network data can change.

## References

- GBIF Species API: `https://techdocs.gbif.org/en/openapi/v1/species`
- GBIF Occurrence API: `https://techdocs.gbif.org/en/openapi/v1/occurrence`
