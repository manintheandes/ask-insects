# Aedes aegypti Literature Source Receipt

Run date: 2026-05-23

Canonical query:

```text
OpenAlex works where title_and_abstract.search is "Aedes aegypti",
publication date is 2020-01-01 through 2026-05-23,
and type is article.
```

Build command:

```bash
python3 scripts/build_source_index.py \
  --fixtures \
  --openalex-literature \
  --literature-species "Aedes aegypti" \
  --from-date 2020-01-01 \
  --to-date 2026-05-23 \
  --work-type article \
  --include-topic-discovery \
  --literature-page-size 200 \
  --literature-delay-seconds 1 \
  --skip-pubmed \
  --skip-fulltext \
  --artifact-dir artifacts/aedes-literature-2020
```

Metadata receipt summary:

- Artifact directory: `artifacts/aedes-literature-2020`
- OpenAlex reported total: 10,683
- OpenAlex raw cursor pages: 54
- OpenAlex raw rows: 10,683
- Unique OpenAlex IDs: 10,683
- SQLite `aedes_literature_openalex` literature records: 10,683
- SQLite `record_payloads` rows for `aedes_literature_openalex`: 10,683
- PubMed-enriched payloads: 3,877
- Unpaywall-enriched payloads: 9,706
- Direct legal full-text candidates: 6,378
- SQLite full-text record count: 4,404
- SQLite `literature_fulltext_units` rows: 53,326
- SQLite `literature_fulltext_fts` rows: 53,326
- Direct full-text candidates with explicit fetch or parse gaps: 1,974
- Direct full-text candidates left unresolved: 0
- Gap rows after dedupe: 25,487

Gap reasons:

- OpenAlex missing abstract, topic search gaps, and topic candidate rejections
- PubMed missing PMID or fetch failure
- Missing DOI
- Unpaywall fetch failure, no direct full-text URL, or landing-page-only full text
- Direct full-text fetch or parse failure

Final grouped gap counts:

- `pubmed_skipped`: 10,683
- `pubmed_missing_pmid`: 6,806
- `fulltext_fetch_failed`: 1,944
- `fulltext_landing_page_only`: 1,830
- `unpaywall_no_fulltext_url`: 1,632
- `openalex_missing_abstract`: 1,100
- `missing_doi`: 968
- `unpaywall_fetch_failed`: 493
- `fulltext_parse_failed`: 30
- `openalex_topic_search_empty`: 1

Notes:

- OpenAlex is the canonical discovery source.
- Cursor requests use `sort=publication_date:desc`; this was required to make the 54-page run stable with 10,683 unique IDs matching the OpenAlex reported count.
- PubMed enrichment is performed after OpenAlex ingest with `scripts/enrich_literature_index.py`.
- Unpaywall enrichment is performed after OpenAlex ingest with `scripts/enrich_literature_index.py`.
- Legal direct full text is extracted only from Unpaywall direct PDF/XML URLs or OpenAlex OA PDF URLs.
- PubMed and Unpaywall payloads are stored in SQLite `record_payloads.payload_json`; OpenAlex cursor pages are stored as raw JSON files.
- No Sci-Hub, private cookies, or institutional scraping were used.

Enrichment command:

```bash
python3 scripts/enrich_literature_index.py \
  --artifact-dir artifacts/aedes-literature-2020 \
  --email "$EMAIL"
```

Large full-text extraction may use deterministic shards:

```bash
python3 scripts/enrich_literature_index.py \
  --artifact-dir artifacts/aedes-literature-2020 \
  --email "$EMAIL" \
  --fulltext-only \
  --record-id-shard-count 6 \
  --record-id-shard-index 0
```

Verification commands:

```bash
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 sources
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 summary
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 sql "select source, lane, count(*) as n from records group by source, lane"
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 search literature "Wolbachia dengue" --limit 3
python3 -m askinsects --artifact-dir artifacts/aedes-literature-2020 ask "what papers since 2020 discuss Wolbachia and Aedes aegypti?" --json --limit 3
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
```

Verification result:

- CLI `sources`, `summary`, `search`, `sql`, and `ask` work against `artifacts/aedes-literature-2020`.
- The Wolbachia literature query returns OpenAlex provenance.
- SQL confirms 4,404 full-text records and 53,326 chunks.
- The completion gate checks that every direct legal full-text candidate has either extracted chunks or an explicit full-text gap.
