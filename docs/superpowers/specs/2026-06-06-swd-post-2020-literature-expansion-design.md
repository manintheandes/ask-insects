# SWD Post-2020 Literature Expansion Design

## Goal

Increase the hosted Ask Insects `Drosophila suzukii` paper corpus for papers from 2020 onward. The current hosted answer surface reports 1,067 SWD paper records, and the hosted source-coverage record says the literature lane is `mapped_queryable_bounded` with broader OpenAlex/PubMed mismatch review still missing.

## Boundary

This change expands paper discovery. It does not claim all SWD papers in the world, scrape publisher pages, bypass paywalls, or parse every supplement file format. The canonical answer surface remains hosted Ask Insects. Local code and tests are the implementation surface used to prepare a hosted refresh.

The first expansion target is `drosophila_suzukii_core`, because it owns canonical OpenAlex literature rows. The PubMed lane remains an audit and reconciliation lane. It can expose PubMed-only candidates, but it should not silently replace canonical OpenAlex paper records.

## Discovery Terms

The current OpenAlex query searches the exact scientific name in title and abstract. The expanded discovery should query multiple material SWD aliases:

- `Drosophila suzukii`
- `spotted wing drosophila`
- `spotted-wing drosophila`
- `"SWD" with Drosophila or drosophila context`

The implementation must deduplicate works by OpenAlex work id, DOI, and normalized title when available. Accepted records must preserve which search term found them so later audits can explain why a paper entered the corpus.

## Data Flow

1. `scripts/ingest_drosophila_suzukii.py` calls `fetch_drosophila_suzukii_records`.
2. `fetch_drosophila_suzukii_records` calls the shared OpenAlex literature fetcher with SWD aliases and a higher cap.
3. The shared literature fetcher runs one bounded OpenAlex cursor query per search term.
4. It deduplicates works before writing `EvidenceRecord` rows.
5. `drosophila_suzukii_core` retargets records to SWD provenance and writes source coverage.
6. Follow-on supplement audit lanes can then audit the expanded paper set.

## Acceptance Criteria

- The core SWD ingest can fetch OpenAlex literature using multiple SWD search terms from 2020 onward.
- Duplicate OpenAlex works returned by multiple aliases are stored once.
- Record payloads preserve discovery search terms and inclusion paths.
- The default SWD literature cap is high enough to exceed the current 1,067 hosted paper boundary when upstream sources expose more candidates.
- Tests prove multi-term discovery and deduplication without calling the network.
- Docs tell future agents to increase canonical paper count before judging supplement coverage.

## Verification

Run:

```bash
python3 -m pytest tests/test_drosophila_suzukii_source.py tests/test_ingest_drosophila_suzukii.py tests/test_drosophila_suzukii_pubmed_literature_source.py tests/test_ingest_drosophila_suzukii_pubmed_literature.py -q
python3 scripts/verify_complete.py
```

After deployment or hosted refresh, verify with:

```bash
ask-insects ask --hosted "How many total canonical paper records for Drosophila suzukii since 2020 are indexed? Count papers only." --json
```
