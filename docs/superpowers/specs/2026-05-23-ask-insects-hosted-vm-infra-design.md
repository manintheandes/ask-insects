# Ask Insects Hosted VM Infrastructure Design

## Purpose

Ask Insects should move from a laptop-only source plane to an Ask Monarch-style hosted source plane. The first hosted build includes both hosted ingest and hosted query.

The design target is deliberately close to Ask Monarch:

```text
local ask-insects CLI -> hosted Ask Insects API -> server-local SQLite indexes
```

The parsed SQLite database lives on the Google server filesystem, not primarily in Cloud Storage.

## Decision

Use a Google Compute Engine VM with a persistent boot disk.

The VM owns the runtime checkout:

```text
/home/josh/ask-insects
```

The VM owns the parsed artifacts:

```text
/home/josh/ask-insects/artifacts/mosquito-v1/source_index.sqlite
/home/josh/ask-insects/artifacts/mosquito-v1/source_status.json
/home/josh/ask-insects/artifacts/mosquito-v1/source_receipt.json
/home/josh/ask-insects/artifacts/mosquito-v1/gaps.json
/home/josh/ask-insects/artifacts/mosquito-v1/raw/inaturalist/
```

This matches the observed Ask Monarch health shape, where hosted source lanes report server-local database paths such as `/home/josh/ask-monarch/artifacts/.../source_index.sqlite`.

## Non-Goals

V1 does not need Kubernetes, Cloud Run, Cloud SQL, object-store-backed SQLite, multiple users, a web UI, or a scheduler. Those can come later.

V1 does not claim all insects are covered. The hosted lane remains mosquito-first, with `Aedes aegypti` as the first deep ingest target.

## Components

### Hosted API

The hosted API runs on the VM and exposes JSON endpoints:

- `GET /health`
- `GET /summary`
- `GET /sources`
- `POST /ask`
- `POST /search`
- `POST /sql`
- `POST /ingest/inaturalist`

Read endpoints answer from the server-local SQLite index. Ingest endpoints run the existing builder on the server, writing raw pages, receipts, gaps, and SQLite artifacts on the VM disk.

### Authentication

The API uses one bearer token in V1.

Every hosted request requires:

```text
Authorization: Bearer <token>
```

The token is supplied through an environment variable on the server and saved locally by the CLI config command.

### Local CLI

The local CLI keeps the local mode that already exists. It adds hosted mode:

```bash
python3 -m askinsects configure --url https://ask-insects.<ip>.sslip.io --token ...
python3 -m askinsects health --hosted
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil"
python3 -m askinsects ingest-inaturalist --hosted --species "Aedes aegypti" --observation-limit 5758 --page-size 200 --delay-seconds 1
```

The local CLI should make it obvious whether a command used local SQLite or the hosted API.

### Deployment Scripts

Repo scripts create and update the VM:

- create the VM if it does not exist
- install Python and required system packages
- copy or pull the Ask Insects repo to `/home/josh/ask-insects`
- install a systemd service for the API
- configure the bearer token
- open the needed firewall port
- run a hosted smoke ingest
- run hosted health and query checks

The first deployment can target the currently configured GCP project unless Josh chooses a different project before execution.

### Source Contract

The hosted lane must satisfy the `insectsource` gates:

- Mapped: source map and docs name the hosted plane and source lanes.
- Accessible: the VM can fetch iNaturalist and GBIF directly.
- Atomically queryable: server-local SQLite contains `records` rows with provenance and, after the payload-table fix lands on the infra branch, `record_payloads` rows for raw per-record payloads.
- Ask-surface wired: local `askinsects` CLI can ask, search, run read-only SQL, and trigger hosted ingest through the hosted API.

## Data Flow

Hosted ingest:

```text
CLI ingest command
  -> hosted API /ingest/inaturalist
  -> build_source_index.py on VM
  -> iNaturalist API pages
  -> raw JSON files on VM disk
  -> source_index.sqlite on VM disk
  -> source_receipt.json and gaps.json on VM disk
```

Hosted query:

```text
CLI ask/search/sql command
  -> hosted API
  -> server-local source_index.sqlite
  -> answer/search rows with provenance
  -> CLI output
```

## Failure Behavior

If hosted ingest fails, the server must not delete the previous working index without reporting a failure. A failed refresh should leave the previous verified `source_index.sqlite` available for hosted query when possible.

Health must report:

- whether the server is alive
- whether the SQLite index exists
- source counts
- gap count
- last ingest status
- artifact path on the server

## Test And Verification

The implementation must include local tests for:

- API auth failures
- hosted health response shape
- hosted ask/search/sql behavior using a temporary SQLite artifact dir
- hosted ingest calling the builder with requested species, limit, page size, and delay
- CLI hosted mode request construction

The hosted deployment is not complete until these pass:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
python3 -m askinsects health --hosted
python3 -m askinsects ingest-inaturalist --hosted --species "Aedes aegypti" --observation-limit 10 --page-size 10 --delay-seconds 0
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil"
python3 -m askinsects sql --hosted "select source, lane, count(*) as n from records group by source, lane"
```

## Open Deployment Defaults

Use these defaults unless Josh changes them before implementation:

- GCP project: current `gcloud` project, observed as `gen-lang-client-0407939408`
- VM name: `ask-insects`
- VM path: `/home/josh/ask-insects`
- first hosted boundary: `mosquito-v1`
- first deep species: `Aedes aegypti`

