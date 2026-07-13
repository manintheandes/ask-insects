from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from .answer import answer_question
from .builder import DEFAULT_ARTIFACT_DIR
from .hosted import CONFIG_PATH as HOSTED_CONFIG_PATH
from .hosted import HostedConfig, hosted_request, load_config, save_config
from .sources.extracted_facts import DEFAULT_MAX_SUPPLEMENT_BYTES
from .sources.video_atoms import DISCOVERY_REPOSITORIES
from .sources.zenodo_aedes_videos import DEFAULT_ZENODO_SIZE
from .sources.figshare_aedes_videos import DEFAULT_FIGSHARE_PAGE_SIZE
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
    if payload.get("answer_shape") == "repellency_comparison":
        claim = payload.get("claim")
        if isinstance(claim, dict):
            lines.append(f"Claim status: {claim.get('status', 'unknown')}")
            reasons = claim.get("reasons")
            if isinstance(reasons, list) and reasons:
                for reason in reasons:
                    if isinstance(reason, dict):
                        lines.append(f"- {reason.get('message', reason.get('code', 'unspecified reason'))}")
        coverage = payload.get("coverage")
        if isinstance(coverage, dict):
            lines.append("")
            lines.append(
                "Coverage: "
                f"{coverage.get('deduplicated_papers', 0)} deduplicated paper(s), "
                f"{coverage.get('papers_with_depth_outcome', 0)} depth outcome(s), "
                f"{coverage.get('structured_assay_facts', 0)} structured assay fact(s), "
                f"{coverage.get('unresolved_source_gaps', 0)} unresolved source gap(s)."
            )
        comparison = payload.get("comparison")
        if isinstance(comparison, dict):
            rows = comparison.get("rows")
            if isinstance(rows, list) and rows:
                lines.extend(("", "Comparison rows:"))
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    dimensions = []
                    for label, key in (
                        ("compound", "compounds"),
                        ("exposure", "exposure_modes"),
                        ("assay", "assays"),
                        ("endpoint", "endpoints"),
                        ("dose", "dose"),
                        ("outcome", "outcome"),
                        ("duration", "duration"),
                    ):
                        value = row.get(key)
                        if isinstance(value, list):
                            value = ", ".join(str(item) for item in value)
                        if value:
                            dimensions.append(f"{label}={value}")
                    row_title = row.get("paper_title") or row.get("title") or row.get("record_id", "assay fact")
                    lines.append(f"- {row_title}: " + "; ".join(dimensions))
        lines.append("")
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

    setup_agent = sub.add_parser("setup-agent")
    setup_agent.add_argument("--destination")

    _LOCAL_HELP = "Dev-only escape: query the LOCAL index instead of the hosted plane (warns; results may be empty/stale)."

    health = sub.add_parser("health")
    health.add_argument("--hosted", action="store_true", help="(default) query the hosted plane")
    health.add_argument("--local", action="store_true", help=_LOCAL_HELP)

    summary = sub.add_parser("summary")
    summary.add_argument("--hosted", action="store_true", help="(default) query the hosted plane")
    summary.add_argument("--local", action="store_true", help=_LOCAL_HELP)

    sources = sub.add_parser("sources")
    sources.add_argument("--hosted", action="store_true", help="(default) query the hosted plane")
    sources.add_argument("--local", action="store_true", help=_LOCAL_HELP)

    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--limit", type=int, default=5)
    ask.add_argument("--json", action="store_true")
    ask.add_argument("--hosted", action="store_true", help="(default) query the hosted plane")
    ask.add_argument("--local", action="store_true", help=_LOCAL_HELP)

    search = sub.add_parser("search")
    search.add_argument("lane")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--hosted", action="store_true", help="(default) query the hosted plane")
    search.add_argument("--local", action="store_true", help=_LOCAL_HELP)

    sql = sub.add_parser("sql")
    sql.add_argument("sql")
    sql.add_argument("--limit", type=int, default=100)
    sql.add_argument("--hosted", action="store_true", help="(default) query the hosted plane")
    sql.add_argument("--local", action="store_true", help=_LOCAL_HELP)

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

    ingest_drosophila_suzukii = sub.add_parser("ingest-drosophila-suzukii")
    ingest_drosophila_suzukii.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii.add_argument("--gbif-occurrence-limit", type=int, default=100)
    ingest_drosophila_suzukii.add_argument("--inaturalist-observation-limit", type=int, default=100)
    ingest_drosophila_suzukii.add_argument("--literature-max-works", type=int, default=100)
    ingest_drosophila_suzukii.add_argument("--bold-limit", type=int, default=100)
    ingest_drosophila_suzukii.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_deep = sub.add_parser("ingest-drosophila-suzukii-deep-sources")
    ingest_drosophila_suzukii_deep.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_deep.add_argument("--ncbi-limit", type=int, default=50)
    ingest_drosophila_suzukii_deep.add_argument("--protein-limit", type=int, default=100)
    ingest_drosophila_suzukii_deep.add_argument("--proteome-limit", type=int, default=10)
    ingest_drosophila_suzukii_deep.add_argument("--repository-limit", type=int, default=50)
    ingest_drosophila_suzukii_deep.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_genome_files = sub.add_parser("ingest-drosophila-suzukii-genome-files")
    ingest_drosophila_suzukii_genome_files.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_genome_files.add_argument("--assembly-accession", default="GCF_043229965.1")
    ingest_drosophila_suzukii_genome_files.add_argument("--max-download-bytes", type=int, default=100_000_000)
    ingest_drosophila_suzukii_genome_files.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_extracted = sub.add_parser("ingest-drosophila-suzukii-extracted-facts")
    ingest_drosophila_suzukii_extracted.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_extracted.add_argument("--max-fulltext-units", type=int, default=5000)
    ingest_drosophila_suzukii_extracted.add_argument("--discover-supplements", action="store_true")
    ingest_drosophila_suzukii_extracted.add_argument("--download-supplements", action="store_true")
    ingest_drosophila_suzukii_extracted.add_argument("--max-supplement-discovery-records", type=int, default=500)
    ingest_drosophila_suzukii_extracted.add_argument("--max-repository-supplement-discovery-records", type=int, default=100)
    ingest_drosophila_suzukii_extracted.add_argument("--max-supplement-files", type=int, default=100)
    ingest_drosophila_suzukii_extracted.add_argument("--max-supplement-bytes", type=int, default=DEFAULT_MAX_SUPPLEMENT_BYTES)
    ingest_drosophila_suzukii_extracted.add_argument("--max-pdf-supplement-files", type=int, default=10)
    ingest_drosophila_suzukii_extracted.add_argument("--source-record-id", action="append", default=[])
    ingest_drosophila_suzukii_extracted.add_argument("--merge-existing", action="store_true")
    ingest_drosophila_suzukii_extracted.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_fulltext = sub.add_parser("ingest-drosophila-suzukii-literature-fulltext")
    ingest_drosophila_suzukii_fulltext.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_fulltext.add_argument("--email")
    ingest_drosophila_suzukii_fulltext.add_argument("--limit", type=int, default=25)
    ingest_drosophila_suzukii_fulltext.add_argument("--delay-seconds", type=float, default=0.0)
    ingest_drosophila_suzukii_fulltext.add_argument("--max-fulltext-bytes", type=int, default=60_000_000)
    ingest_drosophila_suzukii_fulltext.add_argument("--unpaywall", action="store_true")
    ingest_drosophila_suzukii_fulltext.add_argument("--no-resume", dest="resume", action="store_false", default=True)

    ingest_drosophila_suzukii_pubmed = sub.add_parser("ingest-drosophila-suzukii-pubmed-literature")
    ingest_drosophila_suzukii_pubmed.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_pubmed.add_argument("--max-results", type=int, default=1000)
    ingest_drosophila_suzukii_pubmed.add_argument("--page-size", type=int, default=100)
    ingest_drosophila_suzukii_pubmed.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_drosophila_suzukii_pubmed.add_argument("--retrieved-at")

    ingest_swd_neuro = sub.add_parser("ingest-drosophila-suzukii-neurobiology")
    ingest_swd_neuro.add_argument("--hosted", action="store_true")
    ingest_swd_neuro.add_argument("--max-results", type=int, default=200)
    ingest_swd_neuro.add_argument("--page-size", type=int, default=100)
    ingest_swd_neuro.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_swd_neuro.add_argument("--retrieved-at")

    ingest_swd_olf = sub.add_parser("ingest-drosophila-suzukii-olfaction-literature")
    ingest_swd_olf.add_argument("--hosted", action="store_true")
    ingest_swd_olf.add_argument("--max-results", type=int, default=1000)
    ingest_swd_olf.add_argument("--page-size", type=int, default=100)
    ingest_swd_olf.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_swd_olf.add_argument("--retrieved-at")

    ingest_swd_traits = sub.add_parser("ingest-drosophila-suzukii-traits")
    ingest_swd_traits.add_argument("--hosted", action="store_true")
    ingest_swd_traits.add_argument("--max-results", type=int, default=1000)
    ingest_swd_traits.add_argument("--page-size", type=int, default=100)
    ingest_swd_traits.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_swd_traits.add_argument("--retrieved-at")

    ingest_swd_biosamples = sub.add_parser("ingest-drosophila-suzukii-ncbi-biosamples")
    ingest_swd_biosamples.add_argument("--hosted", action="store_true")
    ingest_swd_biosamples.add_argument("--limit", type=int, default=1300)
    ingest_swd_biosamples.add_argument("--page-size", type=int, default=200)
    ingest_swd_biosamples.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_swd_biosamples.add_argument("--retrieved-at")

    ingest_swd_chemo = sub.add_parser("ingest-drosophila-suzukii-chemoreceptors")
    ingest_swd_chemo.add_argument("--hosted", action="store_true")
    ingest_swd_chemo.add_argument("--max-results", type=int, default=600)
    ingest_swd_chemo.add_argument("--page-size", type=int, default=200)
    ingest_swd_chemo.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_swd_chemo.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_ncbi_nucleotide = sub.add_parser("ingest-drosophila-suzukii-ncbi-nucleotide")
    ingest_drosophila_suzukii_ncbi_nucleotide.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_ncbi_nucleotide.add_argument("--max-results", type=int, default=1000)
    ingest_drosophila_suzukii_ncbi_nucleotide.add_argument("--page-size", type=int, default=100)
    ingest_drosophila_suzukii_ncbi_nucleotide.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_drosophila_suzukii_ncbi_nucleotide.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_ncbi_marker_review = sub.add_parser("ingest-drosophila-suzukii-ncbi-marker-review")
    ingest_drosophila_suzukii_ncbi_marker_review.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_ncbi_marker_review.add_argument("--max-results", type=int, default=2000)
    ingest_drosophila_suzukii_ncbi_marker_review.add_argument("--page-size", type=int, default=100)
    ingest_drosophila_suzukii_ncbi_marker_review.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_drosophila_suzukii_ncbi_marker_review.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_ncbi_snp = sub.add_parser("ingest-drosophila-suzukii-ncbi-snp-variation")
    ingest_drosophila_suzukii_ncbi_snp.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_ncbi_snp.add_argument("--limit", type=int, default=1000)
    ingest_drosophila_suzukii_ncbi_snp.add_argument("--page-size", type=int, default=200)
    ingest_drosophila_suzukii_ncbi_snp.add_argument("--delay-seconds", type=float, default=0.34)
    ingest_drosophila_suzukii_ncbi_snp.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_ncbi_gene_orthologs = sub.add_parser("ingest-drosophila-suzukii-ncbi-gene-orthologs")
    ingest_drosophila_suzukii_ncbi_gene_orthologs.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_ncbi_gene_orthologs.add_argument("--max-download-bytes", type=int, default=200_000_000)
    ingest_drosophila_suzukii_ncbi_gene_orthologs.add_argument("--max-rows", type=int)
    ingest_drosophila_suzukii_ncbi_gene_orthologs.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_ensembl_metazoa = sub.add_parser("ingest-drosophila-suzukii-ensembl-metazoa-orthology")
    ingest_drosophila_suzukii_ensembl_metazoa.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_ensembl_metazoa.add_argument("--max-download-bytes", type=int, default=50_000_000)
    ingest_drosophila_suzukii_ensembl_metazoa.add_argument("--max-rows-per-file", type=int)
    ingest_drosophila_suzukii_ensembl_metazoa.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_geo_expression = sub.add_parser("ingest-drosophila-suzukii-geo-expression-matrices")
    ingest_drosophila_suzukii_geo_expression.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_geo_expression.add_argument("--max-download-bytes", type=int, default=10_000_000)
    ingest_drosophila_suzukii_geo_expression.add_argument("--max-rows-per-file", type=int)
    ingest_drosophila_suzukii_geo_expression.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_figshare_mk = sub.add_parser("ingest-drosophila-suzukii-figshare-mk-selection")
    ingest_drosophila_suzukii_figshare_mk.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_figshare_mk.add_argument("--max-download-bytes", type=int, default=10_000_000)
    ingest_drosophila_suzukii_figshare_mk.add_argument("--max-rows", type=int)
    ingest_drosophila_suzukii_figshare_mk.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_population_genomics = sub.add_parser("ingest-drosophila-suzukii-population-genomics")
    ingest_drosophila_suzukii_population_genomics.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_population_genomics.add_argument("--limit", type=int, default=100)
    ingest_drosophila_suzukii_population_genomics.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_dryad_population_variants = sub.add_parser("ingest-drosophila-suzukii-dryad-population-variants")
    ingest_drosophila_suzukii_dryad_population_variants.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_dryad_population_variants.add_argument("--max-mirror-bytes", type=int, default=1_000_000_000)
    ingest_drosophila_suzukii_dryad_population_variants.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_extension = sub.add_parser("ingest-drosophila-suzukii-extension-guidance")
    ingest_drosophila_suzukii_extension.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_extension.add_argument("--source-url", action="append", default=[])
    ingest_drosophila_suzukii_extension.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_jki_traps = sub.add_parser("ingest-drosophila-suzukii-jki-drosomon-trap-captures")
    ingest_drosophila_suzukii_jki_traps.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_jki_traps.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_plos_climate = sub.add_parser("ingest-drosophila-suzukii-plos-climate-suitability")
    ingest_drosophila_suzukii_plos_climate.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_plos_climate.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_osu_traps = sub.add_parser("ingest-drosophila-suzukii-osu-trap-reports")
    ingest_drosophila_suzukii_osu_traps.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_osu_traps.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_dryad_landscape = sub.add_parser("ingest-drosophila-suzukii-dryad-landscape-monitoring")
    ingest_drosophila_suzukii_dryad_landscape.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_dryad_landscape.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_umn_flight = sub.add_parser("ingest-drosophila-suzukii-umn-flight-assay-rows")
    ingest_drosophila_suzukii_umn_flight.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_umn_flight.add_argument("--max-download-bytes", type=int, default=1_000_000)
    ingest_drosophila_suzukii_umn_flight.add_argument("--max-rows", type=int)
    ingest_drosophila_suzukii_umn_flight.add_argument("--retrieved-at")

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

    ingest_who_malaria_threats_resistance = sub.add_parser("ingest-who-malaria-threats-resistance")
    ingest_who_malaria_threats_resistance.add_argument("--hosted", action="store_true")
    ingest_who_malaria_threats_resistance.add_argument("--species", default="Aedes aegypti")
    ingest_who_malaria_threats_resistance.add_argument("--sample-limit", type=int, default=5)
    ingest_who_malaria_threats_resistance.add_argument("--aedes-limit", type=int, default=100)

    ingest_harvard_dataverse_suitability = sub.add_parser("ingest-harvard-dataverse-suitability")
    ingest_harvard_dataverse_suitability.add_argument("--hosted", action="store_true")
    ingest_harvard_dataverse_suitability.add_argument("--query", action="append", default=[])
    ingest_harvard_dataverse_suitability.add_argument("--per-page", type=int, default=25)
    ingest_harvard_dataverse_suitability.add_argument("--dataset-limit", type=int, default=12)

    ingest_observation_climate = sub.add_parser("ingest-observation-climate", aliases=["ingest-observation-climate-join"])
    ingest_observation_climate.add_argument("--hosted", action="store_true")
    ingest_observation_climate.add_argument("--limit", type=int, default=1000)
    ingest_observation_climate.add_argument("--input-source", action="append", default=[])
    ingest_observation_climate.add_argument("--worldclim-zip-path")

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

    ingest_ncvbdc_dengue_surveillance = sub.add_parser("ingest-ncvbdc-dengue-surveillance")
    ingest_ncvbdc_dengue_surveillance.add_argument("--hosted", action="store_true")
    ingest_ncvbdc_dengue_surveillance.add_argument("--source-url", action="append", default=[])

    ingest_opendatasus_dengue_surveillance = sub.add_parser("ingest-opendatasus-dengue-surveillance")
    ingest_opendatasus_dengue_surveillance.add_argument("--hosted", action="store_true")
    ingest_opendatasus_dengue_surveillance.add_argument("--year", type=int, action="append", default=[])
    ingest_opendatasus_dengue_surveillance.add_argument("--file-url", action="append", default=[])

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
    ingest_vectorbase_genomics.add_argument("--orthologs-url")
    ingest_vectorbase_genomics.add_argument("--coorthologs-url")
    ingest_vectorbase_genomics.add_argument("--inparalogs-url")

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

    ingest_vectorbyte_abundance = sub.add_parser("ingest-vectorbyte-abundance")
    ingest_vectorbyte_abundance.add_argument("--hosted", action="store_true")
    ingest_vectorbyte_abundance.add_argument("--query", default="Aedes aegypti")
    ingest_vectorbyte_abundance.add_argument("--dataset-limit", type=int, default=5)
    ingest_vectorbyte_abundance.add_argument("--row-limit", type=int, default=5000)
    ingest_vectorbyte_abundance.add_argument("--search-page-limit", type=int, default=3)
    ingest_vectorbyte_abundance.add_argument("--dataset-page-limit", type=int, default=100)
    ingest_vectorbyte_abundance.add_argument("--dataset-id", dest="dataset_ids", action="append", default=[])
    ingest_vectorbyte_abundance.add_argument("--dataset-id-file", dest="dataset_id_files", action="append", default=[])
    ingest_vectorbyte_abundance.add_argument("--merge-existing", action="store_true")

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

    ingest_pmc_videos = sub.add_parser("ingest-pmc-videos")
    ingest_pmc_videos.add_argument("--hosted", action="store_true")
    ingest_pmc_videos.add_argument("--article-url", action="append")
    ingest_pmc_videos.add_argument("--retrieved-at")

    ingest_zenodo_aedes_videos = sub.add_parser("ingest-zenodo-aedes-videos")
    ingest_zenodo_aedes_videos.add_argument("--hosted", action="store_true")
    ingest_zenodo_aedes_videos.add_argument("--query", default='"Aedes aegypti" (video OR movie OR mp4 OR tracking)')
    ingest_zenodo_aedes_videos.add_argument("--size", type=int, default=DEFAULT_ZENODO_SIZE)

    ingest_figshare_aedes_videos = sub.add_parser("ingest-figshare-aedes-videos")
    ingest_figshare_aedes_videos.add_argument("--hosted", action="store_true")
    ingest_figshare_aedes_videos.add_argument("--query", default="Aedes aegypti video")
    ingest_figshare_aedes_videos.add_argument("--page-size", type=int, default=DEFAULT_FIGSHARE_PAGE_SIZE)

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

    ingest_ncbi_snp_variation = sub.add_parser("ingest-ncbi-snp-variation")
    ingest_ncbi_snp_variation.add_argument("--hosted", action="store_true")
    ingest_ncbi_snp_variation.add_argument("--species", default="Aedes aegypti")
    ingest_ncbi_snp_variation.add_argument("--limit", type=int, default=1000)
    ingest_ncbi_snp_variation.add_argument("--page-size", type=int, default=200)
    ingest_ncbi_snp_variation.add_argument("--delay-seconds", type=float, default=0.34)

    ingest_vector_competence_assays = sub.add_parser("ingest-vector-competence-assays")
    ingest_vector_competence_assays.add_argument("--hosted", action="store_true")

    ingest_resistance_markers = sub.add_parser("ingest-resistance-markers")
    ingest_resistance_markers.add_argument("--hosted", action="store_true")

    ingest_resistance_table_rows = sub.add_parser("ingest-resistance-table-rows")
    ingest_resistance_table_rows.add_argument("--hosted", action="store_true")

    ingest_extracted_facts = sub.add_parser("ingest-extracted-facts")
    ingest_extracted_facts.add_argument("--hosted", action="store_true")
    ingest_extracted_facts.add_argument("--max-fulltext-units", type=int, default=5000)
    ingest_extracted_facts.add_argument("--discover-supplements", action="store_true")
    ingest_extracted_facts.add_argument("--download-supplements", action="store_true")
    ingest_extracted_facts.add_argument("--max-supplement-discovery-records", type=int, default=500)
    ingest_extracted_facts.add_argument("--max-repository-supplement-discovery-records", type=int, default=100)
    ingest_extracted_facts.add_argument("--max-supplement-files", type=int, default=100)
    ingest_extracted_facts.add_argument("--max-supplement-bytes", type=int, default=DEFAULT_MAX_SUPPLEMENT_BYTES)
    ingest_extracted_facts.add_argument("--max-pdf-supplement-files", type=int, default=10)
    ingest_extracted_facts.add_argument("--source-record-id", action="append", default=[])
    ingest_extracted_facts.add_argument("--merge-existing", action="store_true")

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
    ingest_video_atoms.add_argument("--discovery-repository", action="append", choices=DISCOVERY_REPOSITORIES, default=[])
    ingest_video_atoms.add_argument("--merge-existing", action="store_true")
    ingest_video_atoms.add_argument("--skip-motion-rows", action="store_true")

    ingest_drosophila_suzukii_video_atoms = sub.add_parser("ingest-drosophila-suzukii-video-atoms")
    ingest_drosophila_suzukii_video_atoms.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_video_atoms.add_argument("--max-video-bytes", type=int, default=750_000_000)
    ingest_drosophila_suzukii_video_atoms.add_argument("--mirror-videos", action="store_true")
    ingest_drosophila_suzukii_video_atoms.add_argument("--generate-artifacts", action="store_true")
    ingest_drosophila_suzukii_video_atoms.add_argument("--allow-unclear-license", action="store_true")
    ingest_drosophila_suzukii_video_atoms.add_argument("--allowed-licenses")

    ingest_drosophila_suzukii_dryad_table_rows = sub.add_parser("ingest-drosophila-suzukii-dryad-table-rows")
    ingest_drosophila_suzukii_dryad_table_rows.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_dryad_table_rows.add_argument("--max-table-files", type=int, default=50)
    ingest_drosophila_suzukii_dryad_table_rows.add_argument("--max-table-rows-per-file", type=int, default=500)

    ingest_drosophila_suzukii_susceptibility_assay_rows = sub.add_parser("ingest-drosophila-suzukii-susceptibility-assay-rows")
    ingest_drosophila_suzukii_susceptibility_assay_rows.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_susceptibility_assay_rows.add_argument("--retrieved-at")

    ingest_drosophila_suzukii_biocontrol_outcome_rows = sub.add_parser("ingest-drosophila-suzukii-biocontrol-outcome-rows")
    ingest_drosophila_suzukii_biocontrol_outcome_rows.add_argument("--hosted", action="store_true")
    ingest_drosophila_suzukii_biocontrol_outcome_rows.add_argument("--retrieved-at")

    ingest_image_atoms = sub.add_parser("ingest-image-atoms")
    ingest_image_atoms.add_argument("--hosted", action="store_true")
    ingest_image_atoms.add_argument("--mirror-images", action="store_true")
    ingest_image_atoms.add_argument("--max-image-bytes", type=int, default=5_000_000)
    ingest_image_atoms.add_argument("--max-image-mirrors", type=int, default=250)
    ingest_image_atoms.add_argument("--allow-unclear-license", action="store_true")
    ingest_image_atoms.add_argument("--allowed-licenses")

    ingest_source_coverage = sub.add_parser("ingest-source-coverage")
    ingest_source_coverage.add_argument("--hosted", action="store_true")
    ingest_source_coverage.add_argument("--coverage-path", default="config/mosquito-intelligence-coverage.json")

    ingest_insect_intelligence_programs = sub.add_parser("ingest-insect-intelligence-programs")
    ingest_insect_intelligence_programs.add_argument("--hosted", action="store_true")
    ingest_insect_intelligence_programs.add_argument(
        "--program-path",
        default="config/insect-intelligence-programs.json",
    )

    ingest_occurrence_ecology = sub.add_parser("ingest-occurrence-ecology")
    ingest_occurrence_ecology.add_argument("--hosted", action="store_true")

    ingest_drosophila_suzukii_occurrence_ecology = sub.add_parser("ingest-drosophila-suzukii-occurrence-ecology")
    ingest_drosophila_suzukii_occurrence_ecology.add_argument("--hosted", action="store_true")

    ingest_aedes_deep_sources = sub.add_parser("ingest-aedes-deep-sources")
    ingest_aedes_deep_sources.add_argument("--hosted", action="store_true")
    ingest_aedes_deep_sources.add_argument("--compendium-row-limit", type=int, default=5000)
    ingest_aedes_deep_sources.add_argument("--bioproject-limit", type=int, default=20)
    ingest_aedes_deep_sources.add_argument("--worldclim-sample-limit", type=int, default=0)

    ingest_aedes_olfaction_literature = sub.add_parser("ingest-aedes-olfaction-literature")
    ingest_aedes_olfaction_literature.add_argument("--hosted", action="store_true")
    ingest_aedes_olfaction_literature.add_argument("--max-results", type=int, default=500)
    ingest_aedes_olfaction_literature.add_argument("--page-size", type=int, default=100)
    ingest_aedes_olfaction_literature.add_argument("--skip-fulltext", action="store_true")
    ingest_aedes_olfaction_literature.add_argument("--unpaywall-email")
    ingest_aedes_olfaction_literature.add_argument("--fulltext-limit", type=int)
    ingest_aedes_olfaction_literature.add_argument("--delay-seconds", type=float, default=1.0)
    ingest_aedes_olfaction_literature.add_argument("--max-fulltext-bytes", type=int, default=60_000_000)

    ingest_crossref_literature_audit = sub.add_parser("ingest-crossref-literature-audit")
    ingest_crossref_literature_audit.add_argument("--hosted", action="store_true")
    ingest_crossref_literature_audit.add_argument("--max-results", type=int, default=500)
    ingest_crossref_literature_audit.add_argument("--page-size", type=int, default=100)

    ingest_mosquito_repellent_literature = sub.add_parser("ingest-mosquito-repellent-literature")
    ingest_mosquito_repellent_literature.add_argument("--hosted", action="store_true")
    ingest_mosquito_repellent_literature.add_argument("--pubmed-max-results", type=int, default=1000)
    ingest_mosquito_repellent_literature.add_argument("--crossref-max-results", type=int, default=1000)
    ingest_mosquito_repellent_literature.add_argument("--page-size", type=int, default=100)

    ingest_mosquito_repellent_external_discovery = sub.add_parser("ingest-mosquito-repellent-external-discovery")
    ingest_mosquito_repellent_external_discovery.add_argument("--hosted", action="store_true")
    ingest_mosquito_repellent_external_discovery.add_argument("--max-results-per-source", type=int, default=50)

    ingest_literature_depth = sub.add_parser("ingest-literature-depth")
    ingest_literature_depth.add_argument("--hosted", action="store_true")
    literature_depth_selection = ingest_literature_depth.add_mutually_exclusive_group(required=True)
    literature_depth_selection.add_argument("--profile")
    literature_depth_selection.add_argument("--all", action="store_true")
    ingest_literature_depth.add_argument("--retrieved-at")
    ingest_literature_depth.add_argument("--max-fulltext-units", type=int, default=2000)
    ingest_literature_depth.add_argument("--discover-supplements", action="store_true")
    ingest_literature_depth.add_argument("--download-supplements", action="store_true")
    ingest_literature_depth.add_argument("--max-supplement-discovery-records", type=int, default=2000)
    ingest_literature_depth.add_argument("--max-repository-supplement-discovery-records", type=int, default=100)
    ingest_literature_depth.add_argument("--max-supplement-files", type=int, default=50)
    ingest_literature_depth.add_argument("--max-supplement-bytes", type=int, default=DEFAULT_MAX_SUPPLEMENT_BYTES)
    ingest_literature_depth.add_argument("--max-pdf-supplement-files", type=int, default=10)

    args = parser.parse_args(argv)
    artifact_dir = Path(args.artifact_dir)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    db_path = artifact_dir / "source_index.sqlite"

    # ask-insects answers ONLY from the hosted plane. The local index is never the
    # default answer surface: read commands route to hosted by default so an agent can
    # never silently query an empty/stale local index. `--local` is an explicit,
    # deliberate dev escape hatch for inspecting a locally-built index.
    HOSTED_DEFAULT_READ_COMMANDS = {"health", "summary", "sources", "ask", "search", "sql"}
    if args.command in HOSTED_DEFAULT_READ_COMMANDS:
        args.hosted = not getattr(args, "local", False)

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
    if args.command == "setup-agent":
        from askinsects.agent_setup import DEFAULT_SKILL_DESTINATION, install_askinsects_skill

        destination = Path(args.destination) if args.destination else DEFAULT_SKILL_DESTINATION
        payload = install_askinsects_skill(destination=destination)
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "health":
        if args.hosted:
            payload = emit_hosted("GET", "/health")
            return 0 if payload.get("ok") else 2
        db_exists = db_path.exists()
        status_exists = (artifact_dir / "source_status.json").exists()
        ok = db_exists and status_exists
        emit({"ok": ok, "db_exists": db_exists, "status_exists": status_exists})
        return 0 if ok else 2
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
    if args.command == "ingest-drosophila-suzukii":
        request_payload = {
            "gbif_occurrence_limit": args.gbif_occurrence_limit,
            "inaturalist_observation_limit": args.inaturalist_observation_limit,
            "literature_max_works": args.literature_max_works,
            "bold_limit": args.bold_limit,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii import ingest_drosophila_suzukii

        payload = ingest_drosophila_suzukii(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-deep-sources":
        request_payload = {
            "ncbi_limit": args.ncbi_limit,
            "protein_limit": args.protein_limit,
            "proteome_limit": args.proteome_limit,
            "repository_limit": args.repository_limit,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-deep-sources", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_deep_sources import ingest_drosophila_suzukii_deep_sources

        payload = ingest_drosophila_suzukii_deep_sources(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-genome-files":
        request_payload = {
            "assembly_accession": args.assembly_accession,
            "max_download_bytes": args.max_download_bytes,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-genome-files", request_payload, timeout=7200)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_genome_files import ingest_drosophila_suzukii_genome_files

        payload = ingest_drosophila_suzukii_genome_files(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-extracted-facts":
        request_payload = {
            "max_fulltext_units": args.max_fulltext_units,
            "discover_supplements": args.discover_supplements,
            "download_supplements": args.download_supplements,
            "max_supplement_discovery_records": args.max_supplement_discovery_records,
            "max_repository_supplement_discovery_records": args.max_repository_supplement_discovery_records,
            "max_supplement_files": args.max_supplement_files,
            "max_supplement_bytes": args.max_supplement_bytes,
            "max_pdf_supplement_files": args.max_pdf_supplement_files,
            "source_record_ids": args.source_record_id or None,
            "merge_existing": args.merge_existing,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-extracted-facts", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_extracted_facts import ingest_drosophila_suzukii_extracted_facts

        payload = ingest_drosophila_suzukii_extracted_facts(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-literature-fulltext":
        request_payload = {
            "email": args.email,
            "limit": args.limit,
            "delay_seconds": args.delay_seconds,
            "max_fulltext_bytes": args.max_fulltext_bytes,
            "include_unpaywall": args.unpaywall or bool(args.email),
            "resume": args.resume,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-literature-fulltext", request_payload, timeout=7200)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_literature_fulltext import ingest_drosophila_suzukii_literature_fulltext

        payload = ingest_drosophila_suzukii_literature_fulltext(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-pubmed-literature":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-pubmed-literature", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_pubmed_literature import ingest_drosophila_suzukii_pubmed_literature

        payload = ingest_drosophila_suzukii_pubmed_literature(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-neurobiology":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-neurobiology", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_neurobiology import ingest_drosophila_suzukii_neurobiology

        payload = ingest_drosophila_suzukii_neurobiology(artifact_dir=artifact_dir, **request_payload)
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-olfaction-literature":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-olfaction-literature", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_olfaction_literature import ingest_drosophila_suzukii_olfaction_literature

        payload = ingest_drosophila_suzukii_olfaction_literature(artifact_dir=artifact_dir, **request_payload)
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-traits":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-traits", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_traits import ingest_drosophila_suzukii_traits

        payload = ingest_drosophila_suzukii_traits(artifact_dir=artifact_dir, **request_payload)
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-ncbi-biosamples":
        request_payload = {
            "limit": args.limit,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-ncbi-biosamples", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_ncbi_biosamples import ingest_drosophila_suzukii_ncbi_biosamples

        payload = ingest_drosophila_suzukii_ncbi_biosamples(artifact_dir=artifact_dir, **request_payload)
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-chemoreceptors":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-chemoreceptors", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_chemoreceptors import ingest_drosophila_suzukii_chemoreceptors

        payload = ingest_drosophila_suzukii_chemoreceptors(artifact_dir=artifact_dir, **request_payload)
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-ncbi-nucleotide":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-ncbi-nucleotide", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_ncbi_nucleotide import ingest_drosophila_suzukii_ncbi_nucleotide

        payload = ingest_drosophila_suzukii_ncbi_nucleotide(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-ncbi-marker-review":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-ncbi-marker-review", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_ncbi_marker_review import ingest_drosophila_suzukii_ncbi_marker_review

        payload = ingest_drosophila_suzukii_ncbi_marker_review(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-ncbi-snp-variation":
        request_payload = {
            "limit": args.limit,
            "page_size": args.page_size,
            "delay_seconds": args.delay_seconds,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-ncbi-snp-variation", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_ncbi_snp_variation import ingest_drosophila_suzukii_ncbi_snp_variation

        payload = ingest_drosophila_suzukii_ncbi_snp_variation(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-ncbi-gene-orthologs":
        request_payload = {
            "max_download_bytes": args.max_download_bytes,
            "max_rows": args.max_rows,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-ncbi-gene-orthologs", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_ncbi_gene_orthologs import ingest_drosophila_suzukii_ncbi_gene_orthologs

        payload = ingest_drosophila_suzukii_ncbi_gene_orthologs(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-ensembl-metazoa-orthology":
        request_payload = {
            "max_download_bytes": args.max_download_bytes,
            "max_rows_per_file": args.max_rows_per_file,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-ensembl-metazoa-orthology", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_ensembl_metazoa_orthology import ingest_drosophila_suzukii_ensembl_metazoa_orthology

        payload = ingest_drosophila_suzukii_ensembl_metazoa_orthology(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-geo-expression-matrices":
        request_payload = {
            "max_download_bytes": args.max_download_bytes,
            "max_rows_per_file": args.max_rows_per_file,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-geo-expression-matrices", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_geo_expression_matrices import ingest_drosophila_suzukii_geo_expression_matrices

        payload = ingest_drosophila_suzukii_geo_expression_matrices(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-figshare-mk-selection":
        request_payload = {
            "max_download_bytes": args.max_download_bytes,
            "max_rows": args.max_rows,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-figshare-mk-selection", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_figshare_mk_selection import ingest_drosophila_suzukii_figshare_mk_selection

        payload = ingest_drosophila_suzukii_figshare_mk_selection(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-population-genomics":
        request_payload = {
            "limit": args.limit,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-population-genomics", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_population_genomics import ingest_drosophila_suzukii_population_genomics

        payload = ingest_drosophila_suzukii_population_genomics(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-dryad-population-variants":
        request_payload = {
            "max_mirror_bytes": args.max_mirror_bytes,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-dryad-population-variants", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_dryad_population_variants import ingest_drosophila_suzukii_dryad_population_variants

        payload = ingest_drosophila_suzukii_dryad_population_variants(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-extension-guidance":
        request_payload = {
            "source_urls": args.source_url,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-extension-guidance", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_extension_guidance import ingest_drosophila_suzukii_extension_guidance

        payload = ingest_drosophila_suzukii_extension_guidance(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-jki-drosomon-trap-captures":
        request_payload = {
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-jki-drosomon-trap-captures", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_jki_drosomon_trap_captures import ingest_drosophila_suzukii_jki_drosomon_trap_captures

        payload = ingest_drosophila_suzukii_jki_drosomon_trap_captures(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-plos-climate-suitability":
        request_payload = {
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-plos-climate-suitability", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_plos_climate_suitability import ingest_drosophila_suzukii_plos_climate_suitability

        payload = ingest_drosophila_suzukii_plos_climate_suitability(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-osu-trap-reports":
        request_payload = {
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-osu-trap-reports", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_osu_trap_reports import ingest_drosophila_suzukii_osu_trap_reports

        payload = ingest_drosophila_suzukii_osu_trap_reports(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-dryad-landscape-monitoring":
        request_payload = {
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-dryad-landscape-monitoring", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_dryad_landscape_monitoring import (
            ingest_drosophila_suzukii_dryad_landscape_monitoring,
        )

        payload = ingest_drosophila_suzukii_dryad_landscape_monitoring(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-umn-flight-assay-rows":
        request_payload = {
            "max_download_bytes": args.max_download_bytes,
            "max_rows": args.max_rows,
            "retrieved_at": args.retrieved_at,
        }
        if args.hosted:
            payload = emit_hosted("POST", "/ingest/drosophila-suzukii-umn-flight-assay-rows", request_payload, timeout=3600)
            return 0 if payload.get("ok") else 2
        from scripts.ingest_drosophila_suzukii_umn_flight_assay_rows import ingest_drosophila_suzukii_umn_flight_assay_rows

        payload = ingest_drosophila_suzukii_umn_flight_assay_rows(
            artifact_dir=artifact_dir,
            **request_payload,
        )
        emit(payload)
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
    if args.command == "ingest-who-malaria-threats-resistance":
        if not args.hosted:
            from scripts.ingest_who_malaria_threats_resistance import ingest_who_malaria_threats_resistance

            payload = ingest_who_malaria_threats_resistance(
                artifact_dir=artifact_dir,
                species=args.species,
                sample_limit=args.sample_limit,
                aedes_limit=args.aedes_limit,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/who-malaria-threats-resistance",
            {
                "species": args.species,
                "sample_limit": args.sample_limit,
                "aedes_limit": args.aedes_limit,
            },
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-harvard-dataverse-suitability":
        from askinsects.sources.harvard_dataverse_suitability import DEFAULT_QUERIES

        queries = tuple(args.query) if args.query else DEFAULT_QUERIES
        if not args.hosted:
            from scripts.ingest_harvard_dataverse_suitability import ingest_harvard_dataverse_suitability

            payload = ingest_harvard_dataverse_suitability(
                artifact_dir=artifact_dir,
                queries=queries,
                per_page=args.per_page,
                dataset_limit=args.dataset_limit,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/harvard-dataverse-suitability",
            {
                "queries": list(queries),
                "per_page": args.per_page,
                "dataset_limit": args.dataset_limit,
            },
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command in {"ingest-observation-climate", "ingest-observation-climate-join"}:
        input_sources = tuple(args.input_source) if args.input_source else None
        if not args.hosted:
            from scripts.ingest_observation_climate import ingest_observation_climate

            payload = ingest_observation_climate(
                artifact_dir=artifact_dir,
                worldclim_zip_path=Path(args.worldclim_zip_path) if args.worldclim_zip_path else None,
                limit=args.limit,
                input_sources=input_sources,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/observation-climate-join",
            {
                "limit": args.limit,
                "input_sources": list(input_sources) if input_sources else None,
                "worldclim_zip_path": args.worldclim_zip_path,
            },
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
    if args.command == "ingest-ncvbdc-dengue-surveillance":
        if not args.hosted:
            from scripts.ingest_ncvbdc_dengue_surveillance import ingest_ncvbdc_dengue_surveillance

            payload = ingest_ncvbdc_dengue_surveillance(
                artifact_dir=artifact_dir,
                source_urls=args.source_url,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/ncvbdc-dengue-surveillance",
            {"source_urls": args.source_url},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-opendatasus-dengue-surveillance":
        if not args.hosted:
            from scripts.ingest_opendatasus_dengue_surveillance import ingest_opendatasus_dengue_surveillance

            payload = ingest_opendatasus_dengue_surveillance(
                artifact_dir=artifact_dir,
                years=args.year,
                file_urls=args.file_url,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/opendatasus-dengue-surveillance",
            {"years": args.year, "file_urls": args.file_url},
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
                "orthologs": args.orthologs_url,
                "coorthologs": args.coorthologs_url,
                "inparalogs": args.inparalogs_url,
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
    if args.command == "ingest-vectorbyte-abundance":
        request_payload = {
            "query": args.query,
            "dataset_limit": args.dataset_limit,
            "row_limit": args.row_limit,
            "search_page_limit": args.search_page_limit,
            "dataset_page_limit": args.dataset_page_limit,
            "merge_existing": args.merge_existing,
        }
        from scripts.ingest_vectorbyte_abundance import load_dataset_ids_file, merge_dataset_ids

        file_dataset_ids: list[str] = []
        for path in args.dataset_id_files:
            file_dataset_ids.extend(load_dataset_ids_file(Path(path)))
        dataset_ids = merge_dataset_ids(args.dataset_ids, file_dataset_ids)
        if dataset_ids:
            request_payload["dataset_ids"] = dataset_ids
        if not args.hosted:
            from scripts.ingest_vectorbyte_abundance import ingest_vectorbyte_abundance

            payload = ingest_vectorbyte_abundance(artifact_dir=artifact_dir, **request_payload)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/vectorbyte-abundance",
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
    if args.command == "ingest-pmc-videos":
        if not args.hosted:
            from scripts.ingest_pmc_videos import ingest_pmc_videos

            payload = ingest_pmc_videos(
                artifact_dir=artifact_dir,
                article_urls=args.article_url,
                retrieved_at=args.retrieved_at,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/pmc-videos",
            {"article_urls": args.article_url, "retrieved_at": args.retrieved_at},
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
    if args.command == "ingest-ncbi-snp-variation":
        if not args.hosted:
            from scripts.ingest_ncbi_snp_variation import ingest_ncbi_snp_variation

            payload = ingest_ncbi_snp_variation(
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
            "/ingest/ncbi-snp-variation",
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
    if args.command == "ingest-resistance-table-rows":
        if not args.hosted:
            from scripts.ingest_resistance_table_rows import ingest_resistance_table_rows

            payload = ingest_resistance_table_rows(artifact_dir=artifact_dir)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/resistance-table-rows",
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
                max_repository_supplement_discovery_records=args.max_repository_supplement_discovery_records,
                max_supplement_files=args.max_supplement_files,
                max_supplement_bytes=args.max_supplement_bytes,
                max_pdf_supplement_files=args.max_pdf_supplement_files,
                source_record_ids=args.source_record_id or None,
                merge_existing=args.merge_existing,
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
                "max_repository_supplement_discovery_records": args.max_repository_supplement_discovery_records,
                "max_supplement_files": args.max_supplement_files,
                "max_supplement_bytes": args.max_supplement_bytes,
                "max_pdf_supplement_files": args.max_pdf_supplement_files,
                "source_record_ids": args.source_record_id,
                "merge_existing": args.merge_existing,
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
                discovery_repositories=args.discovery_repository or None,
                max_discovery_results=args.max_discovery_results,
                merge_existing=args.merge_existing,
                parse_motion_rows=not args.skip_motion_rows,
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
                "discovery_repositories": args.discovery_repository,
                "merge_existing": args.merge_existing,
                "parse_motion_rows": not args.skip_motion_rows,
            },
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-video-atoms":
        allowed_licenses = split_csv(args.allowed_licenses)
        if not args.hosted:
            from scripts.ingest_drosophila_suzukii_video_atoms import ingest_drosophila_suzukii_video_atoms

            payload = ingest_drosophila_suzukii_video_atoms(
                artifact_dir=artifact_dir,
                max_video_bytes=args.max_video_bytes,
                mirror_videos=args.mirror_videos,
                generate_artifacts=args.generate_artifacts,
                allow_unclear_license=args.allow_unclear_license,
                allowed_licenses=allowed_licenses or None,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/drosophila-suzukii-video-atoms",
            {
                "max_video_bytes": args.max_video_bytes,
                "mirror_videos": args.mirror_videos,
                "generate_artifacts": args.generate_artifacts,
                "allow_unclear_license": args.allow_unclear_license,
                "allowed_licenses": allowed_licenses,
            },
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-dryad-table-rows":
        if not args.hosted:
            from scripts.ingest_drosophila_suzukii_dryad_table_rows import ingest_drosophila_suzukii_dryad_table_rows

            payload = ingest_drosophila_suzukii_dryad_table_rows(
                artifact_dir=artifact_dir,
                max_table_files=args.max_table_files,
                max_table_rows_per_file=args.max_table_rows_per_file,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/drosophila-suzukii-dryad-table-rows",
            {
                "max_table_files": args.max_table_files,
                "max_table_rows_per_file": args.max_table_rows_per_file,
            },
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-susceptibility-assay-rows":
        if not args.hosted:
            from scripts.ingest_drosophila_suzukii_susceptibility_assay_rows import (
                ingest_drosophila_suzukii_susceptibility_assay_rows,
            )

            payload = ingest_drosophila_suzukii_susceptibility_assay_rows(
                artifact_dir=artifact_dir,
                retrieved_at=args.retrieved_at,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/drosophila-suzukii-susceptibility-assay-rows",
            {"retrieved_at": args.retrieved_at},
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-drosophila-suzukii-biocontrol-outcome-rows":
        if not args.hosted:
            from scripts.ingest_drosophila_suzukii_biocontrol_outcome_rows import (
                ingest_drosophila_suzukii_biocontrol_outcome_rows,
            )

            payload = ingest_drosophila_suzukii_biocontrol_outcome_rows(
                artifact_dir=artifact_dir,
                retrieved_at=args.retrieved_at,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/drosophila-suzukii-biocontrol-outcome-rows",
            {"retrieved_at": args.retrieved_at},
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-image-atoms":
        allowed_licenses = tuple(part.strip() for part in (args.allowed_licenses or "").split(",") if part.strip()) or None
        if not args.hosted:
            from scripts.ingest_image_atoms import ingest_image_atoms

            payload = ingest_image_atoms(
                artifact_dir=artifact_dir,
                mirror_images=args.mirror_images,
                max_image_bytes=args.max_image_bytes,
                max_image_mirrors=args.max_image_mirrors,
                allow_unclear_license=args.allow_unclear_license,
                allowed_licenses=allowed_licenses,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/image-atoms",
            {
                "mirror_images": args.mirror_images,
                "max_image_bytes": args.max_image_bytes,
                "max_image_mirrors": args.max_image_mirrors,
                "allow_unclear_license": args.allow_unclear_license,
                "allowed_licenses": list(allowed_licenses) if allowed_licenses else None,
            },
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-source-coverage":
        if not args.hosted:
            from scripts.ingest_source_coverage import ingest_source_coverage

            payload = ingest_source_coverage(artifact_dir=artifact_dir, coverage_path=Path(args.coverage_path))
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/source-coverage",
            {"coverage_path": args.coverage_path},
            timeout=120,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-insect-intelligence-programs":
        if not args.hosted:
            from scripts.ingest_insect_intelligence_programs import ingest_insect_intelligence_programs

            payload = ingest_insect_intelligence_programs(
                artifact_dir=artifact_dir,
                program_path=Path(args.program_path),
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/insect-intelligence-programs",
            {"program_path": args.program_path},
            timeout=120,
        )
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
    if args.command == "ingest-drosophila-suzukii-occurrence-ecology":
        if not args.hosted:
            from scripts.ingest_drosophila_suzukii_occurrence_ecology import ingest_drosophila_suzukii_occurrence_ecology

            payload = ingest_drosophila_suzukii_occurrence_ecology(artifact_dir=artifact_dir)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/drosophila-suzukii-occurrence-ecology",
            {},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-aedes-deep-sources":
        request_payload = {
            "compendium_row_limit": args.compendium_row_limit,
            "bioproject_limit": args.bioproject_limit,
            "worldclim_sample_limit": args.worldclim_sample_limit,
        }
        if not args.hosted:
            from scripts.ingest_aedes_deep_sources import ingest_aedes_deep_sources

            payload = ingest_aedes_deep_sources(artifact_dir=artifact_dir, **request_payload)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/aedes-deep-sources",
            request_payload,
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-aedes-olfaction-literature":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
            "include_fulltext": not args.skip_fulltext,
            "unpaywall_email": args.unpaywall_email,
            "fulltext_limit": args.fulltext_limit,
            "delay_seconds": args.delay_seconds,
            "max_fulltext_bytes": args.max_fulltext_bytes,
        }
        if not args.hosted:
            from scripts.ingest_aedes_olfaction_literature import ingest_aedes_olfaction_literature

            payload = ingest_aedes_olfaction_literature(artifact_dir=artifact_dir, **request_payload)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/aedes-olfaction-literature",
            request_payload,
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-crossref-literature-audit":
        request_payload = {
            "max_results": args.max_results,
            "page_size": args.page_size,
        }
        if not args.hosted:
            from scripts.ingest_aedes_crossref_literature_audit import ingest_aedes_crossref_literature_audit

            payload = ingest_aedes_crossref_literature_audit(artifact_dir=artifact_dir, **request_payload)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/crossref-literature-audit",
            request_payload,
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-mosquito-repellent-literature":
        request_payload = {
            "pubmed_max_results": args.pubmed_max_results,
            "crossref_max_results": args.crossref_max_results,
            "page_size": args.page_size,
        }
        if not args.hosted:
            from scripts.ingest_mosquito_repellent_literature import ingest_mosquito_repellent_literature

            payload = ingest_mosquito_repellent_literature(artifact_dir=artifact_dir, **request_payload)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/mosquito-repellent-literature",
            request_payload,
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-mosquito-repellent-external-discovery":
        request_payload = {
            "max_results_per_source": args.max_results_per_source,
        }
        if not args.hosted:
            from scripts.ingest_mosquito_repellent_external_discovery import ingest_mosquito_repellent_external_discovery

            payload = ingest_mosquito_repellent_external_discovery(artifact_dir=artifact_dir, **request_payload)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/mosquito-repellent-external-discovery",
            request_payload,
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-literature-depth":
        request_payload = {
            "profile": args.profile,
            "all_profiles": args.all,
            "retrieved_at": args.retrieved_at,
            "max_fulltext_units": args.max_fulltext_units,
            "discover_supplements": args.discover_supplements,
            "download_supplements": args.download_supplements,
            "max_supplement_discovery_records": args.max_supplement_discovery_records,
            "max_repository_supplement_discovery_records": args.max_repository_supplement_discovery_records,
            "max_supplement_files": args.max_supplement_files,
            "max_supplement_bytes": args.max_supplement_bytes,
            "max_pdf_supplement_files": args.max_pdf_supplement_files,
        }
        if not args.hosted:
            from scripts.ingest_literature_depth import ingest_literature_depth

            payload = ingest_literature_depth(artifact_dir=artifact_dir, **request_payload)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/literature-depth",
            request_payload,
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    parser.error("unknown command")
    return 1
