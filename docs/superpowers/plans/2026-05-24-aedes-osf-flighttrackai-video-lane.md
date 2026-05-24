# Aedes OSF FlightTrackAI Video Lane Plan

## Checklist

- [x] Map OSF project `cx762` as source id `osf_flighttrackai_aedes_videos`.
- [x] Add a parser for OSF node, provider, folder, file, and pagination manifests.
- [x] Normalize project/folder/software/model/instruction items as `behavior`.
- [x] Normalize MP4 files as `media` with OSF download locators.
- [x] Add local ingest that refreshes only the OSF FlightTrackAI source.
- [x] Wire CLI and hosted API ingest.
- [x] Wire answer search and source priority for OSF FlightTrackAI questions.
- [x] Update source map, README, source-lane docs, and coverage ledger.
- [x] Add verifier requirements for the parser, ingest, tests, spec, plan, source map, and docs.
- [ ] Run real local ingest and query proof.
- [ ] Run full unit suite and `python3 scripts/verify_complete.py`.
- [ ] Deploy, run hosted ingest, verify hosted query proof, commit, and push.

## Completion Evidence

The lane is complete for this slice when local and hosted Ask Insects can answer `show OSF FlightTrackAI Aedes aegypti videos` with media records from `osf_flighttrackai_aedes_videos`, each carrying a download URL and provenance to saved OSF JSON manifests.
