from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from .answer import answer_question
from .builder import DEFAULT_ARTIFACT_DIR
from .hosted import CONFIG_PATH as HOSTED_CONFIG_PATH
from .hosted import HostedConfig, hosted_request, load_config, save_config
from .index import SourceIndex
from .voxels import read_voxel_value


def emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def cli_error(error: str, *, lane: str, artifact_dir: Path) -> dict[str, object]:
    return {
        "ok": False,
        "error": error,
        "answer": error,
        "evidence": [],
        "source_gap": {
            "lane": lane,
            "reason": f"The mosquito_v1 source index is missing or unavailable for lane '{lane}'.",
            "artifact_dir": artifact_dir.as_posix(),
        },
    }


def render_answer(payload: dict[str, object]) -> str:
    lines = [str(payload["answer"]), ""]
    evidence = payload.get("evidence") or []
    if evidence:
        lines.append("Evidence:")
        for item in evidence:
            provenance = item["provenance"]
            lines.append(f"- {item['title']} [{item['source']} {item['record_id']}]")
            lines.append(f"  locator: {provenance['locator']}")
    gap = payload.get("source_gap")
    if gap:
        lines.append("Source gap:")
        lines.append(f"- lane: {gap['lane']}")
        lines.append(f"- reason: {gap['reason']}")
    return "\n".join(lines)


def normalize_search_lane(lane: str) -> str:
    if lane == "papers":
        return "literature"
    if lane in {"fulltext", "full-text", "literature-fulltext"}:
        return "literature_fulltext"
    return lane


def indexed_sources(artifact_dir: Path) -> list[str]:
    status_path = artifact_dir / "source_status.json"
    if not status_path.exists():
        return ["mosquito_v1_fixtures"]
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["mosquito_v1_fixtures"]
    sources = payload.get("sources")
    if isinstance(sources, list) and all(isinstance(source, str) for source in sources):
        return sources
    source_id = payload.get("source_id")
    if isinstance(source_id, str):
        return [source_id]
    return ["mosquito_v1_fixtures"]


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def emit_hosted(method: str, path: str, payload: dict[str, object] | None = None, *, timeout: int = 120) -> dict[str, object]:
    result = hosted_request(load_config(), method, path, payload, timeout=timeout)
    emit(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ask-insects")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    configure = sub.add_parser("configure")
    configure.add_argument("--url", required=True)
    configure.add_argument("--token", required=True)

    setup = sub.add_parser("setup")
    setup.add_argument("--url", required=True)
    setup.add_argument("--token", required=True)

    health = sub.add_parser("health")
    health.add_argument("--hosted", action="store_true")

    summary = sub.add_parser("summary")
    summary.add_argument("--hosted", action="store_true")

    sources = sub.add_parser("sources")
    sources.add_argument("--hosted", action="store_true")

    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--limit", type=int, default=5)
    ask.add_argument("--json", action="store_true")
    ask.add_argument("--hosted", action="store_true")

    search = sub.add_parser("search")
    search.add_argument("lane")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--hosted", action="store_true")

    sql = sub.add_parser("sql")
    sql.add_argument("sql")
    sql.add_argument("--limit", type=int, default=100)
    sql.add_argument("--hosted", action="store_true")

    voxel = sub.add_parser("voxel")
    voxel.add_argument("record_id")
    voxel.add_argument("--x", type=int, required=True)
    voxel.add_argument("--y", type=int, required=True)
    voxel.add_argument("--z", type=int, required=True)

    ingest_inaturalist = sub.add_parser("ingest-inaturalist")
    ingest_inaturalist.add_argument("--hosted", action="store_true")
    ingest_inaturalist.add_argument("--species", action="append", default=[])
    ingest_inaturalist.add_argument("--place")
    ingest_inaturalist.add_argument("--observation-limit", type=int, default=10)
    ingest_inaturalist.add_argument("--page-size", type=int, default=200)
    ingest_inaturalist.add_argument("--delay-seconds", type=float, default=0.0)

    ingest_gbif = sub.add_parser("ingest-gbif")
    ingest_gbif.add_argument("--hosted", action="store_true")
    ingest_gbif.add_argument("--species", action="append", default=[])
    ingest_gbif.add_argument("--occurrence-limit", type=int, default=3)
    ingest_gbif.add_argument("--occurrence-page-size", type=int, default=300)
    ingest_gbif.add_argument("--occurrence-workers", type=int, default=1)
    ingest_gbif.add_argument("--delay-seconds", type=float, default=0.0)

    ingest_irmapper = sub.add_parser("ingest-irmapper")
    ingest_irmapper.add_argument("--hosted", action="store_true")
    ingest_irmapper.add_argument("--species", default="Aedes aegypti")

    ingest_public_health = sub.add_parser("ingest-public-health")
    ingest_public_health.add_argument("--hosted", action="store_true")
    ingest_public_health.add_argument("--source-url", action="append", default=[])

    ingest_paho_dengue_surveillance = sub.add_parser("ingest-paho-dengue-surveillance")
    ingest_paho_dengue_surveillance.add_argument("--hosted", action="store_true")
    ingest_paho_dengue_surveillance.add_argument("--report-url", action="append", default=[])
    ingest_paho_dengue_surveillance.add_argument("--dashboard-page", action="append", default=[])
    ingest_paho_dengue_surveillance.add_argument("--core-indicator-page", action="append", default=[])

    ingest_who_dengue_surveillance = sub.add_parser("ingest-who-dengue-surveillance")
    ingest_who_dengue_surveillance.add_argument("--hosted", action="store_true")
    ingest_who_dengue_surveillance.add_argument("--source-url", action="append", default=[])

    ingest_cdc_dengue_surveillance = sub.add_parser("ingest-cdc-dengue-surveillance")
    ingest_cdc_dengue_surveillance.add_argument("--hosted", action="store_true")
    ingest_cdc_dengue_surveillance.add_argument("--source-url", action="append", default=[])

    ingest_vectorbase_genomics = sub.add_parser("ingest-vectorbase-genomics")
    ingest_vectorbase_genomics.add_argument("--hosted", action="store_true")
    ingest_vectorbase_genomics.add_argument("--gff-url")
    ingest_vectorbase_genomics.add_argument("--protein-url")
    ingest_vectorbase_genomics.add_argument("--cds-url")
    ingest_vectorbase_genomics.add_argument("--transcript-url")
    ingest_vectorbase_genomics.add_argument("--go-url")
    ingest_vectorbase_genomics.add_argument("--codon-usage-url")
    ingest_vectorbase_genomics.add_argument("--id-events-url")
    ingest_vectorbase_genomics.add_argument("--ncbi-linkout-url")

    ingest_expression_omics = sub.add_parser("ingest-expression-omics")
    ingest_expression_omics.add_argument("--hosted", action="store_true")
    ingest_expression_omics.add_argument("--geo-limit", type=int, default=25)
    ingest_expression_omics.add_argument("--sra-limit", type=int, default=25)

    ingest_uniprot_proteins = sub.add_parser("ingest-uniprot-proteins")
    ingest_uniprot_proteins.add_argument("--hosted", action="store_true")
    ingest_uniprot_proteins.add_argument("--protein-limit", type=int, default=250)
    ingest_uniprot_proteins.add_argument("--proteome-limit", type=int, default=10)

    ingest_wolbachia_interventions = sub.add_parser("ingest-wolbachia-interventions")
    ingest_wolbachia_interventions.add_argument("--hosted", action="store_true")
    ingest_wolbachia_interventions.add_argument("--source-url", action="append", default=[])

    ingest_vectorbyte_traits = sub.add_parser("ingest-vectorbyte-traits")
    ingest_vectorbyte_traits.add_argument("--hosted", action="store_true")
    ingest_vectorbyte_traits.add_argument("--query", default="Aedes aegypti")
    ingest_vectorbyte_traits.add_argument("--dataset-limit", type=int, default=20)
    ingest_vectorbyte_traits.add_argument("--row-limit", type=int, default=5000)
    ingest_vectorbyte_traits.add_argument("--search-limit", type=int, default=50)

    ingest_mosquito_alert = sub.add_parser("ingest-mosquito-alert")
    ingest_mosquito_alert.add_argument("--hosted", action="store_true")
    ingest_mosquito_alert.add_argument("--occurrence-limit", type=int, default=1000)
    ingest_mosquito_alert.add_argument("--occurrence-page-size", type=int, default=300)

    ingest_vectornet_surveillance = sub.add_parser("ingest-vectornet-surveillance")
    ingest_vectornet_surveillance.add_argument("--hosted", action="store_true")
    ingest_vectornet_surveillance.add_argument("--species", default="Aedes aegypti")
    ingest_vectornet_surveillance.add_argument("--archive-url")
    ingest_vectornet_surveillance.add_argument("--max-records", type=int)

    ingest_dryad_behavior_videos = sub.add_parser("ingest-dryad-behavior-videos")
    ingest_dryad_behavior_videos.add_argument("--hosted", action="store_true")
    ingest_dryad_behavior_videos.add_argument("--doi", action="append", default=[])

    ingest_osf_flighttrackai_videos = sub.add_parser("ingest-osf-flighttrackai-videos")
    ingest_osf_flighttrackai_videos.add_argument("--hosted", action="store_true")

    ingest_zenodo_aedes_videos = sub.add_parser("ingest-zenodo-aedes-videos")
    ingest_zenodo_aedes_videos.add_argument("--hosted", action="store_true")
    ingest_zenodo_aedes_videos.add_argument("--query", default='"Aedes aegypti" (video OR movie OR mp4 OR tracking)')
    ingest_zenodo_aedes_videos.add_argument("--size", type=int, default=25)

    ingest_figshare_aedes_videos = sub.add_parser("ingest-figshare-aedes-videos")
    ingest_figshare_aedes_videos.add_argument("--hosted", action="store_true")
    ingest_figshare_aedes_videos.add_argument("--query", default="Aedes aegypti video")
    ingest_figshare_aedes_videos.add_argument("--page-size", type=int, default=25)

    ingest_mendeley_behavior_media = sub.add_parser("ingest-mendeley-behavior-media")
    ingest_mendeley_behavior_media.add_argument("--hosted", action="store_true")
    ingest_mendeley_behavior_media.add_argument("--dataset", action="append", default=[])

    ingest_pathogen_taxonomy = sub.add_parser("ingest-pathogen-taxonomy")
    ingest_pathogen_taxonomy.add_argument("--hosted", action="store_true")

    ingest_ncbi_biosamples = sub.add_parser("ingest-ncbi-biosamples")
    ingest_ncbi_biosamples.add_argument("--hosted", action="store_true")
    ingest_ncbi_biosamples.add_argument("--species", default="Aedes aegypti")
    ingest_ncbi_biosamples.add_argument("--limit", type=int, default=1000)
    ingest_ncbi_biosamples.add_argument("--page-size", type=int, default=200)
    ingest_ncbi_biosamples.add_argument("--delay-seconds", type=float, default=0.34)

    ingest_vector_competence_assays = sub.add_parser("ingest-vector-competence-assays")
    ingest_vector_competence_assays.add_argument("--hosted", action="store_true")

    ingest_resistance_markers = sub.add_parser("ingest-resistance-markers")
    ingest_resistance_markers.add_argument("--hosted", action="store_true")

    ingest_extracted_facts = sub.add_parser("ingest-extracted-facts")
    ingest_extracted_facts.add_argument("--hosted", action="store_true")
    ingest_extracted_facts.add_argument("--max-fulltext-units", type=int, default=5000)
    ingest_extracted_facts.add_argument("--discover-supplements", action="store_true")
    ingest_extracted_facts.add_argument("--download-supplements", action="store_true")
    ingest_extracted_facts.add_argument("--max-supplement-discovery-records", type=int, default=500)
    ingest_extracted_facts.add_argument("--max-supplement-files", type=int, default=100)
    ingest_extracted_facts.add_argument("--max-supplement-bytes", type=int, default=2_000_000)

    ingest_video_atoms = sub.add_parser("ingest-video-atoms")
    ingest_video_atoms.add_argument("--hosted", action="store_true")
    ingest_video_atoms.add_argument("--max-video-bytes", type=int, default=750_000_000)
    ingest_video_atoms.add_argument("--mirror-videos", action="store_true")
    ingest_video_atoms.add_argument("--generate-artifacts", action="store_true")
    ingest_video_atoms.add_argument("--discover-sources", action="store_true")
    ingest_video_atoms.add_argument("--allow-unclear-license", action="store_true")
    ingest_video_atoms.add_argument("--allowed-licenses")
    ingest_video_atoms.add_argument("--motion-table", action="append", default=[])
    ingest_video_atoms.add_argument("--max-discovery-results", type=int, default=1000)

    ingest_image_atoms = sub.add_parser("ingest-image-atoms")
    ingest_image_atoms.add_argument("--hosted", action="store_true")

    ingest_occurrence_ecology = sub.add_parser("ingest-occurrence-ecology")
    ingest_occurrence_ecology.add_argument("--hosted", action="store_true")

    args = parser.parse_args(argv)
    artifact_dir = Path(args.artifact_dir)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    db_path = artifact_dir / "source_index.sqlite"

    if args.command == "configure":
        save_config(HostedConfig(url=args.url, token=args.token), path=HOSTED_CONFIG_PATH)
        emit({"ok": True, "config_path": HOSTED_CONFIG_PATH.as_posix(), "url": args.url})
        return 0
    if args.command == "setup":
        config = HostedConfig(url=args.url, token=args.token)
        save_config(config, path=HOSTED_CONFIG_PATH)
        health_payload = hosted_request(config, "GET", "/health")
        payload = {
            "ok": bool(health_payload.get("ok")),
            "status": "ready" if health_payload.get("ok") else "needs_help",
            "config_path": HOSTED_CONFIG_PATH.as_posix(),
            "url": args.url,
        }
        if "record_count" in health_payload:
            payload["record_count"] = health_payload["record_count"]
        if "error" in health_payload:
            payload["error"] = health_payload["error"]
        emit(payload)
        return 0 if payload["ok"] else 2
    if args.command == "health":
        if args.hosted:
            payload = emit_hosted("GET", "/health")
            return 0 if payload.get("ok") else 2
        db_exists = db_path.exists()
        status_exists = (artifact_dir / "source_status.json").exists()
        emit({"ok": db_exists and status_exists, "db_exists": db_exists, "status_exists": status_exists})
        return 0
    if args.command == "summary":
        if args.hosted:
            payload = emit_hosted("GET", "/summary")
            return 0 if payload.get("ok", True) is not False else 2
        if not db_path.exists():
            emit(cli_error("missing mosquito_v1 source index", lane="mosquito_v1", artifact_dir=artifact_dir))
            return 2
        try:
            emit(index.summary())
        except sqlite3.Error as exc:
            emit(cli_error(str(exc), lane="mosquito_v1", artifact_dir=artifact_dir))
            return 2
        return 0
    if args.command == "sources":
        if args.hosted:
            payload = emit_hosted("GET", "/sources")
            return 0 if payload.get("ok", True) is not False else 2
        emit({"sources": indexed_sources(artifact_dir), "artifact_dir": artifact_dir.as_posix()})
        return 0
    if args.command == "ask":
        if args.hosted:
            payload = hosted_request(load_config(), "POST", "/ask", {"question": args.question, "limit": args.limit})
        else:
            try:
                payload = answer_question(args.question, artifact_dir=artifact_dir, limit=args.limit)
            except sqlite3.Error as exc:
                payload = cli_error(str(exc), lane="mosquito_v1", artifact_dir=artifact_dir)
            gap = payload.get("source_gap") or {}
            if not payload.get("ok") and isinstance(gap, dict) and "index has not been built" in str(gap.get("reason")):
                payload = cli_error(
                    "missing mosquito_v1 source index",
                    lane=str(gap.get("lane", "mosquito_v1")),
                    artifact_dir=artifact_dir,
                )
        if args.json:
            emit(payload)
        elif args.hosted and "answer" not in payload:
            emit(payload)
        else:
            print(render_answer(payload))
        return 0 if payload.get("ok") else 2
    if args.command == "search":
        if args.hosted:
            payload = emit_hosted("POST", "/search", {"lane": normalize_search_lane(args.lane), "query": args.query, "limit": args.limit})
            return 0 if payload.get("ok") else 2
        if not db_path.exists():
            emit(cli_error("missing mosquito_v1 source index", lane=args.lane, artifact_dir=artifact_dir))
            return 2
        lane = normalize_search_lane(args.lane)
        try:
            if lane == "literature_fulltext":
                rows = [record.to_row() for record in index.search_literature_fulltext(args.query, limit=args.limit)]
            else:
                rows = [record.to_row() for record in index.search(args.query, lane=lane, limit=args.limit)]
        except sqlite3.Error as exc:
            emit(cli_error(str(exc), lane=args.lane, artifact_dir=artifact_dir))
            return 2
        emit({"ok": True, "rows": rows})
        return 0
    if args.command == "sql":
        if args.hosted:
            payload = emit_hosted("POST", "/sql", {"sql": args.sql, "limit": args.limit})
            return 0 if payload.get("ok") else 2
        if not db_path.exists():
            emit(cli_error("missing mosquito_v1 source index", lane="sql", artifact_dir=artifact_dir))
            return 2
        try:
            emit({"ok": True, "rows": index.sql(args.sql, limit=args.limit)})
        except (sqlite3.Error, ValueError) as exc:
            emit(cli_error(str(exc), lane="sql", artifact_dir=artifact_dir))
            return 2
        return 0
    if args.command == "voxel":
        if not db_path.exists():
            emit(cli_error("missing mosquito_v1 source index", lane="neurobiology", artifact_dir=artifact_dir))
            return 2
        try:
            emit(read_voxel_value(index_path=db_path, record_id=args.record_id, x=args.x, y=args.y, z=args.z))
        except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
            emit(cli_error(str(exc), lane="neurobiology", artifact_dir=artifact_dir))
            return 2
        return 0
    if args.command == "ingest-inaturalist":
        if not args.hosted:
            from scripts.ingest_inaturalist_observations import ingest_inaturalist_observations

            payload = ingest_inaturalist_observations(
                artifact_dir=artifact_dir,
                species=args.species or ["Aedes aegypti"],
                place=args.place,
                observation_limit=args.observation_limit,
                page_size=args.page_size,
                delay_seconds=args.delay_seconds,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/inaturalist",
            {
                "species": args.species or ["Aedes aegypti"],
                "place": args.place,
                "observation_limit": args.observation_limit,
                "page_size": args.page_size,
                "delay_seconds": args.delay_seconds,
            },
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-gbif":
        if not args.hosted:
            emit({"ok": False, "error": "ingest-gbif currently requires --hosted; use scripts/build_source_index.py for local ingest"})
            return 2
        payload = emit_hosted(
            "POST",
            "/ingest/gbif",
            {
                "species": args.species or ["Aedes aegypti"],
                "occurrence_limit": args.occurrence_limit,
                "occurrence_page_size": args.occurrence_page_size,
                "occurrence_workers": args.occurrence_workers,
                "delay_seconds": args.delay_seconds,
            },
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-irmapper":
        if not args.hosted:
            from scripts.ingest_irmapper import ingest_irmapper

            payload = ingest_irmapper(artifact_dir=artifact_dir, species=args.species)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/irmapper",
            {"species": args.species},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-public-health":
        if not args.hosted:
            from scripts.ingest_public_health_guidance import ingest_public_health_guidance

            payload = ingest_public_health_guidance(artifact_dir=artifact_dir, source_urls=args.source_url)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/public-health",
            {"source_urls": args.source_url},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-paho-dengue-surveillance":
        if not args.hosted:
            from scripts.ingest_paho_dengue_surveillance import ingest_paho_dengue_surveillance

            payload = ingest_paho_dengue_surveillance(
                artifact_dir=artifact_dir,
                report_urls=args.report_url,
                dashboard_pages=args.dashboard_page if args.dashboard_page else None,
                core_indicator_pages=args.core_indicator_page if args.core_indicator_page else None,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/paho-dengue-surveillance",
            {
                "report_urls": args.report_url,
                "dashboard_pages": args.dashboard_page,
                "core_indicator_pages": args.core_indicator_page,
            },
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-who-dengue-surveillance":
        if not args.hosted:
            from scripts.ingest_who_dengue_surveillance import ingest_who_dengue_surveillance

            payload = ingest_who_dengue_surveillance(
                artifact_dir=artifact_dir,
                source_urls=args.source_url,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/who-dengue-surveillance",
            {"source_urls": args.source_url},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-cdc-dengue-surveillance":
        if not args.hosted:
            from scripts.ingest_cdc_dengue_surveillance import ingest_cdc_dengue_surveillance

            payload = ingest_cdc_dengue_surveillance(
                artifact_dir=artifact_dir,
                source_urls=args.source_url,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/cdc-dengue-surveillance",
            {"source_urls": args.source_url},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-vectorbase-genomics":
        file_urls = {
            key: value
            for key, value in {
                "gff": args.gff_url,
                "proteins": args.protein_url,
                "cds": args.cds_url,
                "transcript_sequences": args.transcript_url,
                "go": args.go_url,
                "codon_usage": args.codon_usage_url,
                "id_events": args.id_events_url,
                "ncbi_linkout": args.ncbi_linkout_url,
            }.items()
            if value
        }
        if not args.hosted:
            from scripts.ingest_vectorbase_genomics import ingest_vectorbase_genomics

            payload = ingest_vectorbase_genomics(artifact_dir=artifact_dir, file_urls=file_urls or None)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/vectorbase-genomics",
            {"file_urls": file_urls},
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-expression-omics":
        if not args.hosted:
            from scripts.ingest_expression_omics import ingest_expression_omics

            payload = ingest_expression_omics(
                artifact_dir=artifact_dir,
                geo_limit=args.geo_limit,
                sra_limit=args.sra_limit,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/expression-omics",
            {"geo_limit": args.geo_limit, "sra_limit": args.sra_limit},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-uniprot-proteins":
        if not args.hosted:
            from scripts.ingest_uniprot_proteins import ingest_uniprot_proteins

            payload = ingest_uniprot_proteins(
                artifact_dir=artifact_dir,
                protein_limit=args.protein_limit,
                proteome_limit=args.proteome_limit,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/uniprot-proteins",
            {"protein_limit": args.protein_limit, "proteome_limit": args.proteome_limit},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-wolbachia-interventions":
        if not args.hosted:
            from scripts.ingest_wolbachia_interventions import ingest_wolbachia_interventions

            payload = ingest_wolbachia_interventions(
                artifact_dir=artifact_dir,
                source_urls=args.source_url,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/wolbachia-interventions",
            {"source_urls": args.source_url},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-vectorbyte-traits":
        request_payload = {
            "query": args.query,
            "dataset_limit": args.dataset_limit,
            "row_limit": args.row_limit,
            "search_limit": args.search_limit,
        }
        if not args.hosted:
            from scripts.ingest_vectorbyte_traits import ingest_vectorbyte_traits

            payload = ingest_vectorbyte_traits(artifact_dir=artifact_dir, **request_payload)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/vectorbyte-traits",
            request_payload,
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-mosquito-alert":
        if not args.hosted:
            from scripts.ingest_mosquito_alert_observations import ingest_mosquito_alert_observations

            payload = ingest_mosquito_alert_observations(
                artifact_dir=artifact_dir,
                occurrence_limit=args.occurrence_limit,
                occurrence_page_size=args.occurrence_page_size,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/mosquito-alert",
            {
                "occurrence_limit": args.occurrence_limit,
                "occurrence_page_size": args.occurrence_page_size,
            },
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-vectornet-surveillance":
        request_payload = {
            "species": args.species,
            "archive_url": args.archive_url,
            "max_records": args.max_records,
        }
        if not args.hosted:
            from scripts.ingest_vectornet_surveillance import ingest_vectornet_surveillance

            payload = ingest_vectornet_surveillance(
                artifact_dir=artifact_dir,
                species=args.species,
                archive_url=args.archive_url,
                max_records=args.max_records,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/vectornet-surveillance",
            request_payload,
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-dryad-behavior-videos":
        if not args.hosted:
            from scripts.ingest_dryad_behavior_videos import ingest_dryad_behavior_videos

            payload = ingest_dryad_behavior_videos(
                artifact_dir=artifact_dir,
                dois=args.doi or None,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/dryad-behavior-videos",
            {"dois": args.doi},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-osf-flighttrackai-videos":
        if not args.hosted:
            from scripts.ingest_osf_flighttrackai_videos import ingest_osf_flighttrackai_videos

            payload = ingest_osf_flighttrackai_videos(artifact_dir=artifact_dir)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/osf-flighttrackai-videos",
            {},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-zenodo-aedes-videos":
        if not args.hosted:
            from scripts.ingest_zenodo_aedes_videos import ingest_zenodo_aedes_videos

            payload = ingest_zenodo_aedes_videos(
                artifact_dir=artifact_dir,
                query=args.query,
                size=args.size,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/zenodo-aedes-videos",
            {"query": args.query, "size": args.size},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-figshare-aedes-videos":
        if not args.hosted:
            from scripts.ingest_figshare_aedes_videos import ingest_figshare_aedes_videos

            payload = ingest_figshare_aedes_videos(
                artifact_dir=artifact_dir,
                query=args.query,
                page_size=args.page_size,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/figshare-aedes-videos",
            {"query": args.query, "page_size": args.page_size},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-mendeley-behavior-media":
        if not args.hosted:
            from scripts.ingest_mendeley_behavior_media import ingest_mendeley_behavior_media

            payload = ingest_mendeley_behavior_media(
                artifact_dir=artifact_dir,
                datasets=args.dataset or None,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/mendeley-behavior-media",
            {"datasets": args.dataset},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-pathogen-taxonomy":
        if not args.hosted:
            from scripts.ingest_pathogen_taxonomy import ingest_pathogen_taxonomy

            payload = ingest_pathogen_taxonomy(artifact_dir=artifact_dir)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/pathogen-taxonomy",
            {},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-ncbi-biosamples":
        if not args.hosted:
            from scripts.ingest_ncbi_biosamples import ingest_ncbi_biosamples

            payload = ingest_ncbi_biosamples(
                artifact_dir=artifact_dir,
                species=args.species,
                limit=args.limit,
                page_size=args.page_size,
                delay_seconds=args.delay_seconds,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/ncbi-biosamples",
            {
                "species": args.species,
                "limit": args.limit,
                "page_size": args.page_size,
                "delay_seconds": args.delay_seconds,
            },
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-vector-competence-assays":
        if not args.hosted:
            from scripts.ingest_vector_competence_assays import ingest_vector_competence_assays

            payload = ingest_vector_competence_assays(artifact_dir=artifact_dir)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/vector-competence-assays",
            {},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-resistance-markers":
        if not args.hosted:
            from scripts.ingest_resistance_markers import ingest_resistance_markers

            payload = ingest_resistance_markers(artifact_dir=artifact_dir)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/resistance-markers",
            {},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-extracted-facts":
        if not args.hosted:
            from scripts.ingest_extracted_facts import ingest_extracted_facts

            payload = ingest_extracted_facts(
                artifact_dir=artifact_dir,
                max_fulltext_units=args.max_fulltext_units,
                discover_supplements=args.discover_supplements,
                download_supplements=args.download_supplements,
                max_supplement_discovery_records=args.max_supplement_discovery_records,
                max_supplement_files=args.max_supplement_files,
                max_supplement_bytes=args.max_supplement_bytes,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/extracted-facts",
            {
                "max_fulltext_units": args.max_fulltext_units,
                "discover_supplements": args.discover_supplements,
                "download_supplements": args.download_supplements,
                "max_supplement_discovery_records": args.max_supplement_discovery_records,
                "max_supplement_files": args.max_supplement_files,
                "max_supplement_bytes": args.max_supplement_bytes,
            },
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-video-atoms":
        allowed_licenses = split_csv(args.allowed_licenses)
        if not args.hosted:
            from scripts.ingest_video_atoms import ingest_video_atoms

            payload = ingest_video_atoms(
                artifact_dir=artifact_dir,
                max_video_bytes=args.max_video_bytes,
                mirror_videos=args.mirror_videos,
                generate_artifacts=args.generate_artifacts,
                discover_sources=args.discover_sources,
                allow_unclear_license=args.allow_unclear_license,
                allowed_licenses=allowed_licenses or None,
                motion_table_paths=[Path(path) for path in args.motion_table],
                max_discovery_results=args.max_discovery_results,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/video-atoms",
            {
                "max_video_bytes": args.max_video_bytes,
                "mirror_videos": args.mirror_videos,
                "generate_artifacts": args.generate_artifacts,
                "discover_sources": args.discover_sources,
                "allow_unclear_license": args.allow_unclear_license,
                "allowed_licenses": allowed_licenses,
                "motion_table_paths": args.motion_table,
                "max_discovery_results": args.max_discovery_results,
            },
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-image-atoms":
        if not args.hosted:
            from scripts.ingest_image_atoms import ingest_image_atoms

            payload = ingest_image_atoms(artifact_dir=artifact_dir)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted("POST", "/ingest/image-atoms", {}, timeout=3600)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-occurrence-ecology":
        if not args.hosted:
            from scripts.ingest_occurrence_ecology import ingest_occurrence_ecology

            payload = ingest_occurrence_ecology(artifact_dir=artifact_dir)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/occurrence-ecology",
            {},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    parser.error("unknown command")
    return 1
