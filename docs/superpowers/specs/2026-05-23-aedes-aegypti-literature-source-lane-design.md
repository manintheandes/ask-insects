# Aedes aegypti Literature Source Lane Design

## Purpose

Ask Insects needs a source-grade literature lane for academic research papers on
`Aedes aegypti` from January 1, 2020 through the current run date.

The goal is not a one-time bibliography. The goal is a reproducible source
plane: discover the paper universe, save raw source payloads, normalize
queryable rows into SQLite, preserve provenance, enrich open full text where
legally accessible, and record explicit gaps for inaccessible full text.

## Source Boundary

The canonical paper universe is OpenAlex works from January 1, 2020 through the
run date where `Aedes aegypti` is material in the title, abstract, or topic
metadata.

The primary discovery filter is:

```text
title_and_abstract.search:"Aedes aegypti"
from_publication_date:2020-01-01
to_publication_date:<run date>
type:article
```

This boundary means "academic research paper on `Aedes aegypti`" is treated as
an OpenAlex-indexed article whose title, abstract, or source-grade topic
metadata materially indicates the species. It avoids the much broader OpenAlex
full search surface, which returns many passing mentions and non-primary
contexts.

Topic inclusion must be explicit. The ingest should search OpenAlex topics for
`Aedes aegypti` and inspect each work's `primary_topic`, `topics`, and keywords
when present. A topic path can include a paper only when the topic id, topic
display name, topic description, or keyword metadata materially names `Aedes
aegypti`. If OpenAlex has no exact or defensible `Aedes aegypti` topic at run
time, the receipt should say topic expansion found zero additional canonical
topic ids rather than pretending topic coverage exists.

The run date must be written into receipts. As of May 23, 2026, live planning
checks returned these rough counts:

- OpenAlex title or abstract, `type:article`: 10,683 works.
- OpenAlex title or abstract, all work types: 23,254 works.
- OpenAlex broad search, `type:article`: 37,275 works.
- PubMed title or abstract cross-check: 4,617 records.
- OpenAlex topic search for `Aedes aegypti`: no exact topic was returned in the
  planning check, so the first topic expansion may add zero works.

Future runs may change these counts. The receipt count from the actual ingest is
the source of truth for a completed run.

## Source Lanes

Add a new source id:

```text
aedes_literature_openalex
```

The lane writes into a literature artifact boundary, for example:

```text
artifacts/aedes-literature-2020/
```

It should include:

- `source_index.sqlite`
- `source_status.json`
- `source_receipt.json`
- `literature_enrichment_receipt.json`
- `gaps.json`
- raw OpenAlex cursor page JSON under `raw/literature/`
- PubMed and Unpaywall enrichment payloads preserved in SQLite `record_payloads`
- legal direct full text extracted into SQLite `literature_fulltext_units`

The existing mosquito fixture lane can remain in `artifacts/mosquito-v1/`.
Source commands should accept an artifact directory so the literature index can
be built and queried independently while development is underway.

## Discovery Sources

### OpenAlex

OpenAlex is the canonical discovery source. It provides stable work ids, DOI
metadata, publication dates, titles, abstract inverted indexes, authors,
venues, topics, open-access status, and external identifiers such as PMID and
PMCID when available.

Use cursor pagination instead of offset pagination for large runs. Save every
raw API page. The receipt must record the exact query filters, topic-search
results, selected topic ids, cursor mode, page size, page count, total count
reported by OpenAlex, and normalized record count.

The OpenAlex discovery stage has two subqueries:

1. Title or abstract query using `title_and_abstract.search:"Aedes aegypti"`.
2. Topic expansion query using exact or defensible OpenAlex topic ids or
   keywords discovered from the `/topics` API and work topic metadata.

The final canonical set is the deduplicated union of these subqueries. Every
record should store which inclusion paths matched: `title`, `abstract`,
`topic`, or a combination.

### PubMed

PubMed is an enrichment and coverage cross-check source, not the canonical
universe. Use NCBI E-utilities to search:

```text
"Aedes aegypti"[Title/Abstract] AND 2020/01/01:<run date>[pdat]
```

PubMed records should be matched to OpenAlex works by DOI, PMID, PMCID, or
normalized title when identifiers are missing. PubMed-only records become
coverage gaps unless the lane explicitly promotes them through the same
source-grade gates.

### Unpaywall

Unpaywall is the legal open-access resolver for DOI-bearing works. Query it for
each DOI when the work has a DOI. Preserve responses in `record_payloads` and
record:

- open-access status
- best open full-text URL
- license when available
- repository or publisher host
- whether the URL is downloadable or only a landing page

Do not fetch or store paywalled full text. Do not use Sci-Hub, LibGen, browser
cookies, institutional access, or scraped private copies.

## SQLite Shape

Use the existing `records` table for answer-grade evidence rows:

- one `literature` record per canonical paper
- title, abstract text when available, publication date, DOI, PMID, PMCID,
  journal or venue, authors, and open-access status in the text and payload
- inclusion paths showing whether the paper matched by title, abstract, topic,
  or more than one path
- source id `aedes_literature_openalex`
- provenance locator pointing to the saved OpenAlex raw page and work id

Use `record_payloads` for raw per-paper payloads:

- OpenAlex work JSON
- matched PubMed summary or abstract XML/JSON where available
- Unpaywall response where available
- full-text extraction metadata where available

Add a dedicated full-text table only if storing full-text chunks in
`record_payloads` makes queries too slow or too large. The likely shape is:

```sql
literature_fulltext_units(
  unit_id text primary key,
  record_id text not null,
  source text not null,
  unit_index integer not null,
  text text not null,
  url text,
  license text,
  provenance_json text not null
)
```

Full-text units are only source-grade when the full-text source is legally open
and the locator reaches the saved text or source URL.

## Full-Text Rule

For every canonical paper:

1. If OpenAlex or Unpaywall exposes a legal open full-text URL, fetch only from
   that URL or its declared open repository/publisher host.
2. Save the raw response or extracted text when terms and file type allow it.
3. Normalize full text into queryable units with provenance.
4. If the paper is closed, has no DOI, has no open URL, returns a landing page
   only, fails to download, or cannot be parsed, write a gap.

Closed full text is not a failed source lane. It is an explicit source gap for
that paper's full-text layer while the metadata and abstract remain sourced.

## Gaps

Gaps must be structured, not prose-only. Expected gap categories:

- `pubmed_unmatched`: PubMed record did not match a canonical OpenAlex work.
- `openalex_missing_abstract`: OpenAlex work has no abstract.
- `openalex_topic_search_empty`: no exact or defensible OpenAlex topic was
  available for `Aedes aegypti` at run time.
- `openalex_topic_candidate_rejected`: a candidate topic looked related but did
  not materially name `Aedes aegypti`.
- `missing_doi`: no DOI, so Unpaywall cannot be queried.
- `unpaywall_not_oa`: Unpaywall says the work is not open access.
- `unpaywall_no_fulltext_url`: work is open in metadata but no full-text URL is exposed.
- `fulltext_landing_page_only`: URL is inspectable but not direct full text.
- `fulltext_fetch_failed`: legal open URL failed during fetch.
- `fulltext_parse_failed`: downloaded full text could not be converted into text units.
- `pubmed_only_candidate`: PubMed found a possible paper outside the canonical OpenAlex set.

Each gap row must include source id, record id or external id, reason, locator,
and retrieved timestamp.

## CLI Behavior

The build command should add an explicit literature source flag, for example:

```bash
python3 scripts/build_source_index.py \
  --fixtures \
  --openalex-literature \
  --species "Aedes aegypti" \
  --from-date 2020-01-01 \
  --to-date 2026-05-23 \
  --work-type article \
  --include-topic-discovery \
  --page-size 200 \
  --delay-seconds 1
```

The query surface should work through existing commands:

```bash
python3 -m askinsects sources --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects summary --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects search literature "Wolbachia dengue"
python3 -m askinsects ask "what papers since 2020 discuss Wolbachia and Aedes aegypti?"
python3 -m askinsects sql "select source, lane, count(*) from records group by source, lane"
```

If the final CLI keeps a single default artifact directory, then the literature
lane must be merged into that default index and the source map must describe
the combined boundary. During development, a separate artifact directory is
acceptable because the source lane is large and rebuilds are expensive.

## Receipts And Status

`source_status.json` must include:

- `ok`
- source ids
- boundary string
- generated timestamp
- OpenAlex query filters
- OpenAlex topic search results and accepted topic ids
- reported total count
- normalized literature record count
- full-text unit count
- gap count
- raw artifact count
- whether the run completed all pages

`source_receipt.json` must include:

- exact API URLs or query params
- inclusion path counts for title, abstract, topic, and overlapping matches
- source versions or retrieved timestamps
- raw artifact paths
- cursor/page count
- DOI count
- PMID/PMCID count
- Unpaywall queried count
- open full-text count
- closed or inaccessible full-text count
- test and verification commands run

## Verification

Deterministic tests use fake OpenAlex, PubMed, and Unpaywall responses. They
must prove:

- OpenAlex cursor pagination continues until complete.
- A work with title, abstract, or accepted topic metadata for `Aedes aegypti`
  becomes a `literature` record.
- A work included only by a rejected broad or ambiguous topic candidate is
  excluded and recorded as a topic gap.
- Abstract inverted indexes are reconstructed into readable text.
- Raw per-paper payloads are stored in `record_payloads`.
- PubMed identifiers enrich matching OpenAlex works.
- Unpaywall open URLs create full-text metadata or units.
- Closed or missing full text creates structured gaps.
- The CLI can search and SQL-query literature records.
- The completion verifier requires the literature spec, plan, source map, tests,
  and deterministic fixture build.

Live verification after deterministic tests:

```bash
python3 scripts/build_source_index.py --fixtures --openalex-literature --species "Aedes aegypti" --from-date 2020-01-01 --to-date 2026-05-23 --work-type article --include-topic-discovery --page-size 200 --delay-seconds 1
python3 -m askinsects sources --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects summary --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects sql "select source, lane, count(*) as n from records group by source, lane" --artifact-dir artifacts/aedes-literature-2020
python3 -m askinsects search literature "Wolbachia dengue" --artifact-dir artifacts/aedes-literature-2020
```

The lane is not complete until the live receipt proves every canonical OpenAlex
page was fetched, every work was normalized or gapped, open full text was
attempted through legal sources, and the final SQLite database can answer
through `askinsects`.

## References

- OpenAlex works filters: `https://docs.openalex.org/api-entities/works/filter-works`
- OpenAlex works search: `https://docs.openalex.org/api-entities/works/search-works`
- NCBI E-utilities: `https://www.ncbi.nlm.nih.gov/books/NBK25499/`
- Unpaywall API: `https://unpaywall.org/products/api`
