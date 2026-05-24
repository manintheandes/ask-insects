# Aedes Video Atoms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and ship end-to-end Aedes aegypti video intelligence: every downloadable Aedes video is mirrored or verified, inspectable artifacts are generated, motion evidence is parsed into queryable rows, and video-source discovery expands across public repositories with structured gaps.

**Architecture:** Add a derived `aedes_video_atoms` source over existing media/video lanes plus newly discovered video candidates. Keep the source contract strict: candidate video records must be mapped, accessible or gap-recorded, atomically queryable, receipted, and wired to Ask Insects. Heavy binary work must be bounded by byte, duration, and license checks before download.

**Tech Stack:** Python standard library, SQLite through `SourceIndex`, existing `EvidenceRecord` and `Provenance`, `ffprobe` and `ffmpeg` when available, SHA-256 checksums, JSON manifests, `unittest`, hosted Ask Insects ingest route.

---

## File Structure

- Create `askinsects/sources/video_atoms.py`: derive verified video asset, artifact, frame, and motion records from existing video/media sources and source-discovery candidates.
- Create `scripts/ingest_video_atoms.py`: local additive ingest for `aedes_video_atoms`, including receipts and structured gaps.
- Modify `askinsects/cli.py`: add `ingest-video-atoms` with local and hosted modes.
- Modify `askinsects/server.py`: add `POST /ingest/video-atoms` using the existing source-staging pattern.
- Modify `askinsects/answer.py`: prefer `aedes_video_atoms` records for video, keyframe, thumbnail, preview, frame, trajectory, and motion questions.
- Create `tests/test_video_atoms_source.py`: source-unit coverage for mirroring, probing, artifacts, motion rows, discovery, and gaps.
- Create `tests/test_ingest_video_atoms.py`: additive ingest coverage.
- Modify `tests/test_cli_hosted.py`, `tests/test_server.py`, and `tests/test_answer.py`: CLI, hosted, and answer routing.
- Modify `config/source-map.yaml`, `config/mosquito-intelligence-coverage.json`, `docs/source-lanes.md`, `docs/querying-ask-insects.md`, `README.md`, and `scripts/verify_complete.py`: durable source-map, docs, and completion gate.

---

### Task 1: Video Candidate Inventory

**Files:**
- Create: `tests/test_video_atoms_source.py`
- Create: `askinsects/sources/video_atoms.py`

- [ ] **Step 1: Write failing inventory tests**

Add tests that create a temporary SQLite index with existing media records from `pmc_open_access_videos`, `dryad_aedes_behavior_videos`, `mendeley_aedes_behavior_media`, and `osf_flighttrackai_aedes_videos`. The test must assert that `build_video_atom_records()` emits one `media` record per video candidate with payload fields:

```python
{
    "atom_type": "video_asset",
    "source_video_record_id": "pmc:video:PMC123:video1.mp4",
    "source_dataset": "BiteOscope",
    "download_url": "https://example.org/video1.mp4",
    "license": "Creative Commons Attribution License",
    "verification_status": "candidate",
    "source_video_provenance": {"source_id": "pmc_open_access_videos"}
}
```

Run:

```bash
python3 -m unittest tests.test_video_atoms_source.VideoAtomsSourceTests.test_builds_video_candidates_from_existing_media -v
```

Expected: fail because `askinsects.sources.video_atoms` does not exist.

- [ ] **Step 2: Implement candidate selection**

Implement `build_video_atom_records(artifact_dir, *, retrieved_at=None, max_video_bytes=750_000_000, mirror_videos=False, generate_artifacts=False, discover_sources=False)` and select candidates from existing `media` rows whose source is one of:

```python
VIDEO_SOURCE_IDS = {
    "pmc_open_access_videos",
    "dryad_aedes_behavior_videos",
    "mendeley_aedes_behavior_media",
    "osf_flighttrackai_aedes_videos",
}
```

Only include records where `media_url`, `url`, title, or text indicates a video file or moving-image object: `.mp4`, `.mov`, `.avi`, `.m4v`, `.webm`, `video`, `movie`, `flight`, `tracking`, `high-speed`, `wingbeat`.

- [ ] **Step 3: Verify inventory tests pass**

Run:

```bash
python3 -m unittest tests.test_video_atoms_source.VideoAtomsSourceTests.test_builds_video_candidates_from_existing_media -v
```

Expected: pass, with records carrying source provenance and exact download locators.

---

### Task 2: Mirror Or Verify Every Downloadable Video

**Files:**
- Modify: `tests/test_video_atoms_source.py`
- Modify: `askinsects/sources/video_atoms.py`

- [ ] **Step 1: Write failing verification tests**

Add tests with injected fetch and probe functions. The test must prove:

- small downloadable video bytes are saved under `raw/video_atoms/assets/`
- SHA-256 checksum and byte size are recorded
- `ffprobe` metadata is normalized into duration, fps, resolution, and codec
- oversized files become structured gaps, not silent skips
- unclear licenses become structured gaps unless `allow_unclear_license=True`

Expected payload fields:

```python
{
    "atom_type": "video_asset",
    "verification_status": "mirrored",
    "sha256": "known-test-digest",
    "byte_size": 12345,
    "duration_seconds": 12.4,
    "fps": 30.0,
    "width": 1920,
    "height": 1080,
    "codec": "h264",
    "raw_asset_path": "raw/video_atoms/assets/video1_<digest>.mp4"
}
```

- [ ] **Step 2: Implement bounded mirroring**

Implement download logic that:

- rejects missing URLs with `video_download_url_missing`
- rejects unclear license with `video_license_unclear`
- rejects files over `max_video_bytes` with `video_too_large`
- writes accepted video bytes to `raw/video_atoms/assets/`
- computes SHA-256 from the mirrored bytes
- records raw paths relative to the artifact directory

- [ ] **Step 3: Implement media probing**

Implement `probe_video_file(path)` using `ffprobe` when available:

```bash
ffprobe -v error -show_streams -show_format -of json <path>
```

If `ffprobe` is missing or fails, keep the mirrored asset record and add a gap with reason `video_probe_failed` or `video_probe_tool_missing`.

- [ ] **Step 4: Verify verification tests pass**

Run:

```bash
python3 -m unittest tests.test_video_atoms_source.VideoAtomsSourceTests.test_mirrors_and_probes_downloadable_videos -v
python3 -m unittest tests.test_video_atoms_source.VideoAtomsSourceTests.test_records_video_gaps_for_large_or_unclear_assets -v
```

Expected: both pass.

---

### Task 3: Inspectable Artifacts

**Files:**
- Modify: `tests/test_video_atoms_source.py`
- Modify: `askinsects/sources/video_atoms.py`

- [ ] **Step 1: Write failing artifact tests**

Add a test with an injected artifact generator that returns:

```python
{
    "thumbnail_path": "raw/video_atoms/artifacts/video1/thumbnail.jpg",
    "keyframe_paths": [
        "raw/video_atoms/artifacts/video1/keyframe_000001.jpg",
        "raw/video_atoms/artifacts/video1/keyframe_000150.jpg"
    ],
    "preview_clip_path": "raw/video_atoms/artifacts/video1/preview.mp4",
    "frame_manifest_path": "raw/video_atoms/artifacts/video1/frames.json"
}
```

Assert that Ask Insects gets queryable `media` records for `video_thumbnail`, `video_keyframe`, `video_preview_clip`, and `video_frame_manifest`, all linked to the source video asset.

- [ ] **Step 2: Implement artifact generation**

Implement `generate_video_artifacts(asset_path, output_dir, *, max_keyframes=12, preview_seconds=8)` using `ffmpeg` when available:

- thumbnail at 1 second or first available frame
- keyframes at evenly spaced timestamps
- preview clip capped by `preview_seconds`
- `frames.json` manifest with frame index, timestamp, artifact path, source asset, and probe metadata

If `ffmpeg` is missing or fails, keep the asset record and add `video_artifact_generation_failed`.

- [ ] **Step 3: Verify artifact tests pass**

Run:

```bash
python3 -m unittest tests.test_video_atoms_source.VideoAtomsSourceTests.test_generates_inspectable_video_artifacts -v
```

Expected: pass.

---

### Task 4: Motion And Trajectory Rows

**Files:**
- Modify: `tests/test_video_atoms_source.py`
- Modify: `askinsects/sources/video_atoms.py`

- [ ] **Step 1: Write failing motion-row tests**

Create fixture rows from existing trajectory/table-like files:

```csv
video_id,track_id,frame,time_seconds,x,y,behavior,sex,life_stage,assay,stimulus,arena,confidence
video1,track-1,150,5.0,122.4,93.1,host seeking,female,adult,flight assay,CO2,wind tunnel,source_table
```

Assert that each row becomes a queryable `behavior` record with payload fields:

```python
{
    "atom_type": "video_motion_row",
    "source_video_record_id": "video1",
    "track_id": "track-1",
    "frame": 150,
    "time_seconds": 5.0,
    "x": 122.4,
    "y": 93.1,
    "behavior_type": "host seeking",
    "sex": "female",
    "life_stage": "adult",
    "assay": "flight assay",
    "stimulus": "CO2",
    "arena": "wind tunnel",
    "confidence": "source_table"
}
```

- [ ] **Step 2: Implement trajectory/table parser**

Start with existing table-like records and raw manifests from Mendeley, Dryad, and OSF. Parse CSV, TSV, and XLSX files where headers contain any of:

```python
{"video", "track", "frame", "time", "x", "y", "behavior", "sex", "life stage", "assay", "stimulus", "arena"}
```

Map each row to a `behavior` record with source file provenance. Do not infer coordinates from videos yet. If a file looks relevant but cannot be parsed, record `video_motion_table_parse_failed`.

- [ ] **Step 3: Verify motion-row tests pass**

Run:

```bash
python3 -m unittest tests.test_video_atoms_source.VideoAtomsSourceTests.test_parses_motion_rows_from_existing_tables -v
```

Expected: pass.

---

### Task 5: Expanded Source Discovery

**Files:**
- Modify: `tests/test_video_atoms_source.py`
- Modify: `askinsects/sources/video_atoms.py`
- Modify: `config/source-map.yaml`

- [ ] **Step 1: Write failing discovery tests**

Use injected discovery clients for PMC OA, Dryad, Mendeley, OSF, Zenodo, Figshare, and institutional repositories. The test must prove every discovered candidate becomes either a video candidate record or a structured gap.

Expected gap reasons:

```python
[
    "video_discovery_fetch_failed",
    "video_discovery_no_download_url",
    "video_discovery_license_unclear",
    "video_discovery_not_aedes_scope",
    "video_discovery_unsupported_repository"
]
```

- [ ] **Step 2: Implement discovery interfaces**

Implement small, testable discovery functions:

- `discover_pmc_oa_videos()`
- `discover_dryad_videos()`
- `discover_mendeley_videos()`
- `discover_osf_videos()`
- `discover_zenodo_videos()`
- `discover_figshare_videos()`
- `discover_institutional_repository_videos()`

Each function returns normalized dictionaries with title, download URL, repository, source URL, license, size if known, linked paper/dataset if known, and species-scope evidence.

- [ ] **Step 3: Keep discovery bounded**

Add limits:

- `max_discovery_results`
- `max_repository_pages`
- `max_video_bytes`
- `allowed_licenses`

Record a gap when a bound is hit.

- [ ] **Step 4: Verify discovery tests pass**

Run:

```bash
python3 -m unittest tests.test_video_atoms_source.VideoAtomsSourceTests.test_discovers_or_gaps_external_video_candidates -v
```

Expected: pass.

---

### Task 6: Local And Hosted Ingest

**Files:**
- Create: `scripts/ingest_video_atoms.py`
- Create: `tests/test_ingest_video_atoms.py`
- Modify: `askinsects/cli.py`
- Modify: `askinsects/server.py`
- Modify: `tests/test_cli_hosted.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write failing ingest tests**

Test that local ingest:

- preserves unrelated sources
- deletes and replaces only `aedes_video_atoms`
- updates `source_status.json`, `source_receipt.json`, and `gaps.json`
- reports asset, artifact, motion-row, discovery, and gap counts

- [ ] **Step 2: Implement local ingest**

Implement:

```bash
python3 scripts/ingest_video_atoms.py --artifact-dir artifacts/mosquito-v1 --max-video-bytes 750000000
```

Output JSON must include:

```json
{
  "ok": true,
  "source": "aedes_video_atoms",
  "video_asset_count": 0,
  "mirrored_video_count": 0,
  "verified_video_count": 0,
  "artifact_count": 0,
  "motion_row_count": 0,
  "discovery_candidate_count": 0,
  "gap_count": 0
}
```

- [ ] **Step 3: Wire CLI and hosted route**

Add:

```bash
python3 -m askinsects ingest-video-atoms
python3 -m askinsects ingest-video-atoms --hosted
```

Hosted route:

```http
POST /ingest/video-atoms
```

The route must use source-scoped activation and preserve all unrelated hosted sources.

- [ ] **Step 4: Verify ingest tests pass**

Run:

```bash
python3 -m unittest tests.test_ingest_video_atoms -v
python3 -m unittest tests.test_cli_hosted.HostedCliTests.test_hosted_video_atoms_ingest_sends_options -v
python3 -m unittest tests.test_server.ServerTests.test_ingest_video_atoms_adds_records_without_removing_existing_sources -v
```

Expected: all pass.

---

### Task 7: Ask Surface And Documentation

**Files:**
- Modify: `askinsects/answer.py`
- Modify: `tests/test_answer.py`
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `config/mosquito-intelligence-coverage.json`
- Modify: `scripts/verify_complete.py`

- [ ] **Step 1: Write failing answer-routing tests**

Add tests for:

```text
show Aedes aegypti video keyframes
show Aedes aegypti flight tracking videos
what motion rows exist for host seeking videos?
show Aedes aegypti preview clips
```

Expected: fail until `aedes_video_atoms` is preferred for video artifact and motion-row questions.

- [ ] **Step 2: Implement answer routing**

Prefer `aedes_video_atoms` for questions containing `video`, `movie`, `keyframe`, `thumbnail`, `preview`, `frame`, `motion`, `trajectory`, `tracking`, `fps`, `codec`, `duration`, or `resolution`.

- [ ] **Step 3: Update docs and completion gate**

Document `aedes_video_atoms` in README, source lanes, querying docs, source map, coverage ledger, and `verify_complete.py`. The docs must state:

- manifest-only video records are not enough
- mirrored or verified videos carry checksums and media metadata
- inspectable artifacts are queryable
- motion rows are source-table-derived until computer-vision tracking is explicitly added
- unavailable, too-large, or unclear-license videos are structured gaps

- [ ] **Step 4: Verify docs and answer tests pass**

Run:

```bash
python3 -m unittest tests.test_answer -v
python3 scripts/verify_complete.py
```

Expected: pass.

---

### Task 8: Real Hosted Run And Completion Evidence

**Files:**
- All changed files from Tasks 1 through 7

- [ ] **Step 1: Run focused tests**

Run:

```bash
python3 -m unittest tests.test_video_atoms_source -v
python3 -m unittest tests.test_ingest_video_atoms -v
python3 -m unittest tests.test_cli_hosted -v
python3 -m unittest tests.test_server -v
python3 -m unittest tests.test_answer -v
```

Expected: all pass.

- [ ] **Step 2: Run full verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
```

Expected: all tests pass and `verify_complete ok`.

- [ ] **Step 3: Deploy and run hosted ingest**

Run:

```bash
git push origin main
ASK_INSECTS_TOKEN="$(python3 - <<'PY'
from askinsects.hosted import load_config
print(load_config().token)
PY
)" scripts/deploy_gce_app.sh
python3 -m askinsects ingest-video-atoms --hosted --max-video-bytes 750000000
```

Expected: hosted JSON reports nonzero `video_asset_count`, plus structured gaps where appropriate.

- [ ] **Step 4: Prove hosted queryability**

Run:

```bash
python3 -m askinsects health --hosted
python3 -m askinsects sql --hosted "select source,lane,count(*) as n from records where source='aedes_video_atoms' group by source,lane order by lane" --limit 20
python3 -m askinsects ask --hosted "show Aedes aegypti video keyframes" --json --limit 5
python3 -m askinsects ask --hosted "show Aedes aegypti flight tracking motion rows" --json --limit 5
```

Expected: hosted health is ok, `aedes_video_atoms` appears in sources, and video questions return provenance-backed records or explicit video gaps.

- [ ] **Step 5: Commit final work**

Stage only intended files:

```bash
git add askinsects/sources/video_atoms.py scripts/ingest_video_atoms.py tests/test_video_atoms_source.py tests/test_ingest_video_atoms.py tests/test_cli_hosted.py tests/test_server.py tests/test_answer.py askinsects/cli.py askinsects/server.py askinsects/answer.py README.md docs/source-lanes.md docs/querying-ask-insects.md config/source-map.yaml config/mosquito-intelligence-coverage.json scripts/verify_complete.py docs/superpowers/plans/2026-05-24-aedes-video-atoms.md
git commit -m "feat: add Aedes video atoms lane"
git push origin main
```

Expected: `main` contains an end-to-end, queryable video-intelligence lane.

---

## Completion Definition

This goal is not complete until Ask Insects can answer from hosted `aedes_video_atoms` records with provenance for:

- mirrored or verified downloadable videos
- checksums, byte sizes, duration, fps, resolution, codec, source dataset or paper, license, and exact locator
- thumbnails, keyframes, preview clips, and frame manifests
- source-table-derived motion and trajectory rows
- discovery candidates from PMC OA, Dryad, Mendeley, OSF, Zenodo, Figshare, institutional repositories, and paper supplements
- structured gaps for too-large, inaccessible, unclear-license, unparseable, or out-of-scope videos

The global mosquito intelligence goal remains open after this plan unless all other non-video domains are also complete.
