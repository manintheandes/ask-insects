# Aedes OSF FlightTrackAI Video Lane Design

## Goal

Close the explicit OSF video gap for the Aedes-first Ask Insects source plane by indexing the public OSF FlightTrackAI project at project, folder, and file-manifest grain.

## Source Boundary

- Source id: `osf_flighttrackai_aedes_videos`
- Public project: OSF `cx762`
- Boundary: FlightTrackAI `Aedes aegypti` project metadata, OSF storage folders, processed and unprocessed MP4 files, executable bundles, installation instructions, and trained mosquito model metadata.
- Binary policy: save OSF JSON manifests and download locators by default. Do not mirror multi-gigabyte binaries unless a future plan explicitly requires storage, checksums, and frame or waveform parsing.

## Query Contract

- `media` records represent video files with `media_url` set to the OSF download URL.
- `behavior` records represent the project, folders, software, model, and instruction files.
- Every record keeps `species`, source id, source URL, raw manifest locator, retrieved timestamp, and the raw OSF item payload in SQLite.
- The source is source-grade at manifest/file level, not frame-level video decoding.

## Implementation

- `askinsects/sources/osf_flighttrackai_videos.py` fetches OSF node, provider, and recursive `osfstorage` manifests.
- `scripts/ingest_osf_flighttrackai_videos.py` replaces only `osf_flighttrackai_aedes_videos` rows, preserves existing sources, writes receipts, and deduplicates source gaps.
- `python3 -m askinsects ingest-osf-flighttrackai-videos` performs local ingest.
- `python3 -m askinsects ingest-osf-flighttrackai-videos --hosted` calls hosted `/ingest/osf-flighttrackai-videos`.

## Verification

- Unit tests cover OSF manifest normalization, gap recording, local ingest preservation, hosted CLI request wiring, hosted server ingest, and answer priority for OSF FlightTrackAI questions.
- `python3 scripts/verify_complete.py` requires the lane docs, source map, parser, ingest script, and tests.
