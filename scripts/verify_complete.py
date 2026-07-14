#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
import csv
import hashlib
import ipaddress
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VERIFY_ARTIFACT_DIR = Path(tempfile.mkdtemp(prefix="ask-insects-verify-")) / "mosquito-v1"
VERIFY_ENV = {**os.environ, "ASK_INSECTS_ARTIFACT_DIR": VERIFY_ARTIFACT_DIR.as_posix()}
GENERIC_CONFIG_PATH = "config/insect-evidence-package.json"
GENERIC_CONFIG_SCHEMA_VERSION = "ask-insects-evidence-package-config.v2"
PUBLIC_PACKAGE_SCHEMA_VERSION = "ask-insects-evidence-package.v3"
DIRECT_EVIDENCE_RULESET_VERSION = "direct-semantic-evidence.v3"
PUBLIC_VALIDATION_CONTRACT = {
    "producer_linkage": (
        "status_record_count_selected_rows_and_links_verified_in_read_only_source_index"
    ),
    "downstream_validation": "exported_snapshot_internal_consistency_only",
    "snapshot_authentication": "publisher_pinned_content_sha256",
}
GENERIC_CONTEXT_IDS = (
    "treated_area_contact_avoidance",
    "treated_area_noncontact_avoidance",
    "bounded_choice_orientation",
    "oviposition_choice",
    "human_landing_response",
    "spatial_behavior",
    "post_exposure_behavior",
)
GENERIC_CONFIG_CONTEXT_FIELDS = frozenset(
    {
        "id",
        "endpoint_family",
        "exposure_routes",
        "species_ids",
        "required_domains",
        "measures",
        "does_not_establish",
        "plausible_explanations",
        "discriminating_evidence",
        "selectors",
    }
)
PUBLIC_CONTEXT_FIELDS = (GENERIC_CONFIG_CONTEXT_FIELDS - {"selectors"}) | {"provenance"}
PUBLIC_PACKAGE_FIELDS = frozenset(
    {
        "ok",
        "schema_version",
        "package_version",
        "generated_at",
        "objective",
        "validation_contract",
        "configuration_sources",
        "knowledge_domains",
        "upstream_snapshot",
        "contexts",
        "program_records",
        "evidence_records",
        "selector_results",
        "gaps",
        "content_sha256",
    }
)
MAX_PUBLIC_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_PUBLIC_PACKAGE_STRING_LENGTH = 100_000
MAX_PUBLIC_PACKAGE_LIST_ITEMS = 10_000
MAX_PUBLIC_PACKAGE_DEPTH = 20
FORBIDDEN_FILES = ("config/ask-monarch-context-package.json",)
ACTIVE_PUBLIC_SURFACE_DIRS = ("askinsects", "config", "public", "skills/askinsects")
ACTIVE_PUBLIC_SURFACE_FILES = ("pyproject.toml",)
ACTIVE_TEXT_SUFFIXES = frozenset({".json", ".md", ".py", ".toml", ".yaml", ".yml"})
CONSUMER_NAME_RE = re.compile(
    r"(?i)(?:\bask[\s_-]+monarch\b|(?<![a-z0-9])(?:[a-z0-9]+_)*monarch(?:_[a-z0-9]+)*(?![a-z0-9]))"
)
NON_PUBLIC_LOCATOR_RE = re.compile(
    r"(?i)(?<![a-z0-9+.-])(?!https://)[a-z][a-z0-9+.-]*://"
    r"|(?<![a-z0-9+.-])file:/"
)
CREDENTIAL_KEY_TOKENS = frozenset(
    {
        "apikey",
        "auth",
        "authentication",
        "authorization",
        "credential",
        "credentials",
        "passwd",
        "password",
        "secret",
        "token",
    }
)
CONSUMER_KEY_TOKENS = frozenset({"consumer", "customer", "private", "tenant"})
ABSOLUTE_FILESYSTEM_PATH_RE = re.compile(
    r"(?i)(?:^|[\s\"'(=:])(?:/(?!/)[^\s,;]+|[a-z]:[\\/]|\\\\)"
)
SECRET_VALUE_RE = re.compile(
    r"(?i)(?:\bbearer\s+[a-z0-9._~+/=-]{8,}|\b(?:ghp|sk|xox[baprs])[-_][a-z0-9_-]{12,})"
)
PUBLIC_URL_RE = re.compile(r"https?://[^\s<>\"']+", flags=re.IGNORECASE)
QUERY_CREDENTIAL_KEY_TOKENS = frozenset({"key", "session", "sig", "signature"})

REQUIRED_FILES = (
    "AGENTS.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "THIRD_PARTY_DATA.md",
    "pyproject.toml",
    "config/source-map.yaml",
    "config/insect-evidence-package.json",
    "config/insect-intelligence-programs.json",
    "public/evidence-packages/ask-insects-evidence-package-2026-07-14.7.json",
    "config/mosquito-intelligence-coverage.json",
    "config/aedes-source-plane-benchmark.json",
    "data/fixtures/mosquito_records.json",
    "docs/aedes-source-plane-benchmark.md",
    "docs/production-path-evaluation.md",
    "docs/querying-ask-insects.md",
    "docs/source-lanes.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-mosquito-v1-design.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-gbif-v1-design.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-inaturalist-v1-design.md",
    "docs/superpowers/specs/2026-05-23-inaturalist-deep-aedes-ingest-design.md",
    "docs/superpowers/specs/2026-05-23-aedes-aegypti-literature-source-lane-design.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-hosted-vm-infra-design.md",
    "docs/superpowers/specs/2026-05-23-aedes-aegypti-genomics-lane-design.md",
    "docs/superpowers/specs/2026-05-23-aedes-aegypti-neurobiology-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-neurobiology-deep-source-completion-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-aegypti-world-intelligence-source-plane-design.md",
    "docs/superpowers/specs/2026-05-23-neurobiology-gap-closure-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-vector-competence-assay-candidates-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-ncbi-biosample-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-resistance-marker-lane-design.md",
    "docs/superpowers/specs/2026-05-25-aedes-resistance-table-rows-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-occurrence-ecology-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-vectorbase-genomics-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-mendeley-behavior-media-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-mendeley-behavior-table-deep-parse-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-osf-flighttrackai-video-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-extracted-facts-design.md",
    "docs/superpowers/specs/2026-05-25-aedes-wave1-expression-uniprot-wolbachia-design.md",
    "docs/superpowers/specs/2026-05-25-aedes-cdc-dengue-surveillance-design.md",
    "docs/superpowers/specs/2026-05-26-aedes-ncvbdc-dengue-surveillance-design.md",
    "docs/superpowers/specs/2026-05-26-aedes-opendatasus-dengue-surveillance-design.md",
    "docs/superpowers/specs/2026-05-25-aedes-vectorbyte-traits-design.md",
    "docs/superpowers/specs/2026-05-25-aedes-crossref-literature-audit-design.md",
    "docs/superpowers/specs/2026-05-25-mosquito-repellent-literature-design.md",
    "docs/superpowers/specs/2026-05-25-mosquito-repellent-external-discovery-design.md",
    "docs/superpowers/specs/2026-05-24-open-insects-public-identity-design.md",
    "docs/superpowers/specs/2026-05-28-drosophila-suzukii-source-plane-design.md",
    "docs/superpowers/specs/2026-06-05-swd-aedes-parity-program-design.md",
    "docs/superpowers/specs/2026-06-05-swd-neurobiology-olfaction-lane-design.md",
    "docs/superpowers/specs/2026-07-10-ask-insects-repellency-evidence-workflow-design.md",
    "docs/superpowers/specs/2026-07-13-dual-product-insect-intelligence-design.md",
    "docs/superpowers/specs/2026-07-14-generic-insect-evidence-package-design.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-mosquito-v1.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-gbif-v1.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-inaturalist-v1.md",
    "docs/superpowers/plans/2026-05-23-inaturalist-deep-aedes-ingest.md",
    "docs/superpowers/plans/2026-05-23-aedes-aegypti-literature-source-lane.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-hosted-vm-infra.md",
    "docs/superpowers/plans/2026-05-23-aedes-aegypti-genomics-lane.md",
    "docs/superpowers/plans/2026-05-23-aedes-aegypti-neurobiology-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-neurobiology-deep-source-completion.md",
    "docs/superpowers/plans/2026-05-23-neurobiology-gap-closure.md",
    "docs/superpowers/plans/2026-05-24-aedes-vector-competence-assay-candidates.md",
    "docs/superpowers/plans/2026-05-24-aedes-ncbi-biosample-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-resistance-marker-lane.md",
    "docs/superpowers/plans/2026-05-25-aedes-resistance-table-rows.md",
    "docs/superpowers/plans/2026-05-24-aedes-occurrence-ecology-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-vectorbase-genomics-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-mendeley-behavior-media-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-mendeley-behavior-table-deep-parse.md",
    "docs/superpowers/plans/2026-05-24-aedes-osf-flighttrackai-video-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-extracted-facts.md",
    "docs/superpowers/plans/2026-05-24-aedes-video-atoms.md",
    "docs/superpowers/plans/2026-05-25-aedes-image-atoms.md",
    "docs/superpowers/plans/2026-05-25-aedes-wave1-expression-uniprot-wolbachia.md",
    "docs/superpowers/plans/2026-05-25-aedes-cdc-dengue-surveillance.md",
    "docs/superpowers/plans/2026-05-26-aedes-ncvbdc-dengue-surveillance.md",
    "docs/superpowers/plans/2026-05-26-aedes-opendatasus-dengue-surveillance.md",
    "docs/superpowers/plans/2026-05-25-aedes-vectorbyte-traits.md",
    "docs/superpowers/plans/2026-05-25-aedes-crossref-literature-audit.md",
    "docs/superpowers/plans/2026-05-25-mosquito-repellent-literature.md",
    "docs/superpowers/plans/2026-05-25-mosquito-repellent-external-discovery.md",
    "docs/superpowers/plans/2026-05-24-open-insects-public-identity.md",
    "docs/superpowers/plans/2026-05-28-drosophila-suzukii-source-plane.md",
    "docs/superpowers/plans/2026-05-29-swd-susceptibility-assay-lane.md",
    "docs/superpowers/plans/2026-05-29-swd-biocontrol-outcome-lane.md",
    "docs/superpowers/plans/2026-07-10-ask-insects-repellency-evidence-workflow.md",
    "docs/superpowers/plans/2026-07-13-dual-product-insect-intelligence.md",
    "docs/superpowers/plans/2026-07-14-generic-insect-evidence-package.md",
    "evals/ask_insects_production_path_v1.json",
    "evals/repellency_comparison_v1.json",
    "askinsects/__init__.py",
    "askinsects/__main__.py",
    "askinsects/answer.py",
    "askinsects/agent_setup.py",
    "askinsects/builder.py",
    "askinsects/cli.py",
    "askinsects/context_package.py",
    "askinsects/hosted.py",
    "askinsects/index.py",
    "askinsects/planner.py",
    "askinsects/records.py",
    "askinsects/repellency.py",
    "askinsects/server.py",
    "askinsects/voxels.py",
    "askinsects/sources/__init__.py",
    "skills/askinsects/SKILL.md",
    "skills/askinsects/agents/openai.yaml",
    "askinsects/sources/fixtures.py",
    "askinsects/sources/bold_barcodes.py",
    "askinsects/sources/gbif.py",
    "askinsects/sources/inaturalist.py",
    "askinsects/sources/literature.py",
    "askinsects/sources/ncbi_genome.py",
    "askinsects/sources/neurobiology.py",
    "askinsects/sources/pmc_videos.py",
    "askinsects/sources/irmapper.py",
    "askinsects/sources/who_malaria_threats_resistance.py",
    "askinsects/sources/mosquito_alert.py",
    "askinsects/sources/vectornet_surveillance.py",
    "askinsects/sources/dryad_behavior_videos.py",
    "askinsects/sources/mendeley_behavior_media.py",
    "askinsects/sources/osf_flighttrackai_videos.py",
    "askinsects/sources/zenodo_aedes_videos.py",
    "askinsects/sources/figshare_aedes_videos.py",
    "askinsects/sources/public_health.py",
    "askinsects/sources/paho_surveillance.py",
    "askinsects/sources/who_dengue_surveillance.py",
    "askinsects/sources/cdc_dengue_surveillance.py",
    "askinsects/sources/ncvbdc_dengue_surveillance.py",
    "askinsects/sources/opendatasus_dengue_surveillance.py",
    "askinsects/sources/pathogen_taxonomy.py",
    "askinsects/sources/ncbi_biosample.py",
    "askinsects/sources/vectorbase_genomics.py",
    "askinsects/sources/vector_competence_assays.py",
    "askinsects/sources/resistance_markers.py",
    "askinsects/sources/resistance_table_rows.py",
    "askinsects/sources/occurrence_ecology.py",
    "askinsects/sources/observation_climate.py",
    "askinsects/sources/extracted_facts.py",
    "askinsects/sources/expression_omics.py",
    "askinsects/sources/aedes_olfaction_literature.py",
    "askinsects/sources/aedes_crossref_literature_audit.py",
    "askinsects/sources/mosquito_repellent_literature.py",
    "askinsects/sources/mosquito_repellent_external_discovery.py",
    "askinsects/sources/repellency_facts.py",
    "askinsects/sources/insect_intelligence_programs.py",
    "askinsects/sources/literature_depth_profiles.py",
    "askinsects/sources/uniprot_proteins.py",
    "askinsects/sources/wolbachia_interventions.py",
    "askinsects/sources/vectorbyte_traits.py",
    "askinsects/sources/vectorbyte_abundance.py",
    "askinsects/sources/video_atoms.py",
    "askinsects/sources/image_atoms.py",
    "askinsects/sources/aedes_deep_sources.py",
    "askinsects/sources/drosophila_suzukii.py",
    "askinsects/sources/drosophila_suzukii_deep_sources.py",
    "askinsects/sources/drosophila_suzukii_extracted_facts.py",
    "askinsects/sources/drosophila_suzukii_pubmed_literature.py",
    "askinsects/sources/drosophila_suzukii_genome_files.py",
    "askinsects/sources/drosophila_suzukii_ncbi_nucleotide.py",
    "askinsects/sources/drosophila_suzukii_ncbi_marker_review.py",
    "askinsects/sources/drosophila_suzukii_ncbi_snp_variation.py",
    "askinsects/sources/drosophila_suzukii_figshare_mk_selection.py",
    "askinsects/sources/drosophila_suzukii_population_genomics.py",
    "askinsects/sources/drosophila_suzukii_dryad_population_variants.py",
    "askinsects/sources/drosophila_suzukii_ncbi_gene_orthologs.py",
    "askinsects/sources/drosophila_suzukii_ensembl_metazoa_orthology.py",
    "askinsects/sources/drosophila_suzukii_geo_expression_matrices.py",
    "askinsects/sources/drosophila_suzukii_extension_guidance.py",
    "askinsects/sources/drosophila_suzukii_jki_drosomon_trap_captures.py",
    "askinsects/sources/drosophila_suzukii_osu_trap_reports.py",
    "askinsects/sources/drosophila_suzukii_dryad_landscape_monitoring.py",
    "askinsects/sources/drosophila_suzukii_umn_flight_assay_rows.py",
    "askinsects/sources/drosophila_suzukii_susceptibility_assay_rows.py",
    "askinsects/sources/drosophila_suzukii_biocontrol_outcome_rows.py",
    "askinsects/sources/drosophila_suzukii_video_atoms.py",
    "askinsects/sources/drosophila_suzukii_dryad_table_rows.py",
    "askinsects/sources/drosophila_suzukii_occurrence_ecology.py",
    "askinsects/sources/drosophila_suzukii_plos_climate_suitability.py",
    "askinsects/sources/ncbi_snp_variation.py",
    "askinsects/sources/harvard_dataverse_suitability.py",
    "scripts/build_source_index.py",
    "scripts/__init__.py",
    "scripts/enrich_literature_index.py",
    "scripts/ingest_neurobiology_sources.py",
    "scripts/deploy_gce_app.sh",
    "scripts/ask-insects-launcher",
    "scripts/install_local_runtime.sh",
    "scripts/deploy_gce_vm.sh",
    "scripts/install_hosted_tunnel_launchd.sh",
    "scripts/run_hosted_tunnel.sh",
    "scripts/verify_complete.py",
    "scripts/verify_mosquito_intelligence_coverage.py",
    "scripts/build_literature_facets.py",
    "scripts/ingest_bold_barcodes.py",
    "scripts/ingest_inaturalist_observations.py",
    "scripts/ingest_pmc_videos.py",
    "scripts/ingest_irmapper.py",
    "scripts/ingest_who_malaria_threats_resistance.py",
    "scripts/ingest_mosquito_alert_observations.py",
    "scripts/ingest_vectornet_surveillance.py",
    "scripts/ingest_dryad_behavior_videos.py",
    "scripts/ingest_mendeley_behavior_media.py",
    "scripts/ingest_osf_flighttrackai_videos.py",
    "scripts/ingest_zenodo_aedes_videos.py",
    "scripts/ingest_figshare_aedes_videos.py",
    "scripts/ingest_public_health_guidance.py",
    "scripts/ingest_paho_dengue_surveillance.py",
    "scripts/ingest_who_dengue_surveillance.py",
    "scripts/ingest_cdc_dengue_surveillance.py",
    "scripts/ingest_ncvbdc_dengue_surveillance.py",
    "scripts/ingest_opendatasus_dengue_surveillance.py",
    "scripts/ingest_pathogen_taxonomy.py",
    "scripts/ingest_ncbi_biosamples.py",
    "scripts/ingest_ncbi_snp_variation.py",
    "scripts/ingest_vectorbase_genomics.py",
    "scripts/ingest_vector_competence_assays.py",
    "scripts/ingest_resistance_markers.py",
    "scripts/ingest_resistance_table_rows.py",
    "scripts/ingest_occurrence_ecology.py",
    "scripts/ingest_observation_climate.py",
    "scripts/ingest_extracted_facts.py",
    "scripts/ingest_expression_omics.py",
    "scripts/ingest_aedes_olfaction_literature.py",
    "scripts/ingest_aedes_crossref_literature_audit.py",
    "scripts/ingest_mosquito_repellent_literature.py",
    "scripts/ingest_mosquito_repellent_external_discovery.py",
    "scripts/ingest_literature_depth.py",
    "scripts/eval_production_path.py",
    "scripts/eval_repellency_comparison.py",
    "scripts/ingest_insect_intelligence_programs.py",
    "scripts/ingest_uniprot_proteins.py",
    "scripts/ingest_wolbachia_interventions.py",
    "scripts/ingest_vectorbyte_traits.py",
    "scripts/ingest_vectorbyte_abundance.py",
    "scripts/ingest_video_atoms.py",
    "scripts/ingest_image_atoms.py",
    "scripts/ingest_aedes_deep_sources.py",
    "scripts/ingest_drosophila_suzukii.py",
    "scripts/ingest_drosophila_suzukii_deep_sources.py",
    "scripts/ingest_drosophila_suzukii_extracted_facts.py",
    "scripts/ingest_drosophila_suzukii_literature_fulltext.py",
    "scripts/ingest_drosophila_suzukii_pubmed_literature.py",
    "scripts/ingest_drosophila_suzukii_genome_files.py",
    "scripts/ingest_drosophila_suzukii_ncbi_nucleotide.py",
    "scripts/ingest_drosophila_suzukii_ncbi_marker_review.py",
    "scripts/ingest_drosophila_suzukii_ncbi_snp_variation.py",
    "scripts/ingest_drosophila_suzukii_figshare_mk_selection.py",
    "scripts/ingest_drosophila_suzukii_population_genomics.py",
    "scripts/ingest_drosophila_suzukii_dryad_population_variants.py",
    "scripts/ingest_drosophila_suzukii_ncbi_gene_orthologs.py",
    "scripts/ingest_drosophila_suzukii_ensembl_metazoa_orthology.py",
    "scripts/ingest_drosophila_suzukii_geo_expression_matrices.py",
    "scripts/ingest_drosophila_suzukii_extension_guidance.py",
    "scripts/ingest_drosophila_suzukii_jki_drosomon_trap_captures.py",
    "scripts/ingest_drosophila_suzukii_osu_trap_reports.py",
    "scripts/ingest_drosophila_suzukii_dryad_landscape_monitoring.py",
    "scripts/ingest_drosophila_suzukii_umn_flight_assay_rows.py",
    "scripts/ingest_drosophila_suzukii_susceptibility_assay_rows.py",
    "scripts/ingest_drosophila_suzukii_biocontrol_outcome_rows.py",
    "scripts/ingest_drosophila_suzukii_video_atoms.py",
    "scripts/ingest_drosophila_suzukii_dryad_table_rows.py",
    "scripts/ingest_drosophila_suzukii_occurrence_ecology.py",
    "scripts/ingest_drosophila_suzukii_plos_climate_suitability.py",
    "scripts/ingest_harvard_dataverse_suitability.py",
    "scripts/refresh_artifact_receipts.py",
    "deploy/systemd/ask-insects.service",
    "tests/test_answer.py",
    "tests/test_builder.py",
    "tests/test_bold_barcode_source.py",
    "tests/test_cli.py",
    "tests/test_cli_hosted.py",
    "tests/test_deploy_files.py",
    "tests/test_fixture_source.py",
    "tests/test_gbif_source.py",
    "tests/test_hosted_client.py",
    "tests/test_inaturalist_source.py",
    "tests/test_literature_source.py",
    "tests/test_literature_enrichment.py",
    "tests/test_index.py",
    "tests/test_ncbi_genome_source.py",
    "tests/test_neurobiology_source.py",
    "tests/test_records.py",
    "tests/test_server.py",
    "tests/test_verify_complete.py",
    "tests/test_mosquito_intelligence_coverage.py",
    "tests/test_aedes_source_plane_benchmark.py",
    "tests/test_literature_facets.py",
    "tests/test_ingest_bold_barcodes.py",
    "tests/test_ingest_inaturalist_observations.py",
    "tests/test_ingest_pmc_videos.py",
    "tests/test_pmc_video_source.py",
    "tests/test_ingest_irmapper.py",
    "tests/test_irmapper_source.py",
    "tests/test_who_malaria_threats_resistance_source.py",
    "tests/test_ingest_who_malaria_threats_resistance.py",
    "tests/test_mosquito_alert_source.py",
    "tests/test_ingest_mosquito_alert_observations.py",
    "tests/test_vectornet_surveillance_source.py",
    "tests/test_ingest_vectornet_surveillance.py",
    "tests/test_dryad_behavior_videos_source.py",
    "tests/test_ingest_dryad_behavior_videos.py",
    "tests/test_mendeley_behavior_media_source.py",
    "tests/test_ingest_mendeley_behavior_media.py",
    "tests/test_osf_flighttrackai_videos_source.py",
    "tests/test_ingest_osf_flighttrackai_videos.py",
    "tests/test_zenodo_aedes_videos_source.py",
    "tests/test_ingest_zenodo_aedes_videos.py",
    "tests/test_figshare_aedes_videos_source.py",
    "tests/test_ingest_figshare_aedes_videos.py",
    "tests/test_public_health_source.py",
    "tests/test_ingest_public_health_guidance.py",
    "tests/test_paho_surveillance_source.py",
    "tests/test_ingest_paho_dengue_surveillance.py",
    "tests/test_who_dengue_surveillance_source.py",
    "tests/test_ingest_who_dengue_surveillance.py",
    "tests/test_cdc_dengue_surveillance_source.py",
    "tests/test_ingest_cdc_dengue_surveillance.py",
    "tests/test_ncvbdc_dengue_surveillance_source.py",
    "tests/test_ingest_ncvbdc_dengue_surveillance.py",
    "tests/test_opendatasus_dengue_surveillance_source.py",
    "tests/test_ingest_opendatasus_dengue_surveillance.py",
    "tests/test_pathogen_taxonomy_source.py",
    "tests/test_ingest_pathogen_taxonomy.py",
    "tests/test_ncbi_biosample_source.py",
    "tests/test_ingest_ncbi_biosamples.py",
    "tests/test_ncbi_snp_variation_source.py",
    "tests/test_ingest_ncbi_snp_variation.py",
    "tests/test_vectorbase_genomics_source.py",
    "tests/test_ingest_vectorbase_genomics.py",
    "tests/test_vector_competence_assays_source.py",
    "tests/test_ingest_vector_competence_assays.py",
    "tests/test_resistance_markers_source.py",
    "tests/test_ingest_resistance_markers.py",
    "tests/test_resistance_table_rows_source.py",
    "tests/test_ingest_resistance_table_rows.py",
    "tests/test_occurrence_ecology_source.py",
    "tests/test_ingest_occurrence_ecology.py",
    "tests/test_observation_climate_source.py",
    "tests/test_ingest_observation_climate.py",
    "tests/test_extracted_facts_source.py",
    "tests/test_ingest_extracted_facts.py",
    "tests/test_expression_omics_source.py",
    "tests/test_aedes_olfaction_literature_source.py",
    "tests/test_ingest_aedes_olfaction_literature.py",
    "tests/test_aedes_crossref_literature_audit_source.py",
    "tests/test_ingest_aedes_crossref_literature_audit.py",
    "tests/test_mosquito_repellent_literature_source.py",
    "tests/test_ingest_mosquito_repellent_literature.py",
    "tests/test_mosquito_repellent_external_discovery_source.py",
    "tests/test_ingest_mosquito_repellent_external_discovery.py",
    "tests/test_literature_depth_profiles.py",
    "tests/test_ingest_literature_depth.py",
    "tests/test_repellency_comparison.py",
    "tests/test_production_path_eval.py",
    "tests/test_agent_setup.py",
    "tests/test_insect_intelligence_programs.py",
    "tests/test_context_package.py",
    "tests/test_uniprot_proteins_source.py",
    "tests/test_wolbachia_interventions_source.py",
    "tests/test_vectorbyte_traits_source.py",
    "tests/test_ingest_vectorbyte_traits.py",
    "tests/test_vectorbyte_abundance_source.py",
    "tests/test_ingest_vectorbyte_abundance.py",
    "tests/test_ingest_wave1_sources.py",
    "tests/test_video_atoms_source.py",
    "tests/test_ingest_video_atoms.py",
    "tests/test_image_atoms_source.py",
    "tests/test_ingest_image_atoms.py",
    "tests/test_aedes_deep_sources.py",
    "tests/test_ingest_aedes_deep_sources.py",
    "tests/test_drosophila_suzukii_source.py",
    "tests/test_ingest_drosophila_suzukii.py",
    "tests/test_drosophila_suzukii_deep_sources.py",
    "tests/test_ingest_drosophila_suzukii_deep_sources.py",
    "tests/test_drosophila_suzukii_extracted_facts.py",
    "tests/test_ingest_drosophila_suzukii_extracted_facts.py",
    "tests/test_ingest_drosophila_suzukii_literature_fulltext.py",
    "tests/test_drosophila_suzukii_pubmed_literature_source.py",
    "tests/test_ingest_drosophila_suzukii_pubmed_literature.py",
    "tests/test_drosophila_suzukii_genome_files.py",
    "tests/test_ingest_drosophila_suzukii_genome_files.py",
    "tests/test_drosophila_suzukii_ncbi_nucleotide_source.py",
    "tests/test_ingest_drosophila_suzukii_ncbi_nucleotide.py",
    "tests/test_drosophila_suzukii_ncbi_marker_review_source.py",
    "tests/test_ingest_drosophila_suzukii_ncbi_marker_review.py",
    "tests/test_drosophila_suzukii_ncbi_snp_variation_source.py",
    "tests/test_ingest_drosophila_suzukii_ncbi_snp_variation.py",
    "tests/test_drosophila_suzukii_ncbi_gene_orthologs_source.py",
    "tests/test_ingest_drosophila_suzukii_ncbi_gene_orthologs.py",
    "tests/test_drosophila_suzukii_ensembl_metazoa_orthology_source.py",
    "tests/test_ingest_drosophila_suzukii_ensembl_metazoa_orthology.py",
    "tests/test_drosophila_suzukii_geo_expression_matrices_source.py",
    "tests/test_ingest_drosophila_suzukii_geo_expression_matrices.py",
    "tests/test_drosophila_suzukii_extension_guidance.py",
    "tests/test_ingest_drosophila_suzukii_extension_guidance.py",
    "tests/test_drosophila_suzukii_jki_drosomon_trap_captures_source.py",
    "tests/test_ingest_drosophila_suzukii_jki_drosomon_trap_captures.py",
    "tests/test_drosophila_suzukii_osu_trap_reports_source.py",
    "tests/test_ingest_drosophila_suzukii_osu_trap_reports.py",
    "tests/test_drosophila_suzukii_dryad_landscape_monitoring_source.py",
    "tests/test_ingest_drosophila_suzukii_dryad_landscape_monitoring.py",
    "tests/test_drosophila_suzukii_umn_flight_assay_rows_source.py",
    "tests/test_ingest_drosophila_suzukii_umn_flight_assay_rows.py",
    "tests/test_drosophila_suzukii_susceptibility_assay_rows.py",
    "tests/test_ingest_drosophila_suzukii_susceptibility_assay_rows.py",
    "tests/test_drosophila_suzukii_biocontrol_outcome_rows.py",
    "tests/test_ingest_drosophila_suzukii_biocontrol_outcome_rows.py",
    "tests/test_drosophila_suzukii_video_atoms.py",
    "tests/test_ingest_drosophila_suzukii_video_atoms.py",
    "tests/test_drosophila_suzukii_dryad_table_rows.py",
    "tests/test_ingest_drosophila_suzukii_dryad_table_rows.py",
    "tests/test_drosophila_suzukii_occurrence_ecology.py",
    "tests/test_ingest_drosophila_suzukii_occurrence_ecology.py",
    "tests/test_drosophila_suzukii_plos_climate_suitability_source.py",
    "tests/test_ingest_drosophila_suzukii_plos_climate_suitability.py",
    "tests/test_harvard_dataverse_suitability_source.py",
    "tests/test_ingest_harvard_dataverse_suitability.py",
    "tests/test_refresh_artifact_receipts.py",
)

UNIT_TEST_MODULES = (
    "tests.test_answer",
    "tests.test_agent_setup",
    "tests.test_builder",
    "tests.test_bold_barcode_source",
    "tests.test_cli",
    "tests.test_cli_hosted",
    "tests.test_deploy_files",
    "tests.test_fixture_source",
    "tests.test_gbif_source",
    "tests.test_hosted_client",
    "tests.test_inaturalist_source",
    "tests.test_literature_source",
    "tests.test_literature_enrichment",
    "tests.test_index",
    "tests.test_ncbi_genome_source",
    "tests.test_neurobiology_source",
    "tests.test_records",
    "tests.test_server",
    "tests.test_mosquito_intelligence_coverage",
    "tests.test_aedes_source_plane_benchmark",
    "tests.test_literature_facets",
    "tests.test_ingest_bold_barcodes",
    "tests.test_ingest_inaturalist_observations",
    "tests.test_ingest_pmc_videos",
    "tests.test_pmc_video_source",
    "tests.test_ingest_irmapper",
    "tests.test_irmapper_source",
    "tests.test_who_malaria_threats_resistance_source",
    "tests.test_ingest_who_malaria_threats_resistance",
    "tests.test_mosquito_alert_source",
    "tests.test_ingest_mosquito_alert_observations",
    "tests.test_vectornet_surveillance_source",
    "tests.test_ingest_vectornet_surveillance",
    "tests.test_dryad_behavior_videos_source",
    "tests.test_ingest_dryad_behavior_videos",
    "tests.test_mendeley_behavior_media_source",
    "tests.test_ingest_mendeley_behavior_media",
    "tests.test_osf_flighttrackai_videos_source",
    "tests.test_ingest_osf_flighttrackai_videos",
    "tests.test_zenodo_aedes_videos_source",
    "tests.test_ingest_zenodo_aedes_videos",
    "tests.test_figshare_aedes_videos_source",
    "tests.test_ingest_figshare_aedes_videos",
    "tests.test_public_health_source",
    "tests.test_ingest_public_health_guidance",
    "tests.test_paho_surveillance_source",
    "tests.test_ingest_paho_dengue_surveillance",
    "tests.test_who_dengue_surveillance_source",
    "tests.test_ingest_who_dengue_surveillance",
    "tests.test_cdc_dengue_surveillance_source",
    "tests.test_ingest_cdc_dengue_surveillance",
    "tests.test_ncvbdc_dengue_surveillance_source",
    "tests.test_ingest_ncvbdc_dengue_surveillance",
    "tests.test_opendatasus_dengue_surveillance_source",
    "tests.test_ingest_opendatasus_dengue_surveillance",
    "tests.test_pathogen_taxonomy_source",
    "tests.test_ingest_pathogen_taxonomy",
    "tests.test_ncbi_biosample_source",
    "tests.test_ingest_ncbi_biosamples",
    "tests.test_ncbi_snp_variation_source",
    "tests.test_ingest_ncbi_snp_variation",
    "tests.test_vectorbase_genomics_source",
    "tests.test_ingest_vectorbase_genomics",
    "tests.test_vector_competence_assays_source",
    "tests.test_ingest_vector_competence_assays",
    "tests.test_resistance_markers_source",
    "tests.test_ingest_resistance_markers",
    "tests.test_resistance_table_rows_source",
    "tests.test_ingest_resistance_table_rows",
    "tests.test_occurrence_ecology_source",
    "tests.test_ingest_occurrence_ecology",
    "tests.test_observation_climate_source",
    "tests.test_ingest_observation_climate",
    "tests.test_extracted_facts_source",
    "tests.test_ingest_extracted_facts",
    "tests.test_expression_omics_source",
    "tests.test_aedes_olfaction_literature_source",
    "tests.test_ingest_aedes_olfaction_literature",
    "tests.test_mosquito_repellent_literature_source",
    "tests.test_ingest_mosquito_repellent_literature",
    "tests.test_mosquito_repellent_external_discovery_source",
    "tests.test_ingest_mosquito_repellent_external_discovery",
    "tests.test_literature_depth_profiles",
    "tests.test_ingest_literature_depth",
    "tests.test_repellency_comparison",
    "tests.test_insect_intelligence_programs",
    "tests.test_context_package",
    "tests.test_wheel_resources",
    "tests.test_uniprot_proteins_source",
    "tests.test_wolbachia_interventions_source",
    "tests.test_ingest_wave1_sources",
    "tests.test_video_atoms_source",
    "tests.test_ingest_video_atoms",
    "tests.test_image_atoms_source",
    "tests.test_ingest_image_atoms",
    "tests.test_aedes_deep_sources",
    "tests.test_ingest_aedes_deep_sources",
    "tests.test_drosophila_suzukii_source",
    "tests.test_ingest_drosophila_suzukii",
    "tests.test_drosophila_suzukii_deep_sources",
    "tests.test_ingest_drosophila_suzukii_deep_sources",
    "tests.test_drosophila_suzukii_extracted_facts",
    "tests.test_ingest_drosophila_suzukii_extracted_facts",
    "tests.test_ingest_drosophila_suzukii_literature_fulltext",
    "tests.test_drosophila_suzukii_pubmed_literature_source",
    "tests.test_ingest_drosophila_suzukii_pubmed_literature",
    "tests.test_drosophila_suzukii_genome_files",
    "tests.test_ingest_drosophila_suzukii_genome_files",
    "tests.test_drosophila_suzukii_ncbi_nucleotide_source",
    "tests.test_ingest_drosophila_suzukii_ncbi_nucleotide",
    "tests.test_drosophila_suzukii_ncbi_marker_review_source",
    "tests.test_ingest_drosophila_suzukii_ncbi_marker_review",
    "tests.test_drosophila_suzukii_ncbi_snp_variation_source",
    "tests.test_ingest_drosophila_suzukii_ncbi_snp_variation",
    "tests.test_drosophila_suzukii_figshare_mk_selection_source",
    "tests.test_ingest_drosophila_suzukii_figshare_mk_selection",
    "tests.test_drosophila_suzukii_population_genomics_source",
    "tests.test_ingest_drosophila_suzukii_population_genomics",
    "tests.test_drosophila_suzukii_dryad_population_variants_source",
    "tests.test_ingest_drosophila_suzukii_dryad_population_variants",
    "tests.test_drosophila_suzukii_ncbi_gene_orthologs_source",
    "tests.test_ingest_drosophila_suzukii_ncbi_gene_orthologs",
    "tests.test_drosophila_suzukii_ensembl_metazoa_orthology_source",
    "tests.test_ingest_drosophila_suzukii_ensembl_metazoa_orthology",
    "tests.test_drosophila_suzukii_geo_expression_matrices_source",
    "tests.test_ingest_drosophila_suzukii_geo_expression_matrices",
    "tests.test_drosophila_suzukii_extension_guidance",
    "tests.test_ingest_drosophila_suzukii_extension_guidance",
    "tests.test_drosophila_suzukii_jki_drosomon_trap_captures_source",
    "tests.test_ingest_drosophila_suzukii_jki_drosomon_trap_captures",
    "tests.test_drosophila_suzukii_osu_trap_reports_source",
    "tests.test_ingest_drosophila_suzukii_osu_trap_reports",
    "tests.test_drosophila_suzukii_dryad_landscape_monitoring_source",
    "tests.test_ingest_drosophila_suzukii_dryad_landscape_monitoring",
    "tests.test_drosophila_suzukii_umn_flight_assay_rows_source",
    "tests.test_ingest_drosophila_suzukii_umn_flight_assay_rows",
    "tests.test_drosophila_suzukii_video_atoms",
    "tests.test_ingest_drosophila_suzukii_video_atoms",
    "tests.test_drosophila_suzukii_dryad_table_rows",
    "tests.test_ingest_drosophila_suzukii_dryad_table_rows",
    "tests.test_drosophila_suzukii_occurrence_ecology",
    "tests.test_ingest_drosophila_suzukii_occurrence_ecology",
    "tests.test_drosophila_suzukii_plos_climate_suitability_source",
    "tests.test_ingest_drosophila_suzukii_plos_climate_suitability",
    "tests.test_harvard_dataverse_suitability_source",
    "tests.test_ingest_harvard_dataverse_suitability",
    "tests.test_refresh_artifact_receipts",
    "tests.test_gaps",
    "tests.test_planner_routing",
    "tests.test_aedes_crossref_literature_audit_source",
    "tests.test_ingest_aedes_crossref_literature_audit",
    "tests.test_drosophila_suzukii_biocontrol_outcome_rows",
    "tests.test_ingest_drosophila_suzukii_biocontrol_outcome_rows",
    "tests.test_drosophila_suzukii_susceptibility_assay_rows",
    "tests.test_ingest_drosophila_suzukii_susceptibility_assay_rows",
    "tests.test_vectorbyte_abundance_source",
    "tests.test_ingest_vectorbyte_abundance",
    "tests.test_vectorbyte_traits_source",
    "tests.test_ingest_vectorbyte_traits",
    "tests.test_source_coverage",
    "tests.test_prune_literature_gaps",
    "tests.test_merge_literature_artifact",
    "tests.test_relocate_artifact_paths",
    "tests.test_species",
    "tests.test_ingest_runner",
    "tests.test_ingest_parity",
)


def fail(message: str) -> int:
    print(f"verify_complete failed: {message}", file=sys.stderr)
    return 1


def run_command(args: list[str], *, expected_returncode: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=REPO_ROOT, env=VERIFY_ENV, capture_output=True, text=True)
    if result.returncode != expected_returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{' '.join(args)} exited {result.returncode}: {detail}")
    return result


def run_json(args: list[str], *, expected_returncode: int = 0) -> dict[str, object]:
    result = run_command(args, expected_returncode=expected_returncode)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{' '.join(args)} did not return JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{' '.join(args)} returned non-object JSON")
    return payload


def check_required_files() -> None:
    missing = [path for path in REQUIRED_FILES if not (REPO_ROOT / path).is_file()]
    if missing:
        raise RuntimeError(f"missing required file(s): {', '.join(missing)}")


def check_forbidden_files(repo_root: Path = REPO_ROOT) -> None:
    present = [path for path in FORBIDDEN_FILES if (repo_root / path).exists()]
    if present:
        raise RuntimeError(f"deleted config or file is still present: {', '.join(present)}")


def validate_generic_evidence_config(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise RuntimeError("generic evidence config must be a JSON object")
    expected_fields = {
        "schema_version",
        "package_version",
        "last_reviewed",
        "objective",
        "knowledge_domains",
        "contexts",
        "selector_approvals",
    }
    if set(payload) != expected_fields:
        raise RuntimeError("generic evidence config must use exact top-level fields")
    if payload.get("schema_version") != GENERIC_CONFIG_SCHEMA_VERSION:
        raise RuntimeError(f"generic evidence config must use schema v2: {GENERIC_CONFIG_SCHEMA_VERSION}")
    contexts = payload.get("contexts")
    if not isinstance(contexts, list) or not contexts or not all(isinstance(item, dict) for item in contexts):
        raise RuntimeError("generic evidence config contexts must be a non-empty list of objects")
    context_ids = [str(context.get("id") or "") for context in contexts]
    if tuple(context_ids) != GENERIC_CONTEXT_IDS:
        raise RuntimeError("generic evidence config does not declare the complete generic context inventory")
    selector_ids: list[str] = []
    for context in contexts:
        context_id = str(context.get("id") or "<missing>")
        if set(context) != GENERIC_CONFIG_CONTEXT_FIELDS:
            raise RuntimeError(f"context {context_id} must use exact generic context fields")
        for field in (
            "endpoint_family",
            "exposure_routes",
            "species_ids",
            "required_domains",
            "measures",
            "does_not_establish",
            "plausible_explanations",
            "discriminating_evidence",
        ):
            value = context.get(field)
            if field == "endpoint_family":
                valid = isinstance(value, str) and bool(value.strip())
            else:
                valid = isinstance(value, list) and bool(value)
            if not valid:
                raise RuntimeError(f"generic context {context_id} has invalid {field}")
        selectors = context.get("selectors")
        if not isinstance(selectors, list) or not selectors or not all(
            isinstance(selector, dict) for selector in selectors
        ):
            raise RuntimeError(f"generic context {context_id} must declare selector objects")
        for selector in selectors:
            required = {
                "id",
                "species_id",
                "context_required_term_groups",
                "taxon_field_paths",
                "context_field_paths",
            }
            if not required.issubset(selector):
                raise RuntimeError(f"generic context {context_id} selector is missing direct-evidence fields")
            selector_id = selector.get("id")
            if not isinstance(selector_id, str) or not selector_id.strip():
                raise RuntimeError(f"generic context {context_id} selector has an invalid id")
            selector_ids.append(selector_id)
    if len(selector_ids) != len(set(selector_ids)):
        raise RuntimeError("generic evidence config selector ids must be unique")
    approvals = payload.get("selector_approvals")
    if not isinstance(approvals, dict) or set(approvals) != set(selector_ids):
        raise RuntimeError("generic evidence config approvals must cover every selector exactly")
    for selector_id, record_ids in approvals.items():
        if (
            not isinstance(record_ids, list)
            or len(record_ids) != len(set(record_ids))
            or not all(isinstance(record_id, str) and record_id for record_id in record_ids)
        ):
            raise RuntimeError(
                f"generic evidence config approval list is invalid for selector {selector_id}"
            )
    return payload


def check_generic_evidence_config(repo_root: Path = REPO_ROOT) -> None:
    config_path = repo_root / GENERIC_CONFIG_PATH
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"generic evidence config is not readable JSON: {exc}") from exc
    validate_generic_evidence_config(payload)
    if repo_root.resolve() == REPO_ROOT.resolve():
        from askinsects.context_package import (
            CONFIG_SCHEMA_VERSION,
            DEFAULT_CONTEXT_CONFIG,
            load_context_config,
        )

        if CONFIG_SCHEMA_VERSION != GENERIC_CONFIG_SCHEMA_VERSION:
            raise RuntimeError("context package runtime does not declare config schema v2")
        if DEFAULT_CONTEXT_CONFIG.resolve() != config_path.resolve():
            raise RuntimeError("context package runtime does not load the generic config path")
        validate_generic_evidence_config(load_context_config(config_path))


def _active_public_surface_paths(repo_root: Path) -> list[Path]:
    paths: set[Path] = set()
    for relative in ACTIVE_PUBLIC_SURFACE_FILES:
        path = repo_root / relative
        if path.is_file():
            paths.add(path)
    for relative in ACTIVE_PUBLIC_SURFACE_DIRS:
        root = repo_root / relative
        if not root.is_dir():
            continue
        paths.update(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.casefold() in ACTIVE_TEXT_SUFFIXES
        )
    return sorted(paths)


def check_active_public_surfaces(repo_root: Path = REPO_ROOT) -> None:
    offenders: list[str] = []
    for path in _active_public_surface_paths(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(repo_root).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            if CONSUMER_NAME_RE.search(line):
                offenders.append(f"{relative}:{line_number}: consumer-specific name or identifier")
    if offenders:
        preview = "; ".join(offenders[:12])
        suffix = f"; and {len(offenders) - 12} more" if len(offenders) > 12 else ""
        raise RuntimeError(f"active public surface contains consumer coupling: {preview}{suffix}")


def _run_clean_clone_command(
    clone_root: Path,
    env: dict[str, str],
    args: list[str],
    *,
    label: str,
) -> None:
    result = subprocess.run(
        args,
        cwd=clone_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"clean public clone {label} failed: {detail}")


def check_clean_clone_independence(repo_root: Path = REPO_ROOT) -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if tracked.returncode != 0:
        raise RuntimeError(f"clean public clone could not list tracked files: {tracked.stderr.strip()}")
    relative_paths = [Path(value) for value in tracked.stdout.split("\0") if value]
    if not relative_paths:
        raise RuntimeError("clean public clone has no tracked files")

    with tempfile.TemporaryDirectory(prefix="ask-insects-public-clone-") as tmpdir:
        temp_root = Path(tmpdir)
        clone_root = temp_root / "clone"
        home = temp_root / "home"
        clone_root.mkdir()
        home.mkdir()
        for relative in relative_paths:
            source = repo_root / relative
            if not source.is_file():
                continue
            destination = clone_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination, follow_symlinks=False)

        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"LANG", "LC_ALL", "PATH", "TMPDIR"}
        }
        env.update(
            {
                "HOME": home.as_posix(),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            }
        )
        import_probe = """
import os
from pathlib import Path
import askinsects
from askinsects.context_package import (
    DEFAULT_CONTEXT_CONFIG,
    DEFAULT_PUBLISHED_PACKAGE,
    load_context_config,
    load_published_context_package,
)

assert not any(key.startswith("ASK_INSECTS_") for key in os.environ)
assert Path(askinsects.__file__).resolve().is_relative_to(Path.cwd().resolve())
assert DEFAULT_CONTEXT_CONFIG.resolve() == (Path.cwd() / "config/insect-evidence-package.json").resolve()
assert load_context_config()["schema_version"] == "ask-insects-evidence-package-config.v2"
assert DEFAULT_PUBLISHED_PACKAGE.resolve() == (
    Path.cwd() / "public/evidence-packages/ask-insects-evidence-package-2026-07-14.7.json"
).resolve()
assert load_published_context_package()["package_version"] == "2026-07-14.7"
assert not (Path.cwd() / "artifacts/mosquito-v1/source_index.sqlite").exists()
"""
        _run_clean_clone_command(
            clone_root,
            env,
            [sys.executable, "-c", import_probe],
            label="import/config probe",
        )
        fixture_tests = [
            "tests.test_context_package.ContextPackageTests.test_default_config_uses_generic_v2_contract",
            "tests.test_context_package.ContextPackageTests.test_selector_receipt_counts_all_rejections",
            "tests.test_context_package.ContextPackageTests.test_package_declares_producer_and_downstream_validation_boundary",
            "tests.test_context_package.ContextPackageTests.test_validator_rejects_exported_contexts_with_private_fields",
            "tests.test_context_package.ContextPackageTests.test_default_published_package_is_the_exact_public_release",
        ]
        _run_clean_clone_command(
            clone_root,
            env,
            [sys.executable, "-m", "unittest", "-q", *fixture_tests],
            label="fixture-backed package tests",
        )


def _validate_public_value(value: object, *, path: str = "$", depth: int = 0) -> None:
    if depth > MAX_PUBLIC_PACKAGE_DEPTH:
        raise RuntimeError(f"public package exceeds nesting depth at {path}")
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise RuntimeError(f"public package contains a non-string key at {path}")
            if len(key) > MAX_PUBLIC_PACKAGE_STRING_LENGTH:
                raise RuntimeError(f"public package exceeds key length at {path}")
            if _is_credential_key(key):
                raise RuntimeError(f"public package contains credential-shaped key at {path}.{key}")
            if _is_consumer_key(key):
                raise RuntimeError(f"public package contains consumer-specific key at {path}.{key}")
            if _is_machine_bookkeeping_key(key):
                raise RuntimeError(f"public package contains machine-local key at {path}.{key}")
            _validate_public_value(nested, path=f"{path}.{key}", depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > MAX_PUBLIC_PACKAGE_LIST_ITEMS:
            raise RuntimeError(f"public package list is too large at {path}")
        for index, nested in enumerate(value):
            _validate_public_value(nested, path=f"{path}/{index}", depth=depth + 1)
        return
    if isinstance(value, str):
        if len(value) > MAX_PUBLIC_PACKAGE_STRING_LENGTH:
            raise RuntimeError(f"public package exceeds string length at {path}")
        if SECRET_VALUE_RE.search(value):
            raise RuntimeError(f"public package contains a credential or bearer token at {path}")
        if any(
            _url_has_credentials(match.group(0).rstrip(".,);]"))
            for match in PUBLIC_URL_RE.finditer(value)
        ):
            raise RuntimeError(f"public package contains a credentialed URL at {path}")
        if NON_PUBLIC_LOCATOR_RE.search(value):
            raise RuntimeError(f"public package contains a non-public scheme at {path}")
        if ABSOLUTE_FILESYSTEM_PATH_RE.search(value):
            raise RuntimeError(f"public package contains a local or private path at {path}")


def _key_tokens(key: str) -> list[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return [token for token in re.split(r"[^A-Za-z0-9]+", expanded.casefold()) if token]


def _is_credential_key(key: str) -> bool:
    if key.casefold() == "snapshot_authentication":
        return False
    tokens = _key_tokens(key)
    return any(token in CREDENTIAL_KEY_TOKENS for token in tokens) or any(
        left == "api" and right == "key" for left, right in zip(tokens, tokens[1:])
    )


def _is_consumer_key(key: str) -> bool:
    return bool(set(_key_tokens(key)).intersection(CONSUMER_KEY_TOKENS))


def _is_credential_query_key(key: str) -> bool:
    return _is_credential_key(key) or bool(
        set(_key_tokens(key)).intersection(QUERY_CREDENTIAL_KEY_TOKENS)
    )


def _url_has_credentials(value: str) -> bool:
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        return True
    return any(
        _is_credential_query_key(key)
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    )


def _is_machine_bookkeeping_key(key: str) -> bool:
    tokens = set(_key_tokens(key))
    if key.casefold() in {"payload_json", "provenance_json"}:
        return True
    if "path" in tokens and tokens.intersection(
        {"artifact", "cache", "ledger", "local", "machine", "raw"}
    ):
        return True
    return bool(
        tokens.intersection({"original", "raw", "internal"})
        and tokens.intersection({"payload", "provenance"})
    )


def _canonical_public_package_bytes(value: object) -> bytes:
    try:
        serialized = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"public package is not canonical JSON: {exc}") from exc
    return serialized.encode("utf-8")


def _validate_public_package_size(value: object) -> None:
    if len(_canonical_public_package_bytes(value)) > MAX_PUBLIC_PACKAGE_BYTES:
        raise RuntimeError("public evidence package exceeds package byte limit")


def _check_producer_limit_alignment() -> None:
    from askinsects import context_package

    expected = {
        "MAX_PACKAGE_BYTES": MAX_PUBLIC_PACKAGE_BYTES,
        "MAX_STRING_LENGTH": MAX_PUBLIC_PACKAGE_STRING_LENGTH,
        "MAX_LIST_ITEMS": MAX_PUBLIC_PACKAGE_LIST_ITEMS,
        "MAX_NESTING_DEPTH": MAX_PUBLIC_PACKAGE_DEPTH,
    }
    mismatches = [
        f"{name}={getattr(context_package, name, '<missing>')!r}, expected {value!r}"
        for name, value in expected.items()
        if getattr(context_package, name, None) != value
    ]
    if mismatches:
        raise RuntimeError(
            "completion gate resource limits do not match the producer: "
            + "; ".join(mismatches)
        )


def _object_list(package: dict[str, object], field: str, *, allow_empty: bool = True) -> list[dict[str, object]]:
    value = package.get(field)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError(f"public package {field} must be a list of objects")
    if not allow_empty and not value:
        raise RuntimeError(f"public package {field} must not be empty")
    return value


def _validate_public_https_provenance(item: dict[str, object], *, label: str) -> None:
    provenance = item.get("provenance")
    if not isinstance(provenance, dict):
        raise RuntimeError(f"{label} must declare provenance")
    source_id = provenance.get("source_id")
    locator = provenance.get("locator")
    if not isinstance(source_id, str) or not source_id.strip():
        raise RuntimeError(f"{label} provenance must declare source_id")
    if not isinstance(locator, str) or not locator.strip():
        raise RuntimeError(f"{label} provenance must declare a stable public HTTPS locator")
    parsed = urlsplit(locator)
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or not hostname
        or hostname == "localhost"
        or hostname.endswith((".localhost", ".local"))
    ):
        raise RuntimeError(f"{label} provenance is not a stable public HTTPS locator")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise RuntimeError(f"{label} provenance is not a stable public HTTPS locator")


def _validate_direct_assertion(value: object, *, label: str, status: str) -> None:
    if not isinstance(value, dict) or value.get("status") != status:
        readable = "direct focal taxon" if status == "direct_focal_taxon" else "direct context"
        raise RuntimeError(f"{label} must contain a {readable} assertion")
    basis = value.get("basis")
    if not isinstance(basis, list) or not basis or not all(isinstance(item, dict) for item in basis):
        raise RuntimeError(f"{label} direct assertion must contain basis objects")
    for item in basis:
        for field in ("field_path", "matched_term", "excerpt"):
            if not isinstance(item.get(field), str) or not str(item[field]).strip():
                raise RuntimeError(f"{label} direct assertion basis is missing {field}")


def validate_public_evidence_package(
    package: object,
    *,
    require_complete_contexts: bool = False,
) -> dict[str, object]:
    if not isinstance(package, dict):
        raise RuntimeError("public evidence package must be a JSON object")
    _validate_public_value(package)
    _validate_public_package_size(package)
    if set(package) != PUBLIC_PACKAGE_FIELDS:
        raise RuntimeError("public evidence package must use exact top-level fields")
    if package.get("schema_version") != PUBLIC_PACKAGE_SCHEMA_VERSION:
        raise RuntimeError(f"public evidence package must use schema v3: {PUBLIC_PACKAGE_SCHEMA_VERSION}")
    if package.get("validation_contract") != PUBLIC_VALIDATION_CONTRACT:
        raise RuntimeError("public evidence package validation_contract is invalid")
    if package.get("ok") is not True:
        raise RuntimeError("public evidence package must report ok true")

    configuration_sources = package.get("configuration_sources")
    if not isinstance(configuration_sources, dict) or set(configuration_sources) != {
        "context_config",
        "program_config",
    }:
        raise RuntimeError("public evidence package configuration sources are invalid")
    for source_name, source in configuration_sources.items():
        if not isinstance(source, dict) or set(source) != {"source_url", "sha256"}:
            raise RuntimeError(
                f"public evidence package {source_name} configuration source is invalid"
            )
        source_url = source.get("source_url")
        digest = source.get("sha256")
        if not isinstance(source_url, str) or urlsplit(source_url).fragment:
            raise RuntimeError(
                f"public evidence package {source_name} configuration URL is invalid"
            )
        _validate_public_https_provenance(
            {
                "provenance": {
                    "source_id": f"ask_insects_{source_name}",
                    "locator": source_url,
                }
            },
            label=f"{source_name} configuration source",
        )
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise RuntimeError(
                f"public evidence package {source_name} configuration hash is invalid"
            )

    contexts = _object_list(package, "contexts", allow_empty=False)
    context_ids: list[str] = []
    for context in contexts:
        context_id = str(context.get("id") or "<missing>")
        context_ids.append(context_id)
        if set(context) != PUBLIC_CONTEXT_FIELDS:
            raise RuntimeError(f"context {context_id} must use exact generic context fields")
        _validate_public_https_provenance(context, label=f"context {context_id}")
    if len(context_ids) != len(set(context_ids)):
        raise RuntimeError("public evidence package context ids must be unique")
    if require_complete_contexts and tuple(context_ids) != GENERIC_CONTEXT_IDS:
        raise RuntimeError("public evidence package does not contain every generic context")

    program_records = _object_list(package, "program_records", allow_empty=False)
    for record in program_records:
        record_id = str(record.get("record_id") or "<missing>")
        _validate_public_https_provenance(record, label=f"program record {record_id}")

    evidence_records = _object_list(package, "evidence_records", allow_empty=False)
    evidence_ids: set[str] = set()
    for record in evidence_records:
        record_id = str(record.get("record_id") or "")
        if not record_id or record_id in evidence_ids:
            raise RuntimeError("public evidence package evidence record ids must be unique and non-empty")
        evidence_ids.add(record_id)
        _validate_public_https_provenance(record, label=f"evidence record {record_id}")
        eligibility = record.get("eligibility")
        if not isinstance(eligibility, dict):
            raise RuntimeError(f"evidence record {record_id} is missing direct eligibility assertions")
        if eligibility.get("ruleset_version") != DIRECT_EVIDENCE_RULESET_VERSION:
            raise RuntimeError(f"evidence record {record_id} has the wrong direct-evidence ruleset")
        _validate_direct_assertion(
            eligibility.get("taxon"),
            label=f"evidence record {record_id}",
            status="direct_focal_taxon",
        )
        _validate_direct_assertion(
            eligibility.get("context"),
            label=f"evidence record {record_id}",
            status="direct_context",
        )

    selector_results = _object_list(package, "selector_results", allow_empty=False)
    selected_ids: set[str] = set()
    selector_ids: set[str] = set()
    for result in selector_results:
        selector_id = str(result.get("selector_id") or "")
        if not selector_id or selector_id in selector_ids:
            raise RuntimeError("selector rejection receipts must have unique non-empty selector ids")
        selector_ids.add(selector_id)
        counts: dict[str, int] = {}
        for field in ("candidate_count", "eligible_count", "selected_count"):
            value = result.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError(f"selector {selector_id} rejection receipt has invalid {field}")
            counts[field] = value
        rejection_counts = result.get("rejection_counts")
        if not isinstance(rejection_counts, dict) or any(
            not isinstance(reason, str)
            or not reason
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
            for reason, count in rejection_counts.items()
        ):
            raise RuntimeError(f"selector {selector_id} has an invalid rejection receipt")
        if counts["candidate_count"] != counts["eligible_count"] + sum(rejection_counts.values()):
            raise RuntimeError(f"selector {selector_id} rejection receipt is incomplete")
        ids = result.get("selected_record_ids")
        if (
            not isinstance(ids, list)
            or len(ids) != counts["selected_count"]
            or len(ids) != len(set(ids))
            or not all(isinstance(item, str) and item for item in ids)
            or counts["selected_count"] > counts["eligible_count"]
        ):
            raise RuntimeError(f"selector {selector_id} rejection receipt has invalid selected records")
        approved_ids = result.get("approved_record_ids")
        if (
            not isinstance(approved_ids, list)
            or len(approved_ids) != len(set(approved_ids))
            or not all(isinstance(item, str) and item for item in approved_ids)
        ):
            raise RuntimeError(f"selector {selector_id} has invalid approved records")
        if not set(ids).issubset(approved_ids):
            raise RuntimeError(f"selector {selector_id} selected records are not approved")
        selected_ids.update(ids)
    if selected_ids != evidence_ids:
        raise RuntimeError("selector rejection receipts do not exactly cover evidence records")

    _object_list(package, "gaps")
    content_hash = package.get("content_sha256")
    if not isinstance(content_hash, str) or re.fullmatch(r"[0-9a-f]{64}", content_hash) is None:
        raise RuntimeError("public evidence package content_sha256 is invalid")
    return package


def _check_exact_published_release(package: dict[str, object]) -> None:
    from askinsects.context_package import (
        DEFAULT_CONTEXT_CONFIG,
        DEFAULT_PROGRAM_CONFIG,
        DEFAULT_PUBLISHED_PACKAGE,
        DEFAULT_PUBLISHED_PACKAGE_SHA256,
        PUBLIC_CONTEXT_CONFIG_SHA256,
        PUBLIC_CONTEXT_CONFIG_URL,
        PUBLIC_PROGRAM_CONFIG_SHA256,
        PUBLIC_PROGRAM_CONFIG_URL,
    )
    from askinsects.sources.insect_intelligence_programs import (
        build_insect_intelligence_records,
    )

    expected_sources = {
        "context_config": {
            "source_url": PUBLIC_CONTEXT_CONFIG_URL,
            "sha256": PUBLIC_CONTEXT_CONFIG_SHA256,
        },
        "program_config": {
            "source_url": PUBLIC_PROGRAM_CONFIG_URL,
            "sha256": PUBLIC_PROGRAM_CONFIG_SHA256,
        },
    }
    if package.get("package_version") != "2026-07-14.7":
        raise RuntimeError("published evidence package has the wrong release version")
    if package.get("content_sha256") != (
        "48f4013118f9f32ea4466790d0e4ff266db12d21c3a476c185986e85fbde8d55"
    ):
        raise RuntimeError("published evidence package has the wrong content hash")
    if hashlib.sha256(DEFAULT_PUBLISHED_PACKAGE.read_bytes()).hexdigest() != (
        DEFAULT_PUBLISHED_PACKAGE_SHA256
    ):
        raise RuntimeError("published evidence package has the wrong file hash")
    if package.get("configuration_sources") != expected_sources:
        raise RuntimeError("published evidence package configuration sources do not match runtime pins")
    for path, source_name in (
        (DEFAULT_CONTEXT_CONFIG, "context_config"),
        (DEFAULT_PROGRAM_CONFIG, "program_config"),
    ):
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected_sources[source_name]["sha256"]:
            raise RuntimeError(f"published evidence package {source_name} bytes do not match its pin")

    evidence_records = _object_list(package, "evidence_records", allow_empty=False)
    program_records = _object_list(package, "program_records", allow_empty=False)
    selector_results = _object_list(package, "selector_results", allow_empty=False)
    gaps = _object_list(package, "gaps")
    if (len(evidence_records), len(program_records), len(gaps)) != (22, 122, 11):
        raise RuntimeError("published evidence package release counts do not match the audited release")

    context_config = json.loads(DEFAULT_CONTEXT_CONFIG.read_text(encoding="utf-8"))
    approvals = context_config.get("selector_approvals")
    if not isinstance(approvals, dict):
        raise RuntimeError("published evidence config is missing selector approvals")
    receipts = {str(result.get("selector_id") or ""): result for result in selector_results}
    if set(receipts) != set(approvals):
        raise RuntimeError("published evidence package receipts do not cover every curated selector")
    selected_pairs: set[tuple[str, str]] = set()
    approved_pairs: set[tuple[str, str]] = set()
    for selector_id, approved_ids in approvals.items():
        receipt = receipts[selector_id]
        if receipt.get("approved_record_ids") != approved_ids:
            raise RuntimeError(f"published selector {selector_id} does not match its curated approvals")
        selected_pairs.update(
            (selector_id, record_id)
            for record_id in receipt.get("selected_record_ids", [])
        )
        approved_pairs.update((selector_id, record_id) for record_id in approved_ids)
    if len(approved_pairs) != 23 or selected_pairs != approved_pairs:
        raise RuntimeError("published evidence package does not exactly contain the 23 audited approvals")
    if any("W4399796030" in str(record.get("record_id")) for record in evidence_records):
        raise RuntimeError("published evidence package contains the SWD parasitoid-role paper")
    role_rejections = sum(
        int((result.get("rejection_counts") or {}).get("taxon_role_not_directly_confirmed", 0))
        for result in selector_results
    )
    if role_rejections <= 0:
        raise RuntimeError("published evidence package does not preserve focal-taxon role rejections")

    expected_program_records = {
        record.record_id: record
        for record in build_insect_intelligence_records(
            DEFAULT_PROGRAM_CONFIG,
            retrieved_at="2026-07-14T00:00:00Z",
        )
    }
    actual_program_records = {
        str(record.get("record_id") or ""): record for record in program_records
    }
    if set(actual_program_records) != set(expected_program_records):
        raise RuntimeError("published program records do not exactly match the program ledger")
    for record_id, expected in expected_program_records.items():
        expected_fragment = expected.provenance.locator.split("#", 1)[1]
        actual_locator = str(actual_program_records[record_id]["provenance"]["locator"])
        if urlsplit(actual_locator).fragment != expected_fragment:
            raise RuntimeError(f"published program record {record_id} has a non-resolving locator")

    source_map = (REPO_ROOT / "config/source-map.yaml").read_text(encoding="utf-8")
    source_map_terms = (
        PUBLIC_PACKAGE_SCHEMA_VERSION,
        "2026-07-14.7",
        DEFAULT_PUBLISHED_PACKAGE.relative_to(REPO_ROOT).as_posix(),
        DEFAULT_PUBLISHED_PACKAGE_SHA256,
        str(package["content_sha256"]),
    )
    missing = [term for term in source_map_terms if term not in source_map]
    if missing:
        raise RuntimeError(f"source map is missing published release binding: {missing}")


def check_open_source_boundary() -> None:
    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    notice_text = (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")
    data_text = (REPO_ROOT / "THIRD_PARTY_DATA.md").read_text(encoding="utf-8")
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    gitignore_text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    if "Apache License" not in license_text or "Version 2.0" not in license_text:
        raise RuntimeError("LICENSE must contain Apache License Version 2.0")
    if 'license = "Apache-2.0"' not in pyproject_text:
        raise RuntimeError("pyproject.toml must declare Apache-2.0")
    if "[build-system]" not in pyproject_text or 'build-backend = "setuptools.build_meta"' not in pyproject_text:
        raise RuntimeError("pyproject.toml must define the installable setuptools build")
    if 'ask-insects = "askinsects.cli:main"' not in pyproject_text:
        raise RuntimeError("pyproject.toml must install the ask-insects CLI entry point")
    if "artifacts/" not in gitignore_text:
        raise RuntimeError(".gitignore must keep generated artifacts out of git")

    required_terms = (
        "Apache-2.0",
        "not relicensed",
        "third-party data",
        "upstream licenses",
        "credentials",
    )
    combined = "\n".join((notice_text.lower(), data_text.lower(), readme_text.lower()))
    missing = [term for term in required_terms if term.lower() not in combined]
    if missing:
        raise RuntimeError(f"open-source boundary docs missing term(s): {', '.join(missing)}")

    source_terms = (
        "GBIF",
        "iNaturalist",
        "Mosquito Alert",
        "NCBI",
        "VectorBase",
        "VectorByte",
        "OpenAlex",
        "PubMed",
        "Unpaywall",
        "PMC Open Access",
        "Dryad",
        "Mendeley Data",
        "OSF",
        "Zenodo",
        "Figshare",
        "WHO",
        "PAHO",
        "CDC",
        "ECDC",
        "OpenDataSUS",
        "BOLD",
        "IR Mapper",
        "VectorNet",
    )
    missing_sources = [term for term in source_terms if term not in data_text]
    if missing_sources:
        raise RuntimeError(f"THIRD_PARTY_DATA.md missing source term(s): {', '.join(missing_sources)}")


def check_public_identity() -> None:
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    wiki_home_text = (REPO_ROOT / "wiki/Ask Insects.md").read_text(encoding="utf-8")
    source_map_text = (REPO_ROOT / "wiki/Source Map.md").read_text(encoding="utf-8")

    required_readme_terms = (
        "# Open Insects",
        "Open Insects is an open-source effort",
        "Ask Insects is the first tool in Open Insects",
        "The command remains `ask-insects`",
        "https://openinsects.org",
    )
    missing_readme = [term for term in required_readme_terms if term not in readme_text]
    if missing_readme:
        raise RuntimeError(f"README.md missing Open Insects term(s): {', '.join(missing_readme)}")

    required_pyproject_terms = (
        'Homepage = "https://openinsects.org"',
        'Source = "https://github.com/manintheandes/ask-insects"',
        'ask-insects = "askinsects.cli:main"',
    )
    missing_pyproject = [term for term in required_pyproject_terms if term not in pyproject_text]
    if missing_pyproject:
        raise RuntimeError(f"pyproject.toml missing Open Insects metadata term(s): {', '.join(missing_pyproject)}")

    required_wiki_terms = (
        "# Open Insects",
        "Ask Insects: a CLI and hosted source plane",
        'ask-insects ask "where has Aedes aegypti been spotted this year?"',
    )
    missing_wiki = [term for term in required_wiki_terms if term not in wiki_home_text]
    if missing_wiki:
        raise RuntimeError(f"wiki/Ask Insects.md missing Open Insects term(s): {', '.join(missing_wiki)}")

    if "Open Insects is built from public insect sources" not in source_map_text:
        raise RuntimeError("wiki/Source Map.md must explain Open Insects source grounding")
    if "Ask Insects is its first source-backed tool" not in source_map_text:
        raise RuntimeError("wiki/Source Map.md must preserve Ask Insects as the first tool")


DIRECT_SOURCE_REPLACEMENT_RE = re.compile(r"\.delete_source\([^\n]+\)\s*\n\s*[^#\n]*\.upsert_records\(")


def check_atomic_source_replacement() -> None:
    checked_paths = [
        path
        for path in REQUIRED_FILES
        if path.startswith("scripts/ingest_") or path in {"scripts/build_literature_facets.py", "askinsects/server.py"}
    ]
    offenders = []
    for path in checked_paths:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        if DIRECT_SOURCE_REPLACEMENT_RE.search(text):
            offenders.append(path)
    if offenders:
        raise RuntimeError(
            "source replacement must use SourceIndex.replace_source_records instead of delete_source followed by upsert_records: "
            + ", ".join(offenders)
        )

    index_text = (REPO_ROOT / "askinsects/index.py").read_text(encoding="utf-8")
    for term in ("def replace_source_records", "self._delete_source_records(conn, source", "self._upsert_records(conn, chunk"):
        if term not in index_text:
            raise RuntimeError(f"askinsects/index.py missing atomic replacement term: {term}")


def check_unit_tests() -> None:
    run_command([sys.executable, "-m", "unittest", *UNIT_TEST_MODULES, "-v"])


def check_source_index_build() -> None:
    payload = run_json(
        [
            sys.executable,
            "scripts/build_source_index.py",
            "--fixtures",
            "--artifact-dir",
            VERIFY_ARTIFACT_DIR.as_posix(),
        ]
    )
    if not payload.get("ok"):
        raise RuntimeError("fixture index build did not report ok true")
    if int(payload.get("record_count", 0)) < 7:
        raise RuntimeError("fixture index build produced fewer than 7 records")


def check_literature_source_map() -> None:
    text = (REPO_ROOT / "config/source-map.yaml").read_text(encoding="utf-8")
    required_terms = (
        "aedes_literature_openalex",
        "aedes_olfaction_literature",
        "mosquito_repellent_literature",
        "pmc_open_access_videos",
        "irmapper_aedes",
        "dryad_aedes_behavior_videos",
        "mendeley_aedes_behavior_media",
        "osf_flighttrackai_aedes_videos",
        "aedes_pathogen_taxonomy",
        "ncbi_biosamples",
        "aedes_vector_competence_assays",
        "aedes_resistance_markers",
        "aedes_resistance_table_rows",
        "aedes_occurrence_ecology",
        "aedes_extracted_facts",
        "OpenAlex articles where Aedes aegypti is material in title, abstract, or accepted topic metadata",
        "sqlite_payload_table: record_payloads",
        "sqlite_fulltext_table: literature_fulltext_units",
        "search fulltext",
        "live_fetch: opt_in",
        "pubmed_eutilities",
        "unpaywall_api",
    )
    missing = [term for term in required_terms if term not in text]
    if missing:
        raise RuntimeError(f"source map missing literature term(s): {', '.join(missing)}")


def check_mosquito_intelligence_coverage() -> None:
    from scripts.verify_mosquito_intelligence_coverage import load_coverage, verify_coverage

    verify_coverage(load_coverage())
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    lanes_doc = (REPO_ROOT / "docs/source-lanes.md").read_text(encoding="utf-8")
    source_map = (REPO_ROOT / "config/source-map.yaml").read_text(encoding="utf-8")
    required_terms = (
        "config/mosquito-intelligence-coverage.json",
        "Aedes",
        "aedes_literature_facets",
        "aedes_olfaction_literature",
        "aedes_crossref_literature_audit",
        "mosquito_repellent_literature",
        "aedes_public_health_guidance",
        "aedes_paho_dengue_surveillance",
        "aedes_who_dengue_surveillance",
        "aedes_cdc_dengue_surveillance",
        "mosquito_alert_gbif",
        "aedes_opendatasus_dengue_surveillance",
        "vectornet_aedes_surveillance",
        "dryad_aedes_behavior_videos",
        "aedes_pathogen_taxonomy",
        "ncbi_biosamples",
        "aedes_vector_competence_assays",
        "aedes_occurrence_ecology",
        "aedes_observation_climate_join",
        "vectorbase_aedes_genomics",
        "aedes_expression_omics",
        "aedes_uniprot_proteins",
        "aedes_wolbachia_interventions",
        "aedes_vectorbyte_traits",
        "osf_flighttrackai_aedes_videos",
        "zenodo_aedes_videos",
        "figshare_aedes_videos",
        "aedes_video_atoms",
        "aedes_image_atoms",
        "aedes_taxonomy_authorities",
        "aedes_worldclim_climate",
        "aedes_global_compendium_occurrence",
        "aedes_population_genomics",
        "aedes_who_resistance_guidance",
    )
    for term in required_terms:
        if term not in readme:
            raise RuntimeError(f"README.md missing coverage term: {term}")
        if term not in lanes_doc:
            raise RuntimeError(f"docs/source-lanes.md missing coverage term: {term}")
    if "mosquito-intelligence-coverage.json" not in source_map:
        raise RuntimeError("config/source-map.yaml missing coverage ledger link")
    if "aedes-source-plane-benchmark.json" not in source_map:
        raise RuntimeError("config/source-map.yaml missing Aedes source-plane benchmark link")
    if "aedes_literature_facets" not in source_map:
        raise RuntimeError("config/source-map.yaml missing aedes_literature_facets")
    for term in (
        "aedes_olfaction_literature",
        "scripts/ingest_aedes_olfaction_literature.py",
        "pubmed_esearch_esummary_to_sqlite_olfaction_literature_audit_records",
        "coverage_status",
        "matched_record_ids",
        "aedes_olfaction_result_limit_applied",
        "aedes_olfaction_no_canonical_literature_rows",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Aedes olfaction literature term: {term}")
    for term in (
        "aedes_crossref_literature_audit",
        "scripts/ingest_aedes_crossref_literature_audit.py",
        "crossref_works_cursor_pages_to_sqlite_literature_audit_records",
        "raw_crossref_page_locator",
        "aedes_crossref_result_limit_applied",
        "aedes_crossref_no_canonical_literature_rows",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Aedes Crossref literature term: {term}")
    for term in (
        "mosquito_repellent_literature",
        "scripts/ingest_mosquito_repellent_literature.py",
        "pubmed_and_crossref_repellent_metadata_to_sqlite_literature_records",
        "repellent_terms",
        "mosquito_terms",
        "mosquito_repellent_pubmed_result_limit_applied",
        "mosquito_repellent_crossref_result_limit_applied",
        "mosquito_repellent_no_canonical_literature_rows",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing mosquito repellent literature term: {term}")
    for term in (
        "mosquito_repellent_external_discovery",
        "scripts/ingest_mosquito_repellent_external_discovery.py",
        "external_repellent_metadata_to_sqlite_literature_dataset_patent_records",
        "OpenAlex",
        "Europe PMC",
        "Semantic Scholar",
        "DataCite",
        "Zenodo",
        "Figshare",
        "biorxiv_medrxiv_no_text_search_api",
        "patentsview_migrated_or_unavailable_json_api",
        "uspto_open_data_portal_requires_api_access",
        "google_scholar_no_public_api",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing mosquito repellent external discovery term: {term}")
    for term in ("aedes_public_health_guidance", "scripts/ingest_public_health_guidance.py", "public_health", "ECDC"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing public-health guidance term: {term}")
    for term in (
        "aedes_paho_dengue_surveillance",
        "scripts/ingest_paho_dengue_surveillance.py",
        "official_paho_dengue_report_html_and_core_indicators_csv_to_sqlite_public_health_records",
        "PAHO/EIH Core Indicators annual country/territory dengue rows are proven machine-readable via ZIP/CSV",
        "PAHO/PLISA country-week dashboard data remains a source gap",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing PAHO dengue surveillance term: {term}")
    for term in (
        "aedes_who_dengue_surveillance",
        "scripts/ingest_who_dengue_surveillance.py",
        "who_dengue_pages_reports_and_dashboard_locators_to_sqlite_public_health_records",
        "WHO page/report/dashboard-locator grain",
        "dashboard row-level data remains a source gap",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing WHO dengue surveillance term: {term}")
    for term in (
        "aedes_cdc_dengue_surveillance",
        "scripts/ingest_cdc_dengue_surveillance.py",
        "cdc_dengue_pages_visualization_json_and_csv_to_sqlite_public_health_records",
        "csv_row_records",
        "limitation_records",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing CDC dengue surveillance term: {term}")
    for term in (
        "aedes_ncvbdc_dengue_surveillance",
        "scripts/ingest_ncvbdc_dengue_surveillance.py",
        "ncvbdc_dengue_html_table_to_sqlite_public_health_records",
        "state/UT-year",
        "latest-two-complete-year summary",
        "district-level India dengue rows",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing NCVBDC dengue surveillance term: {term}")
    for term in (
        "aedes_opendatasus_dengue_surveillance",
        "scripts/ingest_opendatasus_dengue_surveillance.py",
        "opendatasus_sinan_dengue_csv_zip_to_sqlite_public_health_aggregate_records",
        "source-file",
        "country-year",
        "residence-state-year",
        "epidemiological-week",
        "aggregate_records_only_no_person_level_line_records",
        "EVOLUCAO=2",
        "DENGBR07.csv.zip",
        "DENGBR26.csv.zip",
        "2007 through 2026",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing OpenDataSUS dengue surveillance term: {term}")
    for term in ("mosquito_alert_gbif", "scripts/ingest_mosquito_alert_observations.py", "observations", "media"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Mosquito Alert term: {term}")
    for term in (
        "vectornet_aedes_surveillance",
        "scripts/ingest_vectornet_surveillance.py",
        "vectornet_ipt_darwin_core_archive_to_sqlite_observation_and_ecology_records",
        "degree_of_establishment",
        "absence_surveillance_count",
        "CC-BY-4.0",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing VectorNet surveillance term: {term}")
    for term in ("dryad_aedes_behavior_videos", "scripts/ingest_dryad_behavior_videos.py", "behavior", "media"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Dryad behavior/video term: {term}")
    for term in (
        "mendeley_aedes_behavior_media",
        "scripts/ingest_mendeley_behavior_media.py",
        "mendeley_public_snapshot_folder_file_manifest_audio_context_wav_metadata_and_typed_table_rows_to_sqlite",
        "6gvs94p6r2:1",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Mendeley behavior/media term: {term}")
    for term in (
        "osf_flighttrackai_aedes_videos",
        "scripts/ingest_osf_flighttrackai_videos.py",
        "osf_project_file_manifest_to_sqlite",
        "cx762",
        "manifest_and_download_locators_only_by_default",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing OSF FlightTrackAI term: {term}")
    for term in (
        "zenodo_aedes_videos",
        "scripts/ingest_zenodo_aedes_videos.py",
        "zenodo_records_search_file_manifest_to_sqlite_media_records",
        "metadata_and_download_locators_only_by_default",
        "source_hashes",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Zenodo Aedes video term: {term}")
    for term in (
        "figshare_aedes_videos",
        "scripts/ingest_figshare_aedes_videos.py",
        "figshare_article_search_detail_file_manifest_to_sqlite_media_records",
        "metadata_and_download_locators_only_by_default",
        "figshare_article_id",
        "figshare_file_id",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Figshare Aedes video term: {term}")
    for term in (
        "aedes_video_atoms",
        "scripts/ingest_video_atoms.py",
        "indexed_video_records_motion_tables_and_repository_discovery_to_sqlite_video_atoms",
        "bounded_mirror_when_license_and_size_allow_else_structured_gap",
        "video_download_not_video",
        "video_license_unclear",
        "video_archive_unsupported_format",
        "video_archive_read_failed",
        "thumbnails",
        "keyframes",
        "preview_clips",
        "frame_manifests",
        "coordinates",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Aedes video-atoms term: {term}")
    for term in ("pmc_oa", "dryad", "mendeley", "osf", "zenodo", "figshare", "institutional", "paper_supplements"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Aedes video discovery target: {term}")
    for term in ("aedes_pathogen_taxonomy", "scripts/ingest_pathogen_taxonomy.py", "vector_competence"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing pathogen taxonomy term: {term}")
    for term in ("ncbi_biosamples", "scripts/ingest_ncbi_biosamples.py", "biosamples", "ncbi_eutils_biosample_esearch_esummary_to_sqlite"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing NCBI BioSample term: {term}")
    for term in (
        "aedes_ncbi_snp_variation",
        "scripts/ingest_ncbi_snp_variation.py",
        "ncbi_eutils_snp_esearch_esummary_to_sqlite_variation_audit_records",
        "ncbi_snp_no_aedes_records",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing NCBI dbSNP variation term: {term}")
    for term in ("vectorbase_aedes_genomics", "scripts/ingest_vectorbase_genomics.py", "vectorbase_current_release_downloads_to_sqlite", "VectorBase-CURRENT_AaegyptiLVP_AGWG_GO.gaf.gz"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing VectorBase genomics term: {term}")
    for term in (
        "aedes_expression_omics",
        "scripts/ingest_expression_omics.py",
        "ncbi_eutils_geo_sra_to_sqlite_expression_records",
        "raw_esummary_locator",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing expression omics term: {term}")
    for term in (
        "aedes_uniprot_proteins",
        "scripts/ingest_uniprot_proteins.py",
        "uniprot_rest_to_sqlite_protein_records",
        "go_and_vectorbase_cross_references",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing UniProt proteins term: {term}")
    for term in ("aedes_vector_competence_assays", "scripts/ingest_vector_competence_assays.py", "literature_fulltext_units", "legal_fulltext_only"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing vector competence assay term: {term}")
    for term in ("aedes_resistance_markers", "scripts/ingest_resistance_markers.py", "literature_records_and_fulltext_units_to_sqlite_resistance_marker_records", "legal_fulltext_only"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing resistance marker term: {term}")
    for term in ("aedes_resistance_table_rows", "scripts/ingest_resistance_table_rows.py", "parsed_extracted_facts_resistance_tables_to_sqlite_resistance_records", "schema_validated_not_human_validated"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing resistance table row term: {term}")
    for term in (
        "who_malaria_threats_resistance_audit",
        "scripts/ingest_who_malaria_threats_resistance.py",
        "who_malaria_threats_fact_prevention_view_to_sqlite_resistance_or_gap_records",
        "who_malaria_threats_no_aedes_rows",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing WHO Malaria Threats resistance term: {term}")
    for term in ("aedes_occurrence_ecology", "scripts/ingest_occurrence_ecology.py", "indexed_observation_payloads_to_sqlite_ecology_records", "GBIF and iNaturalist observation joins"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing occurrence ecology term: {term}")
    for term in (
        "aedes_observation_climate_join",
        "scripts/ingest_observation_climate.py",
        "indexed_observation_payloads_and_worldclim_geotiff_to_sqlite_ecology_records",
        "observation_climate_worldclim_zip_missing",
        "observation_climate_limit_applied",
        "bio1_annual_mean_temperature_c",
        "bio12_annual_precipitation_mm",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing observation climate join term: {term}")
    for term in (
        "harvard_dataverse_aedes_suitability",
        "scripts/ingest_harvard_dataverse_suitability.py",
        "harvard_dataverse_search_and_dataset_json_to_sqlite_ecology_records",
        "dataverse_file_download_not_public",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Harvard Dataverse suitability term: {term}")
    for term in (
        "aedes_image_atoms",
        "scripts/ingest_image_atoms.py",
        "indexed_still_image_media_payloads_to_sqlite_image_atoms",
        "image_label_missing",
        "source_image_record_id",
        "quality_grade",
        "rights_holder",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Aedes image-atoms term: {term}")
    for term in (
        "aedes_extracted_facts",
        "scripts/ingest_extracted_facts.py",
        "literature_records_payloads_fulltext_units_supported_supplement_tables_and_per_paper_supplement_audits_to_sqlite_fact_records",
        "one_supplement_audit_atom_per_indexed_aedes_literature_paper",
        "every_schema_promotable_row_is_promoted_to_a_structured_lane",
        "candidate_manifest_or_parsed_not_human_validated",
        "supplement file-gap atoms",
        "existing_manifest seeds during incremental refresh",
        "bounded_opt_in_supplement_discovery_and_download",
        "csv",
        "xlsx",
        "docx",
        "figshare_metadata",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing extracted facts term: {term}")
    for term in (
        "drosophila_suzukii_literature_fulltext",
        "scripts/ingest_drosophila_suzukii_literature_fulltext.py",
        "drosophila_suzukii_literature_records_to_literature_fulltext_units_and_literature_fulltext_fts",
        "legal_direct_fulltext",
        "unpaywall_legal_direct_fulltext",
        "paywalled_pdfs",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii literature fulltext term: {term}")
    for term in (
        "drosophila_suzukii_extracted_facts",
        "scripts/ingest_drosophila_suzukii_extracted_facts.py",
        "drosophila_suzukii_literature_records_payloads_fulltext_units_supported_supplement_tables_and_per_paper_supplement_audits_to_sqlite_fact_records",
        "one_supplement_audit_atom_per_indexed_drosophila_suzukii_literature_paper",
        "crop_damage",
        "biocontrol",
        "bounded_opt_in_supplement_discovery_and_download",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii extracted facts term: {term}")
    for term in (
        "drosophila_suzukii_susceptibility_assay_rows",
        "scripts/ingest_drosophila_suzukii_susceptibility_assay_rows.py",
        "drosophila_suzukii_extracted_facts_resistance_records_to_sqlite_susceptibility_evidence",
        "parsed_table_schema_validated_or_candidate_not_human_validated",
        "candidate_literature_evidence_rows_for_insecticide_assay_or_metric_mentions",
        "explicit_gap_when_no_parsed_susceptibility_table_rows_pass",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii susceptibility assay term: {term}")
    for term in (
        "drosophila_suzukii_biocontrol_outcome_rows",
        "scripts/ingest_drosophila_suzukii_biocontrol_outcome_rows.py",
        "drosophila_suzukii_extracted_facts_biocontrol_records_to_sqlite_outcome_evidence",
        "parsed_table_schema_validated_or_candidate_not_human_validated",
        "candidate_literature_evidence_rows_for_biocontrol_agent_and_outcome_context",
        "explicit_gap_when_no_parsed_biocontrol_table_rows_pass",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii biocontrol outcome term: {term}")
    for term in (
        "drosophila_suzukii_video_atoms",
        "scripts/ingest_drosophila_suzukii_video_atoms.py",
        "drosophila_suzukii_indexed_video_records_and_dryad_frame_archives_to_sqlite_video_atoms",
        "bounded_mirror_when_license_and_size_allow_else_structured_gap",
        "source_trajectory_tables_not_available_for_swd",
        "dryad_10_5061_dryad_8vd762q",
        "dryad_frame_archive_preview_fetch_failed",
        "dryad_frame_archive_too_large_to_mirror",
        "dryad_frame_archive_download_failed",
        "dryad_frame_archive_zip_parse_failed",
        "dryad_frame_archive_keyframe_generation_failed",
        "dryad_tiff_frame_sequence_not_decoded_to_video",
        "dryad_frame_archive_motion_rows_not_available",
        "thumbnails",
        "keyframes",
        "preview_clips",
        "frame_manifests",
        "coordinates",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii video-atoms term: {term}")
    for term in (
        "drosophila_suzukii_genome_files",
        "scripts/ingest_drosophila_suzukii_genome_files.py",
        "drosophila_suzukii_ncbi_assembly_gff_protein_files_to_sqlite_genome_records",
        "GCF_043229965.1",
        "genomic.gff",
        "protein.faa",
        "gff_attributes",
        "sequence_length",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii genome-files term: {term}")
    for term in (
        "drosophila_suzukii_geo_expression_matrices",
        "scripts/ingest_drosophila_suzukii_geo_expression_matrices.py",
        "ncbi_geo_supplementary_gzip_tsv_to_sqlite_expression_rows",
        "GSE126708",
        "GSE73595",
        "log2_fold_change",
        "q_value",
        "geo_expression_file_fetch_or_parse_failed",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii GEO expression matrix term: {term}")
    for term in (
        "drosophila_suzukii_figshare_mk_selection",
        "scripts/ingest_drosophila_suzukii_figshare_mk_selection.py",
        "figshare_csv_to_sqlite_genome_feature_records",
        "10.6084/m9.figshare.13366079.v3",
        "26251579",
        "FETpval",
        "alpha",
        "P-value",
        "figshare_mk_selection_checksum_mismatch",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii Figshare MK selection term: {term}")
    for term in (
        "drosophila_suzukii_population_genomics",
        "scripts/ingest_drosophila_suzukii_population_genomics.py",
        "ncbi_bioproject_esearch_esummary_to_sqlite_population_genomics_records",
        "pool-seq",
        "whole-genome sequencing",
        "swd_population_genomics_bioproject_search_empty",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii population genomics term: {term}")
    for term in (
        "drosophila_suzukii_dryad_population_variants",
        "scripts/ingest_drosophila_suzukii_dryad_population_variants.py",
        "dryad_dataset_version_files_api_to_sqlite_variant_manifest_and_gap_records",
        "10.25338/B89P86",
        "10.1093/g3journal/jkab343",
        "PRJNA705744",
        "dryad_variant_file_too_large",
        "dryad_variant_rows_not_mirrored",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii Dryad population variant term: {term}")
    for term in (
        "drosophila_suzukii_occurrence_ecology",
        "scripts/ingest_drosophila_suzukii_occurrence_ecology.py",
        "drosophila_suzukii_indexed_observation_payloads_to_sqlite_ecology_records",
        "country_month_summary",
        "habitat_summary",
        "raw_occurrence",
        "raw_observation",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii occurrence ecology term: {term}")
    for term in (
        "drosophila_suzukii_jki_drosomon_trap_captures",
        "scripts/ingest_drosophila_suzukii_jki_drosomon_trap_captures.py",
        "data_europa_openagrar_zip_to_sqlite_ecology_capture_and_location_rows",
        "openagrar_mods_00041381",
        "10.3390/insects9040125",
        "trap_count_reported",
        "adult_captures_reported",
        "trap_name",
        "date_start",
        "adult_captures",
        "openagrar_derivate_00016480_zip",
        "latitude",
        "longitude",
        "altitude_m",
        "immediate_habitat_english",
        "openagrar_security_check_blocks_csv_download",
        "jki_trap_rows_parse_empty",
        "jki_trap_description_table_not_queryable",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii JKI DrosoMon trap-capture term: {term}")
    for term in (
        "drosophila_suzukii_plos_climate_suitability",
        "scripts/ingest_drosophila_suzukii_plos_climate_suitability.py",
        "plos_article_supplements_to_sqlite_climate_suitability_rows",
        "10.1371/journal.pone.0174318",
        "plos_supplement_s002_xlsx",
        "occurrence_site_count",
        "model_algorithms",
        "bootstrap_replicates",
        "auc",
        "plos_suitability_raster_files_not_downloadable",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii PLOS climate-suitability term: {term}")
    for term in (
        "drosophila_suzukii_osu_trap_reports",
        "scripts/ingest_drosophila_suzukii_osu_trap_reports.py",
        "osu_public_swd_trap_report_spreadsheets_to_sqlite_ecology_rows",
        "osu_pestmanagement_swd_trap_reports_landing_page",
        "osu_google_sheet_2021_swd_trap_reports",
        "osu_xlsx_2020_swd_trap_reports",
        "osu_google_sheet_2015_swd_trap_reports_unavailable_gap",
        "osu_swd_trap_report_unavailable",
        "osu_swd_trap_report_fetch_or_parse_failed",
        "weekly trap-period observation rows",
        "Ohio public crop-scout monitoring evidence",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii OSU trap-report term: {term}")
    for term in (
        "drosophila_suzukii_dryad_landscape_monitoring",
        "scripts/ingest_drosophila_suzukii_dryad_landscape_monitoring.py",
        "dryad_public_preview_table_to_sqlite_ecology_landscape_monitoring_rows",
        "10.5061/dryad.52c2k52",
        "10.1016/j.agee.2018.11.014",
        "dryad_file_52071_public_preview_js",
        "swd_trap_count",
        "predator_counts",
        "landscape_composition_shannon",
        "dryad_landscape_full_csv_download_blocked_preview_used",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii Dryad landscape-monitoring term: {term}")
    for term in (
        "drosophila_suzukii_umn_flight_assay_rows",
        "scripts/ingest_drosophila_suzukii_umn_flight_assay_rows.py",
        "umn_dspace_csv_to_sqlite_behavior_assay_rows",
        "umn_drum_item_11299_227164",
        "10.13020/4nsz-x660",
        "propensity",
        "phototactic",
        "avg_velocity_cm_s",
        "umn_flight_assay_csv_fetch_or_parse_failed",
        "umn_flight_assay_rows_not_queryable",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Drosophila suzukii UMN flight-assay term: {term}")
    for term in (
        "aedes_wolbachia_interventions",
        "scripts/ingest_wolbachia_interventions.py",
        "world_mosquito_program_html_to_sqlite_public_health_records",
        "metrics_mentioned",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Wolbachia intervention term: {term}")
    for term in (
        "aedes_vectorbyte_traits",
        "scripts/ingest_vectorbyte_traits.py",
        "vbd_hub_search_and_vectraits_dataset_json_to_sqlite_trait_records",
        "trait_row_records",
        "raw_json_locator",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing VectorByte traits term: {term}")
    for term in (
        "aedes_vectorbyte_abundance",
        "scripts/ingest_vectorbyte_abundance.py",
        "vectorbyte_vecdyn_provider_and_csv_json_to_sqlite_abundance_records",
        "abundance_sample_records",
        "vectorbyte_abundance_dataset_page_limit_applied",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing VectorByte abundance term: {term}")
    for term in (
        "aedes_taxonomy_authorities",
        "aedes_worldclim_climate",
        "aedes_global_compendium_occurrence",
        "aedes_population_genomics",
        "aedes_who_resistance_guidance",
        "scripts/ingest_aedes_deep_sources.py",
        "worldclim_html_and_bioclim_geotiff_to_sqlite_ecology_records",
        "bio1_annual_mean_temperature_c",
        "bio12_annual_precipitation_mm",
        "zenodo_record_csv_to_sqlite_observation_records",
        "ncbi_eutils_bioproject_esearch_esummary_to_sqlite_genome_feature_records",
        "who_resistance_guidance_html_to_sqlite_resistance_records",
        "worldclim_raster_sampling_not_enabled",
        "worldclim_raster_sampling_failed",
        "authority_html_pdf_to_sqlite_taxonomy_records",
        "source_format",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Aedes deep-source term: {term}")


def check_insect_intelligence_programs() -> None:
    from askinsects.sources.insect_intelligence_programs import (
        REQUIRED_KNOWLEDGE_DOMAINS,
        REQUIRED_READINESS_DIMENSIONS,
        load_program_ledger,
    )

    payload = load_program_ledger(REPO_ROOT / "config/insect-intelligence-programs.json")
    product_ids = {str(item.get("id")) for item in payload["products"] if isinstance(item, dict)}
    species_ids = {str(item.get("id")) for item in payload["species"] if isinstance(item, dict)}
    domain_ids = {str(item.get("id")) for item in payload["knowledge_domains"] if isinstance(item, dict)}
    readiness_ids = {str(item.get("id")) for item in payload["readiness_dimensions"] if isinstance(item, dict)}
    if product_ids != {"swd_crop_repellent", "human_mosquito_repellent"}:
        raise RuntimeError(f"insect-intelligence product mismatch: {sorted(product_ids)}")
    if species_ids != {"drosophila_suzukii", "aedes_aegypti", "plutella_xylostella"}:
        raise RuntimeError(f"insect-intelligence species mismatch: {sorted(species_ids)}")
    if domain_ids != REQUIRED_KNOWLEDGE_DOMAINS:
        raise RuntimeError("insect-intelligence knowledge-domain contract mismatch")
    if readiness_ids != REQUIRED_READINESS_DIMENSIONS:
        raise RuntimeError("insect-intelligence readiness-dimension contract mismatch")

    source_map = (REPO_ROOT / "config/source-map.yaml").read_text(encoding="utf-8")
    mapped_source_ids = set(re.findall(r"^  - id: ([^ ]+)$", source_map, flags=re.MULTILINE))
    referenced_source_ids = {
        str(source_id)
        for subject in [*payload["products"], *payload["species"]]
        if isinstance(subject, dict)
        for entry in [*subject.get("readiness", []), *subject.get("domains", [])]
        if isinstance(entry, dict)
        for source_id in entry.get("current_sources", [])
    }
    missing_source_ids = referenced_source_ids - mapped_source_ids
    if missing_source_ids:
        raise RuntimeError(f"insect-intelligence ledger references unmapped source ids: {sorted(missing_source_ids)}")
    for term in (
        "insect_intelligence_programs",
        "config/insect-intelligence-programs.json",
        "scripts/ingest_insect_intelligence_programs.py",
        "validated_program_ledger_to_sqlite_insect_intelligence_records",
        "insect_intelligence",
        "Plutella xylostella",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing insect-intelligence term: {term}")
    for doc_path in ("README.md", "docs/source-lanes.md", "docs/querying-ask-insects.md"):
        text = (REPO_ROOT / doc_path).read_text(encoding="utf-8").lower()
        for term in ("insect-intelligence-programs.json", "diamondback moth", "human mosquito repellent"):
            if term.lower() not in text:
                raise RuntimeError(f"{doc_path} missing insect-intelligence term: {term}")

    result = run_json(
        [
            sys.executable,
            "-m",
            "askinsects",
            "--artifact-dir",
            VERIFY_ARTIFACT_DIR.as_posix(),
            "ingest-insect-intelligence-programs",
        ]
    )
    if result.get("ok") is not True:
        raise RuntimeError("insect-intelligence program ingest did not report ok true")
    if int(result.get("species_count", 0)) != 3 or int(result.get("product_count", 0)) != 2:
        raise RuntimeError("insect-intelligence program ingest returned the wrong species or product count")
    if int(result.get("knowledge_domain_count", 0)) != 3 * len(REQUIRED_KNOWLEDGE_DOMAINS):
        raise RuntimeError("insect-intelligence program ingest returned the wrong knowledge-domain count")
    if int(result.get("readiness_dimension_count", 0)) != 2 * len(REQUIRED_READINESS_DIMENSIONS):
        raise RuntimeError("insect-intelligence program ingest returned the wrong readiness-dimension count")
    if int(result.get("gap_count", 0)) < len(REQUIRED_KNOWLEDGE_DOMAINS):
        raise RuntimeError("insect-intelligence program ingest did not preserve explicit gaps")

    questions = (
        ("what is missing from diamondback moth biology coverage?", "Plutella xylostella", "14"),
        ("what is the product readiness status of the human mosquito repellent?", None, "8"),
    )
    for question, expected_species, expected_count in questions:
        answer = run_json(
            [
                sys.executable,
                "-m",
                "askinsects",
                "--artifact-dir",
                VERIFY_ARTIFACT_DIR.as_posix(),
                "ask",
                question,
                "--json",
                "--local",
            ]
        )
        if answer.get("ok") is not True or not answer.get("evidence"):
            raise RuntimeError(f"insect-intelligence answer lacked evidence for: {question}")
        if expected_count not in str(answer.get("answer")):
            raise RuntimeError(f"insect-intelligence answer lacked tracked count for: {question}")
        first = answer["evidence"][0]
        if first.get("source") != "insect_intelligence_programs":
            raise RuntimeError(f"insect-intelligence answer used the wrong source for: {question}")
        if expected_species and first.get("species") != expected_species:
            raise RuntimeError(f"insect-intelligence answer used the wrong species for: {question}")
        locator = str((first.get("provenance") or {}).get("locator") or "")
        if not locator.startswith("config/insect-intelligence-programs.json#"):
            raise RuntimeError(f"insect-intelligence answer lacked exact ledger provenance for: {question}")


def _seed_verification_package_records(artifact_dir: Path) -> None:
    from askinsects.index import SourceIndex
    from askinsects.records import EvidenceRecord, Provenance

    index = SourceIndex(artifact_dir / "source_index.sqlite")
    records = []
    fixtures = (
        (
            "openalex:W2344416877",
            "Aedes aegypti human landing repellency response",
            "https://doi.org/10.0000/ask-insects-public-fixture-1",
        ),
        (
            "verify-package:aedes-landing-wrong-taxon",
            "Anopheles gambiae human landing repellency response",
            "https://doi.org/10.0000/ask-insects-public-fixture-2",
        ),
    )
    for record_id, retained_title, source_url in fixtures:
        records.append(
            EvidenceRecord(
                record_id=record_id,
                lane="literature",
                source="aedes_literature_openalex",
                title=retained_title,
                text=f"Fixture candidate for Aedes aegypti: {retained_title}",
                species="Aedes aegypti",
                url=source_url,
                media_url=None,
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator=f"fixture#{record_id}",
                    retrieved_at="2026-07-14T00:00:00Z",
                    license="CC-BY-4.0",
                    source_url=source_url,
                ),
                payload={
                    "raw_openalex_work": {
                        "display_name": retained_title,
                        "abstract_inverted_index": None,
                    }
                },
            )
        )
    index.upsert_records(records)
    _synchronize_verification_receipts(artifact_dir)


def _synchronize_verification_receipts(artifact_dir: Path) -> None:
    """Keep synthetic completion-gate receipts bound to their mutated fixture DB."""
    db_path = artifact_dir / "source_index.sqlite"
    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as conn:
        record_count = int(conn.execute("SELECT COUNT(*) FROM records").fetchone()[0])
        source_counts = {
            str(source): int(count)
            for source, count in conn.execute(
                "SELECT source, COUNT(*) FROM records GROUP BY source ORDER BY source"
            )
        }
        lane_counts = {
            str(lane): int(count)
            for lane, count in conn.execute(
                "SELECT lane, COUNT(*) FROM records GROUP BY lane ORDER BY lane"
            )
        }

    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _json_file(path, {})
        if not isinstance(payload, dict):
            raise RuntimeError(f"{path} is not a JSON object")
        payload["record_count"] = record_count
        payload["source_counts"] = source_counts
        payload["lanes"] = lane_counts
        sources = payload.get("sources")
        if isinstance(sources, list):
            payload["sources"] = sorted(source_counts)
        elif isinstance(sources, dict):
            synchronized_sources = {}
            for source, count in source_counts.items():
                source_payload = sources.get(source)
                if not isinstance(source_payload, dict):
                    source_payload = {
                        "source": source,
                        "method": "synthetic completion-gate evidence records",
                    }
                synchronized_sources[source] = {**source_payload, "record_count": count}
            payload["sources"] = synchronized_sources
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_verification_evidence_package(artifact_dir: Path) -> dict[str, object]:
    package_path_value = os.environ.get("ASK_INSECTS_VERIFY_PACKAGE_PATH")
    use_hosted = os.environ.get("ASK_INSECTS_VERIFY_HOSTED_PACKAGE") == "1"
    if package_path_value and use_hosted:
        raise RuntimeError("configure either a package path or hosted package verification, not both")
    if package_path_value:
        package_path = Path(package_path_value).expanduser()
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"configured evidence package is not readable JSON: {exc}") from exc
    elif use_hosted:
        package = run_json(
            [sys.executable, "-m", "askinsects", "context-package", "--hosted"]
        )
    else:
        from askinsects.context_package import (
            DEFAULT_PROGRAM_CONFIG,
            build_context_package,
        )

        _seed_verification_package_records(artifact_dir)
        package = build_context_package(
            artifact_dir=artifact_dir,
            program_config_path=DEFAULT_PROGRAM_CONFIG,
            generated_at="2026-07-14T00:00:00Z",
        )
    if not isinstance(package, dict):
        raise RuntimeError("evidence package verification input must be a JSON object")
    return package


def _add_deep_validation_probe(package: dict[str, object]) -> None:
    root: dict[str, object] = {}
    cursor = root
    for _ in range(MAX_PUBLIC_PACKAGE_DEPTH + 2):
        child: dict[str, object] = {}
        cursor["child"] = child
        cursor = child
    upstream = package.get("upstream_snapshot")
    if not isinstance(upstream, dict):
        raise RuntimeError("evidence package upstream_snapshot is not an object")
    upstream["validation_probe"] = root


def _check_context_package_validator_guards(package: dict[str, object]) -> None:
    from askinsects.context_package import validate_context_package

    probes = (
        (
            "unknown top-level field",
            lambda value: value.__setitem__("unexpected_validation_probe", True),
        ),
        (
            "unknown evidence-record field",
            lambda value: value["evidence_records"][0].__setitem__(
                "unexpected_validation_probe", True
            ),
        ),
        (
            "unknown evidence-payload field",
            lambda value: value["evidence_records"][0]["payload"].__setitem__(
                "unexpected_validation_probe", True
            ),
        ),
        (
            "unknown provenance field",
            lambda value: value["evidence_records"][0]["provenance"].__setitem__(
                "unexpected_validation_probe", True
            ),
        ),
        (
            "credential-shaped key",
            lambda value: value["upstream_snapshot"].__setitem__("api_token", "secret"),
        ),
        (
            "consumer-shaped key",
            lambda value: value["upstream_snapshot"].__setitem__(
                "tenant_identifier", "external-system"
            ),
        ),
        (
            "machine-local key",
            lambda value: value["upstream_snapshot"].__setitem__(
                "raw_artifact_path", "public-looking"
            ),
        ),
        (
            "local path",
            lambda value: value["evidence_records"][0]["provenance"].__setitem__(
                "locator", "file:///tmp/private/result.json"
            ),
        ),
        (
            "private-scheme provenance",
            lambda value: value["evidence_records"][0]["provenance"].__setitem__(
                "locator", "private://example.org/result/1"
            ),
        ),
        (
            "plain-HTTP provenance",
            lambda value: value["evidence_records"][0]["provenance"].__setitem__(
                "locator", "http://example.org/result/1"
            ),
        ),
        (
            "credentialed URL",
            lambda value: value.__setitem__(
                "objective", "See https://example.org/data?access_token=secret"
            ),
        ),
        (
            "oversized string",
            lambda value: value.__setitem__(
                "objective", "x" * (MAX_PUBLIC_PACKAGE_STRING_LENGTH + 1)
            ),
        ),
        ("excessive nesting", _add_deep_validation_probe),
    )
    for label, mutate in probes:
        invalid = deepcopy(package)
        mutate(invalid)
        try:
            validate_context_package(invalid, verify_hash=False)
        except (TypeError, ValueError):
            continue
        raise RuntimeError(
            f"context package exact structural/privacy validation accepted {label}"
        )


def check_evidence_package(artifact_dir: Path = VERIFY_ARTIFACT_DIR) -> None:
    from askinsects.context_package import (
        load_published_context_package,
        validate_context_package,
    )

    _check_producer_limit_alignment()
    published = load_published_context_package()
    validate_public_evidence_package(published, require_complete_contexts=True)
    _check_exact_published_release(published)
    package = _load_verification_evidence_package(artifact_dir)
    validate_context_package(package)
    validate_public_evidence_package(package, require_complete_contexts=True)
    _check_context_package_validator_guards(package)


def check_production_path_evaluation() -> None:
    from scripts.eval_production_path import CONTRACT_VERSION, load_contract

    contract = load_contract(REPO_ROOT / "evals/ask_insects_production_path_v1.json")
    if contract.get("contract_version") != CONTRACT_VERSION:
        raise RuntimeError("production-path evaluation contract version mismatch")
    if int(contract.get("minimum_case_count", 0)) < 200:
        raise RuntimeError("production-path evaluation must require at least 200 questions")
    if float(contract.get("maximum_seconds", 999)) > 30:
        raise RuntimeError("production-path evaluation must require every answer in under 30 seconds")
    cases = contract.get("cases")
    if not isinstance(cases, list) or len(cases) != 200:
        raise RuntimeError("production-path evaluation corpus must contain exactly 200 questions")
    questions = "\n".join(str(case.get("question") or "") for case in cases if isinstance(case, dict)).lower()
    for term in (
        "drosophila suzukii",
        "aedes",
        "diamondback moth",
        "swd crop repellent",
        "human mosquito repellent",
        "contact and non-contact",
        "best mosquito repellent",
        "separate private r&d system",
    ):
        if term not in questions:
            raise RuntimeError(f"production-path evaluation corpus is missing required question coverage: {term}")
    boundary_cases = {
        str(case.get("id")): str(case.get("question") or "")
        for case in cases
        if isinstance(case, dict) and str(case.get("id")) in {"boundary-01", "boundary-02", "boundary-04"}
    }
    if set(boundary_cases) != {"boundary-01", "boundary-02", "boundary-04"}:
        raise RuntimeError("production-path evaluation is missing the private-system boundary cases")
    for case_id, question in boundary_cases.items():
        if "separate private R&D system" not in question or CONSUMER_NAME_RE.search(question):
            raise RuntimeError(f"production-path boundary case {case_id} is consumer-specific")
    runner = (REPO_ROOT / "scripts/eval_production_path.py").read_text(encoding="utf-8")
    for term in (
        "codex",
        "--ephemeral",
        "ask-insects",
        "--compact",
        "maximum_seconds",
        "production_gate_passed",
        "visible_answer",
        "locator_patterns",
        "--regrade-results",
        "regraded_source_sha256",
        "_is_allowed_installed_skill_read",
        "_ask_command_failure",
    ):
        if term not in runner:
            raise RuntimeError(f"production-path evaluator is missing required behavior: {term}")
    if "BLOCKED_COMMAND_TERMS" in runner or CONSUMER_NAME_RE.search(runner):
        raise RuntimeError("production-path evaluator must use a generic command allowlist")
    skill_source = (REPO_ROOT / "skills/askinsects/SKILL.md").read_text(encoding="utf-8")
    skill = " ".join(skill_source.split())
    for term in (
        "Do not inspect memory",
        "run a second Ask Insects call",
        "write every cited locator in full",
        "--compact",
        "final_answer",
        "verbatim",
        "under 30 seconds",
    ):
        if term not in skill:
            raise RuntimeError(f"Ask Insects skill is missing production-path guidance: {term}")
    skill_frontmatter = " ".join(skill_source.split("---", 2)[1].split())
    for term in (
        "Do not open this file for a normal answer",
        "adding a new insect",
        "answer-routing design",
        "first hosted command",
        'ask-insects ask "<the user\'s exact question>" --json --compact',
        "return final_answer verbatim",
    ):
        if term not in skill_frontmatter:
            raise RuntimeError(f"Ask Insects skill description is missing direct-route guidance: {term}")
    agents = " ".join((REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8").split())
    for term in (
        "preferred first and only operational command",
        "Do not load the installed skill",
        "adding a new insect",
        "answer-routing design",
        "Do not inspect memory",
        "Do not emit a progress update",
        "answer immediately without another command",
        "Preserve canonical labels",
        "--compact",
        "final_answer",
        "verbatim",
    ):
        if term not in agents:
            raise RuntimeError(f"Ask Insects AGENTS.md is missing production-path guidance: {term}")
    docs = (REPO_ROOT / "docs/production-path-evaluation.md").read_text(encoding="utf-8")
    for term in ("200", "100 percent", "under 30 seconds", "production_gate_passed: true"):
        if term not in docs:
            raise RuntimeError(f"production-path evaluation documentation is missing: {term}")


def check_aedes_source_plane_benchmark() -> None:
    benchmark_path = REPO_ROOT / "config/aedes-source-plane-benchmark.json"
    doc_path = REPO_ROOT / "docs/aedes-source-plane-benchmark.md"
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    doc = doc_path.read_text(encoding="utf-8")
    if payload.get("primary_taxon") != "Aedes aegypti":
        raise RuntimeError("Aedes benchmark must declare Aedes aegypti as the primary taxon")
    if payload.get("claim_status") != "not_proven_world_largest":
        raise RuntimeError("Aedes benchmark must keep the world-largest claim unproven")
    claim_rules = payload.get("claim_rules")
    if not isinstance(claim_rules, dict) or claim_rules.get("world_largest_claim_allowed") is not False:
        raise RuntimeError("Aedes benchmark must disallow the world-largest claim")
    current_proof = payload.get("ask_insects_current", {})
    if not isinstance(current_proof, dict):
        raise RuntimeError("Aedes benchmark missing ask_insects_current proof")
    if int(current_proof.get("hosted_record_count", 0)) < 1415737:
        raise RuntimeError("Aedes benchmark hosted proof is below the expected hosted record count")
    if int(current_proof.get("hosted_vectorbase_genomics_records", 0)) < 872001:
        raise RuntimeError("Aedes benchmark hosted VectorBase proof is below the expected record count")
    if int(current_proof.get("hosted_video_atom_records", 0)) < 46181:
        raise RuntimeError("Aedes benchmark hosted video-atom proof is below the expected record count")
    if int(current_proof.get("hosted_video_artifact_records", 0)) < 179:
        raise RuntimeError("Aedes benchmark hosted video-artifact proof is below the expected record count")
    if int(current_proof.get("hosted_video_gap_records", 0)) < 330:
        raise RuntimeError("Aedes benchmark hosted video-gap proof is below the expected record count")
    hosted_sources = current_proof.get("hosted_sources")
    if not isinstance(hosted_sources, list):
        raise RuntimeError("Aedes benchmark must list hosted sources")
    for source_id in (
        "vectorbase_aedes_genomics",
        "aedes_video_atoms",
        "aedes_crossref_literature_audit",
        "mosquito_repellent_external_discovery",
        "aedes_resistance_table_rows",
        "who_malaria_threats_resistance_audit",
    ):
        if source_id not in hosted_sources:
            raise RuntimeError(f"Aedes benchmark hosted source list missing {source_id}")
    required_comparators = {
        "vectorbase_veupathdb",
        "ncbi_entrez_datasets",
        "gbif",
        "inaturalist",
        "mosquito_alert",
        "vectornet",
        "bold",
        "irmapper",
        "vectorbyte_vectraits",
        "openalex_pubmed_pmc",
        "paho_cdc_public_health",
    }
    comparators = payload.get("external_comparators")
    if not isinstance(comparators, list):
        raise RuntimeError("Aedes benchmark must declare external_comparators")
    comparator_ids = {str(item.get("id")) for item in comparators if isinstance(item, dict)}
    if comparator_ids != required_comparators:
        raise RuntimeError(f"Aedes benchmark comparator mismatch: {sorted(comparator_ids)}")
    for term in ("Claim Ladder", "not proven", "VectorBase", "VectorByte", "GBIF", "IR Mapper"):
        if term not in doc:
            raise RuntimeError(f"docs/aedes-source-plane-benchmark.md missing term: {term}")


def check_cli() -> None:
    health = run_json([sys.executable, "-m", "askinsects", "health", "--local"])
    if health.get("ok") is not True:
        raise RuntimeError("health did not report ok true")

    summary = run_json([sys.executable, "-m", "askinsects", "summary", "--local"])
    if int(summary.get("record_count", 0)) < 7:
        raise RuntimeError("summary reported fewer than 7 records")

    sources = run_json([sys.executable, "-m", "askinsects", "sources", "--local"])
    if "mosquito_v1_fixtures" not in sources.get("sources", []):
        raise RuntimeError("sources did not include mosquito_v1_fixtures")

    answer_cases = (
        "what do we know about Aedes aegypti?",
        "show mosquito observations with images in Brazil",
        "what should a scientist inspect next for Culex pipiens?",
    )
    for question in answer_cases:
        payload = run_json([sys.executable, "-m", "askinsects", "ask", question, "--json", "--local"])
        if payload.get("ok") is not True:
            raise RuntimeError(f"answer did not report ok true for: {question}")
        if not payload.get("evidence"):
            raise RuntimeError(f"answer did not include evidence for: {question}")

    gap = run_json(
        [
            sys.executable,
            "-m",
            "askinsects",
            "ask",
            "show mosquito videos from Brazil",
            "--json",
            "--local",
        ],
        expected_returncode=2,
    )
    if gap.get("ok") is not False:
        raise RuntimeError("media source gap did not report ok false")
    if not gap.get("source_gap"):
        raise RuntimeError("media source gap did not include source_gap")


VIDEO_MOTION_HEADERS = {
    "video",
    "video_id",
    "source_video_record_id",
    "track",
    "track_id",
    "trackid",
    "tracking_id",
    "frame",
    "time",
    "time_seconds",
    "position_t",
    "timestamp",
    "t",
    "x",
    "position_x",
    "x_position",
    "pos_x",
    "center_x",
    "y",
    "position_y",
    "y_position",
    "pos_y",
    "center_y",
    "behavior",
    "behavioral_activity",
    "behavioural_activity",
    "behavior_type",
}
VIDEO_DISCOVERY_TARGETS = (
    "pmc_oa",
    "dryad",
    "mendeley",
    "osf",
    "zenodo",
    "figshare",
    "institutional",
    "paper_supplements",
)


def _json_file(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _sqlite_source_counts(db_path: Path) -> tuple[int, dict[str, int]]:
    with sqlite3.connect(db_path) as conn:
        record_count = int(conn.execute("select count(*) from records").fetchone()[0])
        source_counts = {
            str(row[0]): int(row[1])
            for row in conn.execute("select source, count(*) from records group by source order by source")
        }
    return record_count, source_counts


def _receipt_source_payload(payload: dict[str, object], source: str) -> dict[str, object]:
    direct = payload.get(source)
    if isinstance(direct, dict):
        return direct
    sources = payload.get("sources")
    if isinstance(sources, dict):
        nested = sources.get(source)
        if isinstance(nested, dict):
            return nested
    return {}


def check_receipts_match_sqlite(artifact_dir: Path) -> None:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise RuntimeError(f"missing SQLite artifact: {db_path}")
    record_count, source_counts = _sqlite_source_counts(db_path)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        if not path.exists():
            raise RuntimeError(f"missing receipt artifact: {path}")
        payload = _json_file(path, {})
        if not isinstance(payload, dict):
            raise RuntimeError(f"{path} is not a JSON object")
        if "record_count" in payload and int(payload.get("record_count", -1)) != record_count:
            raise RuntimeError(
                f"{path.name} record_count mismatch for {artifact_dir}: SQLite has {record_count}, receipt has {payload.get('record_count')}"
            )
        receipt_source_counts = payload.get("source_counts")
        if isinstance(receipt_source_counts, dict):
            normalized = {str(key): int(value) for key, value in receipt_source_counts.items()}
            if normalized != source_counts:
                raise RuntimeError(
                    f"{path.name} source_counts mismatch for {artifact_dir}: SQLite has {source_counts}, receipt has {normalized}"
                )
        for source, count in source_counts.items():
            source_payload = _receipt_source_payload(payload, source)
            if source_payload and "record_count" in source_payload and int(source_payload.get("record_count", -1)) != count:
                raise RuntimeError(
                    f"{path.name} {source}.record_count mismatch for {artifact_dir}: SQLite has {count}, receipt has {source_payload.get('record_count')}"
                )


def _video_source_payload(status: dict[str, object]) -> dict[str, object]:
    payload = status.get("aedes_video_atoms")
    if isinstance(payload, dict):
        return payload
    sources = status.get("sources")
    if isinstance(sources, dict):
        payload = sources.get("aedes_video_atoms")
        if isinstance(payload, dict):
            return payload
    return {}


def _video_atom_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        select json_extract(payload_json, '$.atom_type') as atom_type, count(*) as n
        from record_payloads
        where source='aedes_video_atoms'
        group by atom_type
        """
    ).fetchall()
    return {str(row["atom_type"]): int(row["n"]) for row in rows if row["atom_type"] is not None}


def _video_repository_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        select repository, count(*) as n
        from (
          select coalesce(
            json_extract(payload_json, '$.discovery_repository'),
            json_extract(payload_json, '$.repository')
          ) as repository
          from record_payloads
          where source='aedes_video_atoms'
        )
        where repository is not null
        group by repository
        """
    ).fetchall()
    return {str(row["repository"]): int(row["n"]) for row in rows}


def _video_sweep_repository_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        select json_extract(payload_json, '$.repository') as repository, count(*) as n
        from record_payloads
        where source='aedes_video_atoms'
          and json_extract(payload_json, '$.atom_type')='video_sweep'
        group by repository
        """
    ).fetchall()
    return {str(row["repository"]): int(row["n"]) for row in rows if row["repository"] is not None}


def _has_motion_table_inputs(artifact_dir: Path) -> bool:
    roots = (
        artifact_dir / "raw" / "pmc_videos",
        artifact_dir / "raw" / "dryad_behavior_videos",
        artifact_dir / "raw" / "mendeley_behavior_media" / "table_files",
        artifact_dir / "raw" / "mendeley_behavior_media",
        artifact_dir / "raw" / "osf_flighttrackai_videos",
        artifact_dir / "raw" / "zenodo_aedes_videos",
        artifact_dir / "raw" / "figshare_aedes_videos",
        artifact_dir / "raw" / "video_atoms",
    )
    for root in roots:
        if not root.exists():
            continue
        for path in sorted([*root.rglob("*.csv"), *root.rglob("*.tsv")]):
            try:
                with path.open(newline="", encoding="utf-8-sig") as handle:
                    reader = csv.reader(handle, delimiter="\t" if path.suffix.lower() == ".tsv" else ",")
                    headers = next(reader, [])
            except (OSError, UnicodeDecodeError, StopIteration, csv.Error):
                continue
            normalized = {re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_") for header in headers}
            if normalized & VIDEO_MOTION_HEADERS:
                return True
    return False


def check_aedes_video_atoms_artifact(artifact_dir: Path | None = None) -> None:
    artifact_dir = artifact_dir or (REPO_ROOT / "artifacts/mosquito-v1")
    db_path = artifact_dir / "source_index.sqlite"
    status_path = artifact_dir / "source_status.json"
    gaps_path = artifact_dir / "gaps.json"
    for path in (db_path, status_path, gaps_path):
        if not path.exists():
            raise RuntimeError(f"missing Aedes video artifact file: {path.relative_to(REPO_ROOT)}")

    status = _json_file(status_path, {})
    if not isinstance(status, dict):
        raise RuntimeError("source_status.json is not an object")
    video_status = _video_source_payload(status)
    if not video_status:
        raise RuntimeError("source_status.json missing aedes_video_atoms payload")
    gaps_payload = _json_file(gaps_path, [])
    if not isinstance(gaps_payload, list):
        raise RuntimeError("gaps.json is not a list")
    video_gaps = [gap for gap in gaps_payload if isinstance(gap, dict) and gap.get("source") == "aedes_video_atoms"]

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        source_records = int(conn.execute("select count(*) from records where source='aedes_video_atoms'").fetchone()[0])
        atom_counts = _video_atom_counts(conn)
        repository_counts = _video_repository_counts(conn)
        sweep_repository_counts = _video_sweep_repository_counts(conn)
        verified_assets = int(
            conn.execute(
                """
                select count(*)
                from record_payloads
                where source='aedes_video_atoms'
                  and json_extract(payload_json, '$.atom_type')='video_asset'
                  and json_extract(payload_json, '$.verification_status')='verified'
                """
            ).fetchone()[0]
        )
        mirrored_assets = int(
            conn.execute(
                """
                select count(*)
                from record_payloads
                where source='aedes_video_atoms'
                  and json_extract(payload_json, '$.atom_type')='video_asset'
                  and coalesce(
                    json_extract(payload_json, '$.mirror_path'),
                    json_extract(payload_json, '$.raw_asset_path'),
                    json_extract(payload_json, '$.mirrored_path'),
                    json_extract(payload_json, '$.local_mirror_path')
                  ) is not null
                """
            ).fetchone()[0]
        )
        broken_motion_asset_refs = int(
            conn.execute(
                """
                with motion as (
                  select json_extract(payload_json, '$.source_video_asset_id') as asset_id
                  from record_payloads
                  where source='aedes_video_atoms'
                    and json_extract(payload_json, '$.atom_type')='video_motion_row'
                )
                select count(*)
                from motion
                left join record_payloads asset on asset.record_id = motion.asset_id
                where motion.asset_id is not null
                  and asset.record_id is null
                """
            ).fetchone()[0]
        )
        broken_archive_member_asset_refs = int(
            conn.execute(
                """
                with members as (
                  select json_extract(payload_json, '$.source_video_asset_id') as asset_id
                  from record_payloads
                  where source='aedes_video_atoms'
                    and json_extract(payload_json, '$.atom_type')='video_archive_member'
                )
                select count(*)
                from members
                left join record_payloads asset on asset.record_id = members.asset_id
                where members.asset_id is not null
                  and asset.record_id is null
                """
            ).fetchone()[0]
        )
        stale_archive_gaps = int(
            conn.execute(
                """
                select count(*)
                from record_payloads
                where source='aedes_video_atoms'
                  and json_extract(payload_json, '$.atom_type')='video_gap'
                  and json_extract(payload_json, '$.reason')='video_archive_not_expanded'
                """
            ).fetchone()[0]
        )
        thumbnail_keyframes = int(
            conn.execute(
                """
                select count(*)
                from record_payloads p
                join records r on r.record_id = p.record_id
                where p.source='aedes_video_atoms'
                  and json_extract(p.payload_json, '$.atom_type')='video_keyframe'
                  and (
                    lower(coalesce(r.media_url, '')) like '%thumbnail%'
                    or lower(coalesce(json_extract(p.payload_json, '$.artifact_path'), '')) like '%thumbnail%'
                  )
                """
            ).fetchone()[0]
        )
        frame_manifest_paths = [
            str(row["path"])
            for row in conn.execute(
                """
                select coalesce(
                  r.media_url,
                  json_extract(p.payload_json, '$.artifact_path')
                ) as path
                from record_payloads p
                join records r on r.record_id = p.record_id
                where p.source='aedes_video_atoms'
                  and json_extract(p.payload_json, '$.atom_type')='video_frame_manifest'
                """
            ).fetchall()
            if row["path"]
        ]

    expected_record_count = int(video_status.get("record_count", 0))
    if source_records == 0:
        raise RuntimeError("Aedes video atoms artifact has no queryable records")
    if expected_record_count and source_records != expected_record_count:
        raise RuntimeError(f"Aedes video atom record_count mismatch: SQLite has {source_records}, receipt has {expected_record_count}")

    checks = {
        "video_asset_count": atom_counts.get("video_asset", 0),
        "motion_row_count": atom_counts.get("video_motion_row", 0),
        "gap_count": atom_counts.get("video_gap", 0),
    }
    artifact_count = sum(atom_counts.get(atom_type, 0) for atom_type in ("video_thumbnail", "video_keyframe", "video_preview_clip", "video_frame_manifest"))
    checks["artifact_count"] = artifact_count
    checks["verified_video_count"] = verified_assets
    checks["mirrored_video_count"] = mirrored_assets
    for key, actual in checks.items():
        if key in video_status and int(video_status.get(key, -1)) != actual:
            raise RuntimeError(f"Aedes video atom {key} mismatch: SQLite has {actual}, receipt has {video_status.get(key)}")

    if len(video_gaps) != atom_counts.get("video_gap", 0):
        raise RuntimeError(
            f"Aedes video gaps must be queryable: gaps.json has {len(video_gaps)}, SQLite has {atom_counts.get('video_gap', 0)} video_gap records"
        )
    if _has_motion_table_inputs(artifact_dir) and atom_counts.get("video_motion_row", 0) == 0:
        raise RuntimeError("Aedes video motion tables exist, but aedes_video_atoms has zero queryable video_motion_row records")
    if broken_motion_asset_refs:
        raise RuntimeError(f"Aedes video motion rows have broken source video asset references: {broken_motion_asset_refs}")
    if broken_archive_member_asset_refs:
        raise RuntimeError(f"Aedes video archive member rows have broken source video asset references: {broken_archive_member_asset_refs}")
    if stale_archive_gaps:
        raise RuntimeError(f"Aedes video atoms has stale unexpanded archive gaps: {stale_archive_gaps}")
    if thumbnail_keyframes:
        raise RuntimeError(f"Aedes video atoms has thumbnail-derived keyframe records: {thumbnail_keyframes}")
    frame_manifests_without_keyframes = 0
    for manifest_path in frame_manifest_paths:
        path = Path(manifest_path)
        if not path.is_absolute():
            path = artifact_dir / path
        try:
            payload = _json_file(path, {})
        except RuntimeError:
            frame_manifests_without_keyframes += 1
            continue
        keyframes = payload.get("keyframes") if isinstance(payload, dict) else None
        if not isinstance(keyframes, list) or not keyframes:
            frame_manifests_without_keyframes += 1
    if frame_manifests_without_keyframes:
        raise RuntimeError(f"Aedes video atoms has frame manifests without keyframes: {frame_manifests_without_keyframes}")

    missing_targets = [target for target in VIDEO_DISCOVERY_TARGETS if repository_counts.get(target, 0) == 0]
    if missing_targets:
        raise RuntimeError("Aedes video discovery targets lack queryable asset or gap records: " + ", ".join(missing_targets))
    sweep_receipts = video_status.get("discovery_sweep_receipts")
    if not isinstance(sweep_receipts, list):
        raise RuntimeError("Aedes video atoms receipt missing discovery_sweep_receipts")
    receipt_by_target = {
        str(receipt.get("repository")): receipt
        for receipt in sweep_receipts
        if isinstance(receipt, dict) and receipt.get("repository")
    }
    missing_receipts = [target for target in VIDEO_DISCOVERY_TARGETS if target not in receipt_by_target]
    if missing_receipts:
        raise RuntimeError("Aedes video discovery targets lack sweep receipts: " + ", ".join(missing_receipts))
    incomplete_receipts = []
    for target, receipt in receipt_by_target.items():
        if target not in VIDEO_DISCOVERY_TARGETS:
            continue
        if not receipt.get("status") or (
            int(receipt.get("raw_candidate_count") or 0) == 0
            and int(receipt.get("gap_count") or 0) == 0
        ):
            incomplete_receipts.append(target)
        has_coverage_locator = any(
            isinstance(receipt.get(key), list) and receipt.get(key)
            for key in ("queries", "request_urls", "raw_artifacts", "input_sources")
        )
        if (
            not receipt.get("coverage_method")
            or not has_coverage_locator
            or int(receipt.get("page_count") or 0) < 1
            or "cursor_or_page_complete" not in receipt
            or "candidate_limit" not in receipt
        ):
            incomplete_receipts.append(target)
    if incomplete_receipts:
        raise RuntimeError("Aedes video discovery sweep receipts lack candidate or gap proof: " + ", ".join(sorted(incomplete_receipts)))
    missing_sweep_records = [target for target in VIDEO_DISCOVERY_TARGETS if sweep_repository_counts.get(target, 0) == 0]
    if missing_sweep_records:
        raise RuntimeError("Aedes video discovery sweep records are not queryable for all targets: " + ", ".join(missing_sweep_records))


def _image_source_payload(status: dict[str, object]) -> dict[str, object]:
    payload = status.get("aedes_image_atoms")
    if isinstance(payload, dict):
        return payload
    sources = status.get("sources")
    if isinstance(sources, dict):
        payload = sources.get("aedes_image_atoms")
        if isinstance(payload, dict):
            return payload
    return {}


def _image_atom_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        select json_extract(payload_json, '$.atom_type') as atom_type, count(*) as n
        from record_payloads
        where source='aedes_image_atoms'
        group by atom_type
        """
    ).fetchall()
    return {str(row["atom_type"]): int(row["n"]) for row in rows if row["atom_type"] is not None}


def check_aedes_image_atoms_artifact(artifact_dir: Path | None = None) -> None:
    artifact_dir = artifact_dir or (REPO_ROOT / "artifacts/mosquito-v1")
    db_path = artifact_dir / "source_index.sqlite"
    status_path = artifact_dir / "source_status.json"
    gaps_path = artifact_dir / "gaps.json"
    for path in (db_path, status_path, gaps_path):
        if not path.exists():
            raise RuntimeError(f"missing Aedes image artifact file: {path.relative_to(REPO_ROOT)}")

    status = _json_file(status_path, {})
    if not isinstance(status, dict):
        raise RuntimeError("source_status.json is not an object")
    image_status = _image_source_payload(status)
    if not image_status:
        raise RuntimeError("source_status.json missing aedes_image_atoms payload")
    gaps_payload = _json_file(gaps_path, [])
    if not isinstance(gaps_payload, list):
        raise RuntimeError("gaps.json is not a list")
    image_gaps = [gap for gap in gaps_payload if isinstance(gap, dict) and gap.get("source") == "aedes_image_atoms"]

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        source_records = int(conn.execute("select count(*) from records where source='aedes_image_atoms'").fetchone()[0])
        atom_counts = _image_atom_counts(conn)
        mirrored_images = int(
            conn.execute(
                """
                select count(*)
                from record_payloads
                where source='aedes_image_atoms'
                  and json_extract(payload_json, '$.atom_type')='image_asset'
                  and json_extract(payload_json, '$.raw_asset_path') is not null
                """
            ).fetchone()[0]
        )
        verified_images = int(
            conn.execute(
                """
                select count(*)
                from record_payloads
                where source='aedes_image_atoms'
                  and json_extract(payload_json, '$.atom_type')='image_asset'
                  and json_extract(payload_json, '$.verification_status')='verified'
                """
            ).fetchone()[0]
        )
        input_media = int(
            conn.execute(
                """
                select count(*)
                from records
                where source in ('inaturalist_api', 'mosquito_alert_gbif')
                  and lane='media'
                  and media_url is not null
                  and lower(coalesce(species, '')) like 'aedes aegypti%'
                """
            ).fetchone()[0]
        )

    expected_record_count = int(image_status.get("record_count", 0))
    if source_records == 0:
        raise RuntimeError("Aedes image atoms artifact has no queryable records")
    if expected_record_count and source_records != expected_record_count:
        raise RuntimeError(f"Aedes image atom record_count mismatch: SQLite has {source_records}, receipt has {expected_record_count}")
    checks = {
        "image_asset_count": atom_counts.get("image_asset", 0),
        "image_label_count": atom_counts.get("image_label", 0),
        "image_gap_count": atom_counts.get("image_gap", 0),
        "mirrored_image_count": mirrored_images,
        "verified_image_count": verified_images,
    }
    for key, actual in checks.items():
        if key in image_status and int(image_status.get(key, -1)) != actual:
            raise RuntimeError(f"Aedes image atom {key} mismatch: SQLite has {actual}, receipt has {image_status.get(key)}")
    if input_media and atom_counts.get("image_asset", 0) != input_media:
        raise RuntimeError(f"Aedes image atom assets must match indexed still-image media: inputs {input_media}, assets {atom_counts.get('image_asset', 0)}")
    if atom_counts.get("image_label", 0) == 0:
        raise RuntimeError("Aedes image atoms artifact has no queryable image_label records")
    if len(image_gaps) != atom_counts.get("image_gap", 0):
        raise RuntimeError(
            f"Aedes image gaps must be queryable: gaps.json has {len(image_gaps)}, SQLite has {atom_counts.get('image_gap', 0)} image_gap records"
        )


def _direct_fulltext_from_payload(payload: dict[str, object]) -> bool:
    unpaywall = payload.get("unpaywall")
    if isinstance(unpaywall, dict) and unpaywall.get("is_oa"):
        location = unpaywall.get("best_oa_location")
        if isinstance(location, dict):
            url = location.get("url_for_pdf") or location.get("url_for_xml")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return True
    work = payload.get("raw_openalex_work")
    if isinstance(work, dict):
        location = work.get("best_oa_location")
        if isinstance(location, dict):
            url = location.get("pdf_url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return True
    return False


def check_literature_artifact() -> None:
    legacy_artifact_dir = REPO_ROOT / "artifacts/aedes-literature-2020"
    merged_artifact_dir = REPO_ROOT / "artifacts/mosquito-v1"
    artifact_dir = legacy_artifact_dir if (legacy_artifact_dir / "source_index.sqlite").exists() else merged_artifact_dir
    db_path = artifact_dir / "source_index.sqlite"
    status_path = artifact_dir / "source_status.json"
    receipt_path = artifact_dir / "source_receipt.json"
    enrichment_receipt_path = artifact_dir / "literature_enrichment_receipt.json"
    gaps_path = artifact_dir / "gaps.json"
    required_paths = [db_path, status_path, receipt_path, gaps_path]
    if artifact_dir == legacy_artifact_dir:
        required_paths.append(enrichment_receipt_path)
    for path in required_paths:
        if not path.exists():
            raise RuntimeError(f"missing Aedes literature artifact file: {path.relative_to(REPO_ROOT)}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        literature_records = int(
            conn.execute("select count(*) from records where source='aedes_literature_openalex'").fetchone()[0]
        )
        payload_rows = conn.execute(
            "select record_id, payload_json from record_payloads where source='aedes_literature_openalex'"
        ).fetchall()
        pubmed_enriched = int(
            conn.execute(
                "select count(*) from record_payloads where source='aedes_literature_openalex' and json_type(payload_json, '$.pubmed')='object'"
            ).fetchone()[0]
        )
        unpaywall_enriched = int(
            conn.execute(
                "select count(*) from record_payloads where source='aedes_literature_openalex' and json_type(payload_json, '$.unpaywall')='object'"
            ).fetchone()[0]
        )
        fulltext_records = int(conn.execute("select count(distinct record_id) from literature_fulltext_units").fetchone()[0])
        fulltext_units = int(conn.execute("select count(*) from literature_fulltext_units").fetchone()[0])
        fulltext_fts = int(conn.execute("select count(*) from literature_fulltext_fts").fetchone()[0])
        fulltext_record_ids = {row[0] for row in conn.execute("select distinct record_id from literature_fulltext_units")}
        facet_counts = {
            str(row["lane"]): int(row["n"])
            for row in conn.execute(
                """
                select lane, count(*) as n
                from records
                where source='aedes_literature_facets'
                group by lane
                """
            )
        }

    if literature_records < 10683:
        raise RuntimeError(f"Aedes literature record count is {literature_records}, expected at least 10683")
    if len(payload_rows) != literature_records:
        raise RuntimeError("Aedes literature payload count does not match record count")
    if pubmed_enriched < 3800:
        raise RuntimeError(f"PubMed enrichment count is too low: {pubmed_enriched}")
    if unpaywall_enriched < 9500:
        raise RuntimeError(f"Unpaywall enrichment count is too low: {unpaywall_enriched}")
    if fulltext_records == 0 or fulltext_units == 0:
        raise RuntimeError("Aedes literature full text has not been extracted")
    if fulltext_fts != fulltext_units:
        raise RuntimeError("literature_fulltext_fts count does not match literature_fulltext_units")
    required_facet_counts = {
        "behavior": 2816,
        "vector_competence": 4534,
        "resistance": 2843,
        "ecology": 5253,
        "public_health": 8261,
    }
    for lane, expected in required_facet_counts.items():
        actual = facet_counts.get(lane, 0)
        if actual != expected:
            raise RuntimeError(f"Aedes literature facet count for {lane} is {actual}, expected {expected}")

    payloads = {row["record_id"]: json.loads(row["payload_json"]) for row in payload_rows}
    direct_candidates = {record_id for record_id, payload in payloads.items() if _direct_fulltext_from_payload(payload)}
    gaps = json.loads(gaps_path.read_text(encoding="utf-8"))
    if not isinstance(gaps, list):
        raise RuntimeError("gaps.json is not a list")
    gap_keys = {
        (
            str(gap.get("source")),
            str(gap.get("lane")),
            str(gap.get("reason")),
            str(gap.get("record_id")),
            str(gap.get("locator")),
        )
        for gap in gaps
        if isinstance(gap, dict)
    }
    if len(gap_keys) != len(gaps):
        raise RuntimeError("gaps.json contains duplicate source/lane/reason/record/locator rows")
    failed_fulltext_ids = {
        str(gap.get("record_id"))
        for gap in gaps
        if isinstance(gap, dict)
        and gap.get("source") == "aedes_literature_openalex"
        and gap.get("reason") in {"fulltext_fetch_failed", "fulltext_parse_failed"}
    }
    unresolved_direct = direct_candidates - fulltext_record_ids - failed_fulltext_ids
    if unresolved_direct:
        sample = ", ".join(sorted(unresolved_direct)[:5])
        raise RuntimeError(f"{len(unresolved_direct)} direct full-text candidates lack extracted text or explicit gap, sample: {sample}")

    status = json.loads(status_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    status_lit = status.get("literature") if isinstance(status, dict) else None
    receipt_lit = receipt.get("literature") if isinstance(receipt, dict) else None
    if not isinstance(status_lit, dict) or not isinstance(receipt_lit, dict):
        raise RuntimeError("literature counts missing from source_status.json or source_receipt.json")
    standalone_receipts = artifact_dir == legacy_artifact_dir
    if standalone_receipts:
        if status.get("source_id") != "aedes_literature_openalex":
            raise RuntimeError("source_status.json source_id does not identify the Aedes literature source")
        if receipt.get("source_id") != "aedes_literature_openalex":
            raise RuntimeError("source_receipt.json source_id does not identify the Aedes literature source")
        if "aedes_literature_openalex" not in status.get("sources", []):
            raise RuntimeError("source_status.json sources does not include the Aedes literature source")
        if "aedes_literature_openalex" not in receipt.get("sources", []):
            raise RuntimeError("source_receipt.json sources does not include the Aedes literature source")
    expected_pairs = {
        "record_count": literature_records,
        "payload_count": len(payload_rows),
        "pubmed_enriched_count": pubmed_enriched,
        "unpaywall_enriched_count": unpaywall_enriched,
        "direct_fulltext_candidate_count": len(direct_candidates),
        "fulltext_record_count": fulltext_records,
        "fulltext_unit_count": fulltext_units,
        "fulltext_fts_count": fulltext_fts,
    }
    required_receipt_keys = set(expected_pairs) if standalone_receipts else {"record_count"}
    for payload_name, payload in (("source_status.json", status_lit), ("source_receipt.json", receipt_lit)):
        for key, value in expected_pairs.items():
            if key not in payload:
                if key in required_receipt_keys:
                    raise RuntimeError(f"{payload_name} literature.{key} is missing")
                continue
            if int(payload.get(key, -1)) != value:
                raise RuntimeError(f"{payload_name} literature.{key} does not match SQLite")

    sources = run_json([sys.executable, "-m", "askinsects", "--artifact-dir", artifact_dir.as_posix(), "sources", "--local"])
    if "aedes_literature_openalex" not in sources.get("sources", []):
        raise RuntimeError("Aedes artifact sources command does not include aedes_literature_openalex")
    if "aedes_literature_facets" not in sources.get("sources", []):
        raise RuntimeError("Aedes artifact sources command does not include aedes_literature_facets")
    search = run_json(
        [sys.executable, "-m", "askinsects", "--artifact-dir", artifact_dir.as_posix(), "search", "literature", "Wolbachia", "--limit", "3", "--local"]
    )
    if not search.get("rows"):
        raise RuntimeError("Aedes artifact literature search returned no rows for Wolbachia")
    if artifact_dir != legacy_artifact_dir:
        return
    answer = run_json(
        [
            sys.executable,
            "-m",
            "askinsects",
            "--artifact-dir",
            artifact_dir.as_posix(),
            "ask",
            "what papers since 2020 discuss Wolbachia and Aedes aegypti?",
            "--limit",
            "3",
            "--json",
            "--local",
        ]
    )
    if answer.get("ok") is not True or not answer.get("evidence"):
        raise RuntimeError("Aedes artifact ask query did not return provenance-bearing evidence")


def check_installed_artifact_receipts() -> None:
    primary_artifact_dir = REPO_ROOT / "artifacts/mosquito-v1"
    if not (primary_artifact_dir / "source_index.sqlite").exists():
        raise RuntimeError(f"missing SQLite artifact: {primary_artifact_dir / 'source_index.sqlite'}")
    check_receipts_match_sqlite(primary_artifact_dir)

    legacy_artifact_dir = REPO_ROOT / "artifacts/aedes-literature-2020"
    if (legacy_artifact_dir / "source_index.sqlite").exists():
        check_receipts_match_sqlite(legacy_artifact_dir)


def main() -> int:
    try:
        check_required_files()
        check_forbidden_files()
        check_generic_evidence_config()
        check_active_public_surfaces()
        check_clean_clone_independence()
        check_open_source_boundary()
        check_public_identity()
        check_unit_tests()
        check_source_index_build()
        check_atomic_source_replacement()
        check_literature_source_map()
        check_mosquito_intelligence_coverage()
        check_insect_intelligence_programs()
        check_evidence_package()
        check_production_path_evaluation()
        check_aedes_source_plane_benchmark()
        check_cli()
        installed_db = REPO_ROOT / "artifacts/mosquito-v1/source_index.sqlite"
        if installed_db.exists():
            check_installed_artifact_receipts()
            check_literature_artifact()
            check_aedes_video_atoms_artifact()
            check_aedes_image_atoms_artifact()
        elif os.environ.get("ASK_INSECTS_REQUIRE_INSTALLED_ARTIFACTS") == "1":
            raise RuntimeError(f"missing SQLite artifact: {installed_db}")
    except Exception as exc:
        return fail(str(exc))
    print("verify_complete ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
