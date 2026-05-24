# Aedes Mendeley Behavior And Media Lane Design

## Goal

Add a source-grade Mendeley Data lane for public `Aedes aegypti` behavior, flight, hearing, mating, and locomotion datasets. The lane must keep the world-class push focused on `Aedes aegypti`: comparison taxa may appear inside a dataset, but a dataset is in scope only when `Aedes aegypti` is materially present in the title, abstract, topic, or dataset description.

## Source Boundary

Source id: `mendeley_aedes_behavior_media`

Default datasets:

- `10.17632/6gvs94p6r2.1`: high-speed video, sound files, and behavior data for yellow fever mosquito mate location and recognition.
- `10.17632/g79w8wxpr7.2`: raw and analysed data for male `Aedes aegypti` and `Aedes albopictus` hearing-system recognition of conspecific female flight tones.
- `10.17632/sg5rrvdzvg.1`: video-analysis data for `Aedes aegypti` and `Ae. japonicus` locomotory behavior under different temperature regimes.

The lane uses the public Mendeley Data API pages:

- `/public-api/datasets/{dataset_id}/snapshot/{version}`
- `/public-api/datasets/{dataset_id}/folders/{version}`
- `/public-api/datasets/{dataset_id}/files?folder_id={folder_id}&version={version}`

## Atomic Query Grain

- One `behavior` record per dataset snapshot.
- One `behavior` record per folder in the dataset manifest.
- One `media` record per file that is video, audio, or archive-like.
- One `behavior` record per non-media file such as spreadsheet, source data, README, or code.

Each file record must preserve filename, folder path, size, content type, SHA-256 hash when supplied, download URL, view URL, dataset DOI, dataset title, behavior labels, license, and raw manifest locator.

## Source Contract

- Mapped: `config/source-map.yaml` declares the lane, query plane, boundary, API base, ingest script, and lanes.
- Accessible: the ingest fetches public snapshot, folder, and file manifest JSON from Mendeley Data.
- Atomically queryable: SQLite records expose dataset, folder, and file atoms with `record_payloads`.
- Receipted: `source_status.json`, `source_receipt.json`, and `gaps.json` include Mendeley lane status and gaps.
- Ask surface wired: `ask-insects ask/search` can surface Mendeley behavior and media records, and Mendeley-specific questions prefer this lane.

## Explicit Limits

This lane indexes manifests and public download locators. It does not mirror multi-gigabyte binaries by default and does not decode video frames or spreadsheet tables yet. Those are follow-on Aedes behavior deep-parse tasks.
