# Aedes Paper Gap Fill Refresh

## Objective

Refresh Ask Insects Aedes paper coverage from 2020 onward, with supplementary
information represented as source-grade, queryable audit evidence.

## Scope

- Canonical paper lane: `aedes_literature_openalex`.
- Audit breadth lanes: `aedes_crossref_literature_audit`,
  `aedes_olfaction_literature`, `mosquito_repellent_literature`, and
  `mosquito_repellent_external_discovery`.
- Supplement evidence lane: `aedes_extracted_facts`.
- Structured promoted lanes: `aedes_resistance_table_rows` and
  `aedes_vector_competence_assays`.

## Refresh Result

Run date: 2026-05-27.

- Added 6 OpenAlex Aedes paper records from 2026-05-24 through 2026-05-27.
- Canonical Aedes paper count is now 10,689.
- Refreshed Crossref audit against 10,689 canonical papers: 199 candidates,
  with 6 Crossref-only metadata records.
- Refreshed PubMed olfaction audit: 183 candidates.
- Refreshed mosquito repellent metadata: 1,377 literature candidates.
- Refreshed external repellent discovery: 551 records across literature,
  datasets, and patents.
- Rebuilt supplement discovery across all 10,689 canonical papers with no
  discovery-record cap.
- Installed 41,512 `aedes_extracted_facts` records.
- Created 10,689 per-paper supplement audit atoms.
- Found 1,774 supplement manifests across 996 papers.
- Downloaded 234 public supplement files.
- Parsed 218 supported supplement files.
- Parsed 795 supported supplement rows.
- Promoted 84 parsed supplement rows into `aedes_resistance_table_rows`.

## Verification

Local artifact verification used:

```bash
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 health
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 sql "select source, count(*) as n from records where source in ('aedes_literature_openalex','aedes_extracted_facts','aedes_resistance_table_rows') group by source order by source" --limit 20
python3 -m askinsects --artifact-dir artifacts/mosquito-v1 ask "Show Aedes paper gap and supplement audit coverage since 2020." --json
```

Focused code verification used:

```bash
uv run python -m unittest tests.test_server.ServerTests.test_auth_required tests.test_server.ServerTests.test_read_endpoints_reject_missing_source_index_without_creating_db tests.test_server.ServerTests.test_read_endpoints_reject_empty_source_index tests.test_server.ServerTests.test_ingest_crossref_literature_audit_route_passes_options tests.test_cli_hosted.HostedCliTests.test_hosted_crossref_literature_audit_ingest_sends_options
```

## Hosted Guard

The hosted server now refuses read endpoints when the SQLite source index is
missing, empty, unreadable, or lacks the `records` table. This prevents hosted
queries from silently creating or accepting an empty SQLite file after a code
deploy without artifacts.

