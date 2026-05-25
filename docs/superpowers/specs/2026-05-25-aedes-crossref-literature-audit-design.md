# Aedes Crossref Literature Audit Design

## Goal

Add a source-grade Crossref audit lane for `Aedes aegypti` literature since 2020 so Ask Insects can reconcile publisher DOI/member metadata against the existing OpenAlex and PubMed literature lanes.

## Boundary

The lane covers Crossref `/works` results where Crossref metadata materially names `Aedes aegypti` or `Ae. aegypti` in title, abstract, subject, or container metadata, with `from-pub-date=2020-01-01`.

It does not replace the canonical `aedes_literature_openalex` corpus, scrape publisher pages, or claim legal full text. It produces audit atoms:

- one Crossref candidate per record
- DOI, title, publisher, container title, issued date, type, subjects, URL, Crossref member, reference count, and license links when supplied
- `coverage_status` showing whether an existing Ask Insects literature row already matches by DOI or normalized title
- structured gaps for failed fetches, no candidates, limit-applied frontiers, and missing canonical literature rows

## Data Flow

1. Fetch bounded Crossref pages using `query.bibliographic=Aedes aegypti`, publication-date filter, cursor pagination, and `select` fields.
2. Save raw page JSON under `artifacts/mosquito-v1/raw/aedes_crossref_literature_audit/`.
3. Filter records to material Aedes scope using source metadata, not search terms alone.
4. Compare each candidate against current literature rows, excluding the Crossref lane itself.
5. Replace only `aedes_crossref_literature_audit` rows after a successful refresh.
6. Update source status, receipt, and gaps without removing other source lanes.

## Ask Surface

Add `ingest-crossref-literature-audit` locally and hosted. Literature and source-coverage questions mentioning Crossref, publisher metadata, DOI audit, missing DOI, or literature reconciliation should be able to return this lane.

## Verification

Tests cover source parsing, preservation on failed refresh, CLI/hosted routing, server endpoint wiring, answer preference, source-map/doc coverage, and the repo completion gate.
