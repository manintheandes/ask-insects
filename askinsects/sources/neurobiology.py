from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import io
import json
import re
import shutil
import tarfile
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from askinsects.records import EvidenceRecord, Provenance


NEUROBIOLOGY_SOURCE_ID = "aedes_neurobiology_sources"


@dataclass(frozen=True)
class NeurobiologyBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")


NEUROBIOLOGY_SOURCE_ATOMS: tuple[dict[str, object], ...] = (
    {
        "record_id": "neuro:mosquitobrains:female-brain-atlas",
        "record_type": "brain_atlas",
        "title": "Aedes aegypti female brain atlas",
        "text": (
            "MosquitoBrains provides an online atlas of a whole-mount female Aedes aegypti brain, "
            "with annotated brain regions, z-stack navigation, and 3D reconstruction context."
        ),
        "species": "Aedes aegypti",
        "url": "https://www.mosquitobrains.org/about",
        "locator": "https://www.mosquitobrains.org/about#description",
        "license": "public web page metadata",
        "keywords": ["brain atlas", "female brain", "neuroanatomy", "3D reconstruction"],
    },
    {
        "record_id": "neuro:mosquitobrains:reference-brain-download",
        "record_type": "brain_reference_download",
        "title": "Aedes aegypti reference brain download",
        "text": (
            "MosquitoBrains lists a downloadable Aedes reference brain for the LVPib12 female strain "
            "at 1 micrometer voxel resolution, with an MHD file and companion raw data file."
        ),
        "species": "Aedes aegypti",
        "url": "https://www.mosquitobrains.org/downloads-and-links",
        "locator": "https://www.mosquitobrains.org/downloads-and-links#Aedes-Reference-Brain",
        "license": "public web page metadata",
        "keywords": ["reference brain", "download", "image volume", "LVPib12"],
    },
    {
        "record_id": "neuro:mosquitobrains:segmentation-files",
        "record_type": "brain_segmentation_download",
        "title": "Aedes aegypti brain segmentation files",
        "text": (
            "MosquitoBrains lists segmentation files used to annotate different female Aedes aegypti "
            "brain regions and generate 3D reconstructions."
        ),
        "species": "Aedes aegypti",
        "url": "https://www.mosquitobrains.org/downloads-and-links",
        "locator": "https://www.mosquitobrains.org/downloads-and-links#Segmentation-Files",
        "license": "public web page metadata",
        "keywords": ["segmentation", "brain regions", "3D reconstruction"],
    },
    {
        "record_id": "neuro:geo:GSE160740",
        "record_type": "brain_snRNA_seq_dataset",
        "title": "GSE160740 Aedes aegypti male and female brain snRNA-seq",
        "text": (
            "GEO series GSE160740 profiles single nuclei from adult male and female Aedes aegypti brains "
            "using 10x single-cell 3 prime RNA-seq, with processed MTX and TSV files and raw SRA data."
        ),
        "species": "Aedes aegypti",
        "url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE160740",
        "locator": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE160740#series",
        "license": "NCBI GEO public metadata",
        "accession": "GSE160740",
        "keywords": ["single-nucleus", "brain", "snRNA-seq", "male brain", "female brain", "neurons", "glia"],
    },
    {
        "record_id": "neuro:zenodo:mosquito-cell-atlas-14890013",
        "record_type": "cell_atlas_package",
        "title": "Mosquito Cell Atlas supplementary data",
        "text": (
            "Zenodo record 14890013 hosts supplementary data for the Aedes aegypti Mosquito Cell Atlas, "
            "including gene annotations, H5AD packages, cell type annotations, heatmaps, scripts, and analysis outputs."
        ),
        "species": "Aedes aegypti",
        "url": "https://zenodo.org/records/14890013",
        "locator": "https://zenodo.org/records/14890013#files",
        "license": "Zenodo public record metadata",
        "accession": "10.5281/zenodo.14890013",
        "keywords": ["cell atlas", "single-nucleus", "H5AD", "cell type annotations", "brain"],
    },
    {
        "record_id": "neuro:study:antennal-lobe-atlas",
        "record_type": "neurobiology_study",
        "title": "Updated antennal lobe atlas for Aedes aegypti",
        "text": (
            "The antennal lobe atlas maps the first central olfactory processing center in the Aedes aegypti brain, "
            "where olfactory sensory neuron axons project from antennae and other peripheral smell organs."
        ),
        "species": "Aedes aegypti",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7575095/",
        "locator": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7575095/#abstract",
        "license": "open access article metadata",
        "keywords": ["antennal lobe", "olfactory sensory neurons", "brain regions", "smell"],
    },
    {
        "record_id": "neuro:study:olfactory-receptor-coexpression",
        "record_type": "neurobiology_study",
        "title": "Olfactory receptor coexpression in Aedes aegypti sensory neurons",
        "text": (
            "This study used transcriptomes from tens of thousands of Aedes aegypti antennal neurons to resolve "
            "olfactory, thermosensory, and hygrosensory neuron subtypes and their receptor expression."
        ),
        "species": "Aedes aegypti",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11370346/",
        "locator": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11370346/#abstract",
        "license": "open access article metadata",
        "keywords": ["olfactory sensory neurons", "antenna", "receptors", "thermosensory", "hygrosensory"],
    },
    {
        "record_id": "neuro:study:odor-encoding-antennal-lobe",
        "record_type": "neurobiology_study",
        "title": "Odor encoding in the Aedes aegypti antennal lobe",
        "text": (
            "This study examines how odorants are represented by downstream neurons in the mosquito brain, "
            "linking olfactory sensory input to antennal lobe circuit activity."
        ),
        "species": "Aedes aegypti",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10272161/",
        "locator": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10272161/#abstract",
        "license": "open access article metadata",
        "keywords": ["odor encoding", "antennal lobe", "neural circuits", "olfaction"],
    },
)


def _record(atom: dict[str, object], *, retrieved_at: str, record_id: str | None = None) -> EvidenceRecord:
    text = str(atom["text"])
    keywords = atom.get("keywords")
    if isinstance(keywords, list):
        text = f"{text} Keywords: {', '.join(str(keyword) for keyword in keywords)}."
    return EvidenceRecord(
        record_id=record_id or str(atom["record_id"]),
        lane="neurobiology",
        source=NEUROBIOLOGY_SOURCE_ID,
        title=str(atom["title"]),
        text=text,
        species=str(atom["species"]),
        url=str(atom["url"]),
        media_url=None,
        provenance=Provenance(
            source_id=NEUROBIOLOGY_SOURCE_ID,
            locator=str(atom["locator"]),
            retrieved_at=retrieved_at,
            license=str(atom["license"]),
            source_url=str(atom["url"]),
        ),
        payload=dict(atom),
    )


def _read_gzip_text_from_tar(tar: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    stream = tar.extractfile(member)
    if stream is None:
        return ""
    with gzip.GzipFile(fileobj=stream) as gz:
        return gz.read().decode("utf-8", errors="replace")


def _geo_records(artifact_dir: Path, *, retrieved_at: str) -> tuple[list[EvidenceRecord], list[str], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    tar_path = artifact_dir / "geo" / "GSE160740" / "GSE160740_RAW.tar"
    if not tar_path.exists():
        gaps.append({"source": NEUROBIOLOGY_SOURCE_ID, "lane": "neurobiology", "reason": "geo_raw_tar_missing", "path": tar_path.as_posix()})
        return records, raw_artifacts, gaps

    raw_artifacts.append(tar_path.as_posix())
    sample_parts: dict[str, dict[str, tarfile.TarInfo]] = {}
    with tarfile.open(tar_path) as tar:
        for member in tar.getmembers():
            name = Path(member.name).name
            match = re.match(r"(?P<sample>GSM\d+_[^_]+)_(?P<kind>barcodes|features|matrix)\.tsv\.gz$", name)
            matrix_match = re.match(r"(?P<sample>GSM\d+_[^_]+)_matrix\.mtx\.gz$", name)
            if match:
                sample_parts.setdefault(match.group("sample"), {})[match.group("kind")] = member
            elif matrix_match:
                sample_parts.setdefault(matrix_match.group("sample"), {})["matrix"] = member

        for sample, parts in sorted(sample_parts.items()):
            sex = "female" if "female" in sample.lower() else "male" if "male" in sample.lower() else "unknown"
            barcode_count = 0
            feature_rows: list[tuple[str, str]] = []
            matrix_shape: dict[str, int] = {}
            if "barcodes" in parts:
                barcode_count = len([line for line in _read_gzip_text_from_tar(tar, parts["barcodes"]).splitlines() if line.strip()])
            if "features" in parts:
                for line in _read_gzip_text_from_tar(tar, parts["features"]).splitlines():
                    columns = line.split("\t")
                    if len(columns) >= 2:
                        feature_rows.append((columns[0], columns[1]))
            if "matrix" in parts:
                for line in _read_gzip_text_from_tar(tar, parts["matrix"]).splitlines():
                    if not line or line.startswith("%"):
                        continue
                    columns = line.split()
                    if len(columns) >= 3:
                        matrix_shape = {"rows": int(columns[0]), "columns": int(columns[1]), "nonzero_entries": int(columns[2])}
                    break

            title = f"GSE160740 {sex} brain snRNA-seq matrix summary"
            text = (
                f"GEO GSE160740 sample {sample} is an Aedes aegypti {sex} brain single-nucleus RNA-seq matrix "
                f"with {matrix_shape.get('rows', 0)} features, {matrix_shape.get('columns', barcode_count)} barcodes, "
                f"and {matrix_shape.get('nonzero_entries', 0)} nonzero matrix entries."
            )
            records.append(
                _record(
                    {
                        "record_id": f"neuro:geo:GSE160740:{sample}:matrix",
                        "record_type": "geo_matrix_summary",
                        "title": title,
                        "text": text,
                        "species": "Aedes aegypti",
                        "url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE160740",
                        "locator": f"{tar_path.as_posix()}#{sample}_matrix.mtx.gz",
                        "license": "NCBI GEO public metadata",
                        "sample": sample,
                        "sex": sex,
                        "matrix": matrix_shape,
                        "barcode_count": barcode_count,
                        "feature_count": len(feature_rows),
                    },
                    retrieved_at=retrieved_at,
                )
            )
            for gene_id, gene_symbol in feature_rows:
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:geo:GSE160740:{sample}:feature:{gene_id}",
                            "record_type": "geo_feature",
                            "title": f"GSE160740 {sex} brain feature {gene_symbol}",
                            "text": f"GEO GSE160740 {sex} brain snRNA-seq feature {gene_symbol} ({gene_id}) is present in the processed feature table.",
                            "species": "Aedes aegypti",
                            "url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE160740",
                            "locator": f"{tar_path.as_posix()}#{sample}_features.tsv.gz/{gene_id}",
                            "license": "NCBI GEO public metadata",
                            "sample": sample,
                            "sex": sex,
                            "gene_id": gene_id,
                            "gene_symbol": gene_symbol,
                        },
                        retrieved_at=retrieved_at,
                    )
                )
    return records, raw_artifacts, gaps


def _int_value(value: object) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def _sra_records(artifact_dir: Path, *, retrieved_at: str) -> tuple[list[EvidenceRecord], list[str], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    runinfo_path = artifact_dir / "geo" / "SRP290992_runinfo.csv"
    if not runinfo_path.exists():
        gaps.append(
            {
                "source": NEUROBIOLOGY_SOURCE_ID,
                "lane": "neurobiology",
                "reason": "sra_runinfo_missing",
                "path": runinfo_path.as_posix(),
            }
        )
        return records, raw_artifacts, gaps

    raw_artifacts.append(runinfo_path.as_posix())
    rows = list(csv.DictReader(runinfo_path.read_text(encoding="utf-8").splitlines()))
    sample_rows: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        run = str(row.get("Run", "")).strip()
        sample_name = str(row.get("SampleName", "")).strip() or str(row.get("Sample", "")).strip()
        if sample_name:
            sample_rows.setdefault(sample_name, []).append(row)
        records.append(
            _record(
                {
                    "record_id": f"neuro:sra:SRP290992:run:{run}",
                    "record_type": "sra_run",
                    "title": f"GSE160740 SRA run {run}",
                    "text": (
                        f"SRA SRP290992 run {run} belongs to sample {sample_name} for Aedes aegypti brain RNA-seq raw read metadata. "
                        f"Library {row.get('LibraryStrategy')} {row.get('LibraryLayout')}; "
                        f"{row.get('spots')} spots, {row.get('bases')} bases, {row.get('size_MB')} MB."
                    ),
                    "species": "Aedes aegypti",
                    "url": "https://www.ncbi.nlm.nih.gov/sra?term=SRP290992",
                    "locator": f"{runinfo_path.as_posix()}#Run/{run}",
                    "license": "NCBI SRA public metadata",
                    "run": run,
                    "experiment": row.get("Experiment"),
                    "sample": row.get("Sample"),
                    "biosample": row.get("BioSample"),
                    "sample_name": sample_name,
                    "library_strategy": row.get("LibraryStrategy"),
                    "library_layout": row.get("LibraryLayout"),
                    "spots": _int_value(row.get("spots")),
                    "bases": _int_value(row.get("bases")),
                    "size_mb": _int_value(row.get("size_MB")),
                    "download_path": row.get("download_path"),
                    "raw_runinfo": row,
                },
                retrieved_at=retrieved_at,
            )
        )

    for sample_name, grouped_rows in sorted(sample_rows.items()):
        total_spots = sum(_int_value(row.get("spots")) for row in grouped_rows)
        total_bases = sum(_int_value(row.get("bases")) for row in grouped_rows)
        total_size_mb = sum(_int_value(row.get("size_MB")) for row in grouped_rows)
        records.append(
            _record(
                {
                    "record_id": f"neuro:sra:SRP290992:sample:{sample_name}",
                    "record_type": "sra_sample_summary",
                    "title": f"GSE160740 SRA sample {sample_name}",
                    "text": (
                        f"SRA SRP290992 sample {sample_name} has {len(grouped_rows)} public raw read run(s), "
                        f"{total_spots} spots, {total_bases} bases, and {total_size_mb} MB in runinfo metadata."
                    ),
                    "species": "Aedes aegypti",
                    "url": "https://www.ncbi.nlm.nih.gov/sra?term=SRP290992",
                    "locator": f"{runinfo_path.as_posix()}#SampleName/{sample_name}",
                    "license": "NCBI SRA public metadata",
                    "sample_name": sample_name,
                    "run_count": len(grouped_rows),
                    "runs": [row.get("Run") for row in grouped_rows],
                    "total_spots": total_spots,
                    "total_bases": total_bases,
                    "total_size_mb": total_size_mb,
                },
                retrieved_at=retrieved_at,
            )
        )
    run_payloads = [
        {
            "run": row.get("Run"),
            "sample_name": row.get("SampleName") or row.get("Sample"),
            "download_path": row.get("download_path"),
            "size_mb": _int_value(row.get("size_MB")),
            "spots": _int_value(row.get("spots")),
            "bases": _int_value(row.get("bases")),
        }
        for row in rows
    ]
    total_size_mb = sum(int(run["size_mb"]) for run in run_payloads)
    records.append(
        _record(
            {
                "record_id": "neuro:sra:SRP290992:raw-access",
                "record_type": "sra_raw_access",
                "title": "GSE160740 SRA raw read access manifest",
                "text": (
                    f"SRA SRP290992 exposes {len(run_payloads)} raw read run(s) for Aedes aegypti brain RNA-seq, "
                    f"totaling {total_size_mb} MB in public runinfo metadata. Download URLs are preserved per run."
                ),
                "species": "Aedes aegypti",
                "url": "https://www.ncbi.nlm.nih.gov/sra?term=SRP290992",
                "locator": f"{runinfo_path.as_posix()}#download_path",
                "license": "NCBI SRA public metadata",
                "run_count": len(run_payloads),
                "total_size_mb": total_size_mb,
                "runs": run_payloads,
            },
            retrieved_at=retrieved_at,
        )
    )
    records.append(
        _record(
            {
                "record_id": "neuro:sra:SRP290992:reanalysis-workflow",
                "record_type": "sra_reanalysis_workflow",
                "title": "GSE160740 raw SRA reanalysis workflow",
                "text": (
                    "Raw SRA reanalysis for GSE160740 is mechanically defined from public runinfo: download each SRR run, "
                    "convert with fasterq-dump --split-files, then align/count against the Aedes aegypti reference genome "
                    "with a 10x-aware RNA-seq workflow such as STARsolo or kallisto/bustools. "
                    "The source index records the workflow and inputs; it does not execute the compute-heavy alignment."
                ),
                "species": "Aedes aegypti",
                "url": "https://www.ncbi.nlm.nih.gov/sra?term=SRP290992",
                "locator": f"{runinfo_path.as_posix()}#reanalysis-workflow",
                "license": "NCBI SRA public metadata",
                "execution_status": "not_executed_by_source_index",
                "inputs": run_payloads,
                "commands": [
                    "prefetch <SRR>",
                    "fasterq-dump --split-files <SRR>",
                    "STARsolo or kallisto/bustools alignment/counting against GCF_002204515.2",
                ],
            },
            retrieved_at=retrieved_at,
        )
    )
    return records, raw_artifacts, gaps

def _xlsx_sheet_names(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as workbook:
            with workbook.open("xl/workbook.xml") as handle:
                root = ET.fromstring(handle.read())
    except (KeyError, ET.ParseError, zipfile.BadZipFile):
        return []
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    names: list[str] = []
    for sheet in root.findall(".//main:sheet", namespace):
        name = sheet.attrib.get("name")
        if name:
            names.append(name)
    return names


def _clean_hdf5_value(value: object) -> object:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): _clean_hdf5_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_hdf5_value(item) for item in value]
    if hasattr(value, "tolist"):
        return _clean_hdf5_value(value.tolist())
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    return value


def _hdf5_attrs(node: object) -> dict[str, object]:
    attrs = getattr(node, "attrs", {})
    cleaned: dict[str, object] = {}
    for key, value in attrs.items():
        cleaned[str(key)] = _clean_hdf5_value(value)
    return cleaned


def _dataset_sample(dataset: object, limit: int = 5) -> list[object]:
    try:
        values = dataset[:limit]  # type: ignore[index]
    except Exception:
        return []
    try:
        return [_clean_hdf5_value(value) for value in values.tolist()]
    except AttributeError:
        return [_clean_hdf5_value(value) for value in values]


def _h5ad_matrix_shape(h5: object) -> list[int] | None:
    x = h5.get("X")  # type: ignore[attr-defined]
    if x is None:
        return None
    shape = getattr(x, "shape", None)
    if shape:
        return [int(value) for value in shape]
    attrs = _hdf5_attrs(x)
    attr_shape = attrs.get("shape")
    if isinstance(attr_shape, list):
        return [int(value) for value in attr_shape]
    if isinstance(attr_shape, tuple):
        return [int(value) for value in attr_shape]
    return None


def _h5ad_axis_count(h5: object, axis: str) -> int | None:
    group = h5.get(axis)  # type: ignore[attr-defined]
    if group is None:
        return None
    index = group.get("_index")  # type: ignore[attr-defined]
    if index is not None and getattr(index, "shape", None):
        return int(index.shape[0])
    return None


def _h5ad_column_payload(group: object, name: str) -> dict[str, object] | None:
    node = group.get(name)  # type: ignore[attr-defined]
    if node is None:
        return None
    if hasattr(node, "shape"):
        return {
            "column": name,
            "kind": "dataset",
            "shape": [int(value) for value in getattr(node, "shape", ())],
            "dtype": str(getattr(node, "dtype", "unknown")),
            "sample_values": _dataset_sample(node),
            "attrs": _hdf5_attrs(node),
        }
    categories = node.get("categories") if hasattr(node, "get") else None
    codes = node.get("codes") if hasattr(node, "get") else None
    payload: dict[str, object] = {
        "column": name,
        "kind": "group",
        "attrs": _hdf5_attrs(node),
    }
    if categories is not None:
        payload["categories"] = _dataset_sample(categories, limit=20)
        payload["category_count"] = int(categories.shape[0]) if getattr(categories, "shape", None) else None
    if codes is not None:
        payload["code_count"] = int(codes.shape[0]) if getattr(codes, "shape", None) else None
        payload["code_sample"] = _dataset_sample(codes)
    return payload


def _h5ad_records_from_file(
    *,
    path: Path,
    locator_base: str,
    archive_key: str,
    member_name: str,
    url: str,
    retrieved_at: str,
) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    try:
        import h5py  # type: ignore[import-not-found]
    except ImportError:
        gaps.append(
            {
                "source": NEUROBIOLOGY_SOURCE_ID,
                "lane": "neurobiology",
                "reason": "h5py_not_installed",
                "path": path.as_posix(),
                "member": member_name,
            }
        )
        return records, gaps

    try:
        h5 = h5py.File(path, "r")
    except OSError as exc:
        gaps.append(
            {
                "source": NEUROBIOLOGY_SOURCE_ID,
                "lane": "neurobiology",
                "reason": "h5ad_not_readable",
                "path": path.as_posix(),
                "member": member_name,
                "error": str(exc),
            }
        )
        return records, gaps

    with h5:
        matrix_shape = _h5ad_matrix_shape(h5)
        obs_count = _h5ad_axis_count(h5, "obs")
        var_count = _h5ad_axis_count(h5, "var")
        records.append(
            _record(
                {
                    "record_id": f"neuro:zenodo:14890013:h5ad-summary:{member_name}",
                    "record_type": "h5ad_summary",
                    "title": f"Mosquito Cell Atlas H5AD summary {member_name}",
                    "text": (
                        f"H5AD file {member_name} is an AnnData/HDF5 artifact from {archive_key}. "
                        f"Matrix shape {matrix_shape}; obs count {obs_count}; var count {var_count}."
                    ),
                    "species": "Aedes aegypti",
                    "url": url,
                    "locator": f"{locator_base}#/",
                    "license": "CC-BY-4.0 metadata",
                    "archive": archive_key,
                    "member": member_name,
                    "matrix_shape": matrix_shape,
                    "obs_count": obs_count,
                    "var_count": var_count,
                    "attrs": _hdf5_attrs(h5),
                },
                retrieved_at=retrieved_at,
            )
        )

        def visitor(name: str, node: object) -> None:
            if not name:
                return
            if hasattr(node, "shape"):
                shape = [int(value) for value in getattr(node, "shape", ())]
                dtype = str(getattr(node, "dtype", "unknown"))
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:zenodo:14890013:h5ad-dataset:{member_name}:{name}",
                            "record_type": "h5ad_dataset",
                            "title": f"H5AD dataset {name}",
                            "text": f"H5AD file {member_name} contains dataset {name} with shape {shape} and dtype {dtype}.",
                            "species": "Aedes aegypti",
                            "url": url,
                            "locator": f"{locator_base}#/{name}",
                            "license": "CC-BY-4.0 metadata",
                            "archive": archive_key,
                            "member": member_name,
                            "hdf5_path": name,
                            "shape": shape,
                            "dtype": dtype,
                            "attrs": _hdf5_attrs(node),
                            "sample_values": _dataset_sample(node),
                        },
                        retrieved_at=retrieved_at,
                    )
                )
            else:
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:zenodo:14890013:h5ad-group:{member_name}:{name}",
                            "record_type": "h5ad_group",
                            "title": f"H5AD group {name}",
                            "text": f"H5AD file {member_name} contains group {name}.",
                            "species": "Aedes aegypti",
                            "url": url,
                            "locator": f"{locator_base}#/{name}",
                            "license": "CC-BY-4.0 metadata",
                            "archive": archive_key,
                            "member": member_name,
                            "hdf5_path": name,
                            "attrs": _hdf5_attrs(node),
                        },
                        retrieved_at=retrieved_at,
                    )
                )

        h5.visititems(visitor)

        for axis, record_type, label in (("obs", "h5ad_obs_column", "obs"), ("var", "h5ad_var_column", "var")):
            group = h5.get(axis)
            if group is None:
                continue
            for column in sorted(group.keys()):
                if column == "_index":
                    continue
                payload = _h5ad_column_payload(group, column)
                if payload is None:
                    continue
                record_id_type = record_type.replace("_", "-")
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:zenodo:14890013:{record_id_type}:{member_name}:{column}",
                            "record_type": record_type,
                            "title": f"H5AD {label} column {column}",
                            "text": f"H5AD file {member_name} contains AnnData {label} column {column}.",
                            "species": "Aedes aegypti",
                            "url": url,
                            "locator": f"{locator_base}#/{axis}/{column}",
                            "license": "CC-BY-4.0 metadata",
                            "archive": archive_key,
                            "member": member_name,
                            "axis": axis,
                            **payload,
                        },
                        retrieved_at=retrieved_at,
                        record_id=f"neuro:zenodo:14890013:{record_id_type}:{member_name}:{column}",
                    )
                )
    return records, gaps


def _h5ad_records_from_zip_member(
    *,
    archive: zipfile.ZipFile,
    path: Path,
    key: str,
    member_name: str,
    url: str,
    retrieved_at: str,
) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    with tempfile.TemporaryDirectory(prefix="ask-insects-h5ad-") as tmpdir:
        out_path = Path(tmpdir) / Path(member_name).name
        with archive.open(member_name) as source, out_path.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        return _h5ad_records_from_file(
            path=out_path,
            locator_base=f"{path.as_posix()}#{member_name}",
            archive_key=key,
            member_name=member_name,
            url=url,
            retrieved_at=retrieved_at,
        )


def _zip_member_records(
    *,
    path: Path,
    key: str,
    url: str,
    retrieved_at: str,
) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            for info in infos:
                member_name = info.filename
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:zenodo:14890013:zip-member:{key}:{member_name}",
                            "record_type": "zenodo_zip_member",
                            "title": f"Mosquito Cell Atlas ZIP member {member_name}",
                            "text": (
                                f"Zenodo archive {key} contains {member_name}. "
                                f"Uncompressed size {info.file_size} bytes, compressed size {info.compress_size} bytes."
                            ),
                            "species": "Aedes aegypti",
                            "url": url,
                            "locator": f"{path.as_posix()}#{member_name}",
                            "license": "CC-BY-4.0 metadata",
                            "archive": key,
                            "member": member_name,
                            "file_size": info.file_size,
                            "compressed_size": info.compress_size,
                        },
                        retrieved_at=retrieved_at,
                    )
                )
                if member_name.lower().endswith(".h5ad"):
                    h5ad_records, h5ad_gaps = _h5ad_records_from_zip_member(
                        archive=archive,
                        path=path,
                        key=key,
                        member_name=member_name,
                        url=url,
                        retrieved_at=retrieved_at,
                    )
                    records.extend(h5ad_records)
                    gaps.extend(h5ad_gaps)
    except zipfile.BadZipFile:
        gaps.append(
            {
                "source": NEUROBIOLOGY_SOURCE_ID,
                "lane": "neurobiology",
                "reason": "zenodo_zip_not_readable",
                "path": path.as_posix(),
            }
        )
        return records, gaps
    return records, gaps


def _zenodo_records(artifact_dir: Path, *, retrieved_at: str) -> tuple[list[EvidenceRecord], list[str], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    zenodo_dir = artifact_dir / "zenodo" / "14890013"
    record_path = zenodo_dir / "record.json"
    if not record_path.exists():
        gaps.append({"source": NEUROBIOLOGY_SOURCE_ID, "lane": "neurobiology", "reason": "zenodo_record_json_missing", "path": record_path.as_posix()})
        return records, raw_artifacts, gaps

    raw_artifacts.append(record_path.as_posix())
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    for file_payload in payload.get("files", []):
        key = str(file_payload.get("key", "unknown"))
        url = str(file_payload.get("links", {}).get("self", "https://zenodo.org/records/14890013"))
        local_path = zenodo_dir / key
        downloaded = local_path.exists()
        if downloaded:
            raw_artifacts.append(local_path.as_posix())
        records.append(
            _record(
                {
                    "record_id": f"neuro:zenodo:14890013:file:{key}",
                    "record_type": "zenodo_file",
                    "title": f"Mosquito Cell Atlas file {key}",
                    "text": (
                        f"Zenodo file {key} is part of the Mosquito Cell Atlas supplementary data. "
                        f"Size {file_payload.get('size', 'unknown')} bytes. Downloaded locally: {downloaded}."
                    ),
                    "species": "Aedes aegypti",
                    "url": url,
                    "locator": local_path.as_posix() if downloaded else url,
                    "license": "CC-BY-4.0 metadata",
                    "zenodo_file": file_payload,
                    "downloaded": downloaded,
                },
                retrieved_at=retrieved_at,
            )
        )
        if downloaded and key.endswith(".xlsx"):
            for sheet_name in _xlsx_sheet_names(local_path):
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:zenodo:14890013:workbook:{key}:sheet:{sheet_name}",
                            "record_type": "zenodo_workbook_sheet",
                            "title": f"Mosquito Cell Atlas workbook sheet {sheet_name}",
                            "text": f"Supplementary workbook {key} contains sheet {sheet_name}, a queryable entry point into Mosquito Cell Atlas table metadata.",
                            "species": "Aedes aegypti",
                            "url": url,
                            "locator": f"{local_path.as_posix()}#sheet/{sheet_name}",
                            "license": "CC-BY-4.0 metadata",
                            "workbook": key,
                            "sheet": sheet_name,
                        },
                        retrieved_at=retrieved_at,
                    )
                )
        if downloaded and key.endswith(".zip"):
            zip_records, zip_gaps = _zip_member_records(
                path=local_path,
                key=key,
                url=url,
                retrieved_at=retrieved_at,
            )
            records.extend(zip_records)
            gaps.extend(zip_gaps)
    return records, raw_artifacts, gaps


def _metaimage_header(text: str) -> dict[str, object]:
    header: dict[str, object] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        header[key] = value
        if key == "ElementDataFile":
            break
    for key in ("DimSize", "ElementSpacing", "ElementSize"):
        if isinstance(header.get(key), str):
            header[f"{key}_values"] = str(header[key]).split()
    return header


def _read_metaimage_header_and_data_offset(payload: bytes) -> tuple[dict[str, object], int]:
    offset = 0
    lines: list[str] = []
    for raw_line in payload.splitlines(keepends=True):
        offset += len(raw_line)
        line = raw_line.decode("utf-8", errors="replace")
        lines.append(line)
        if line.strip().startswith("ElementDataFile"):
            break
    return _metaimage_header("".join(lines)), offset


def _dim_size_values(header: dict[str, object]) -> list[int]:
    raw_values = header.get("DimSize_values")
    if not isinstance(raw_values, list):
        return []
    values: list[int] = []
    for value in raw_values:
        try:
            values.append(int(str(value)))
        except ValueError:
            return []
    return values


def _byte_order_msb(header: dict[str, object]) -> bool:
    value = str(header.get("BinaryDataByteOrderMSB", "False")).strip().lower()
    return value in {"1", "true", "yes"}


def _raw_member_for_header(member_path: str, header: dict[str, object]) -> str | None:
    data_file = header.get("ElementDataFile")
    if not isinstance(data_file, str) or data_file.upper() == "LOCAL":
        return None
    parent = str(Path(member_path).parent)
    if parent == ".":
        return data_file
    return f"{parent}/{data_file}"


def _brain_volume_record(
    *,
    archive_name: str,
    member_name: str,
    header: dict[str, object],
    locator: str,
    retrieved_at: str,
    voxel_access: dict[str, object] | None = None,
) -> EvidenceRecord:
    dim_size = header.get("DimSize")
    spacing = header.get("ElementSpacing") or header.get("ElementSize")
    element_type = header.get("ElementType")
    queryable_text = " Exact voxel values are queryable by coordinate." if voxel_access else ""
    return _record(
        {
            "record_id": f"neuro:mosquitobrains:volume:{archive_name}:{member_name}",
            "record_type": "brain_volume_header",
            "title": f"MosquitoBrains volume header {member_name}",
            "text": (
                f"MosquitoBrains volume {member_name} has DimSize {dim_size}, spacing {spacing}, "
                f"and element type {element_type}.{queryable_text}"
            ),
            "species": "Aedes aegypti",
            "url": "https://www.mosquitobrains.org/downloads-and-links",
            "locator": locator,
            "license": "public web page metadata",
            "archive": archive_name,
            "member": member_name,
            "header": header,
            "dim_size": dim_size,
            "spacing": spacing,
            "element_type": element_type,
            "voxel_access": voxel_access,
        },
        retrieved_at=retrieved_at,
    )


def _brain_region_label_records(
    *,
    archive_name: str,
    member_name: str,
    text: str,
    locator: str,
    retrieved_at: str,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for line in text.splitlines():
        match = re.match(
            r"\s*(?P<idx>\d+)\s+(?P<r>\d+)\s+(?P<g>\d+)\s+(?P<b>\d+)\s+(?P<a>[0-9.]+)\s+(?P<vis>\d+)\s+(?P<msh>\d+)\s+\"(?P<label>[^\"]+)\"",
            line,
        )
        if not match:
            continue
        idx = match.group("idx")
        label = match.group("label")
        records.append(
            _record(
                {
                    "record_id": f"neuro:mosquitobrains:label:{archive_name}:{member_name}:{idx}",
                    "record_type": "brain_region_label",
                    "title": f"MosquitoBrains brain region label {label}",
                    "text": f"MosquitoBrains label file {member_name} defines region {idx}: {label}.",
                    "species": "Aedes aegypti",
                    "url": "https://www.mosquitobrains.org/downloads-and-links",
                    "locator": f"{locator}#label/{idx}",
                    "license": "public web page metadata",
                    "archive": archive_name,
                    "member": member_name,
                    "label_index": int(idx),
                    "label": label,
                    "rgb": [int(match.group("r")), int(match.group("g")), int(match.group("b"))],
                    "alpha": float(match.group("a")),
                    "visible": match.group("vis") == "1",
                    "mesh_visible": match.group("msh") == "1",
                },
                retrieved_at=retrieved_at,
            )
        )
    return records


def _mosquitobrains_archive_detail_records(
    *,
    archive_name: str,
    member_name: str,
    member_path: str,
    data: bytes,
    locator: str,
    archive_path: Path,
    nested_archive_member: str | None,
    retrieved_at: str,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    lower = member_name.lower()
    if lower.endswith((".mha", ".mhd")):
        header, data_offset = _read_metaimage_header_and_data_offset(data)
        voxel_access: dict[str, object] | None = None
        dim_size = _dim_size_values(header)
        element_type = header.get("ElementType")
        if dim_size and isinstance(element_type, str):
            if str(header.get("ElementDataFile", "")).upper() == "LOCAL":
                voxel_access = {
                    "kind": "nested_zip_mha_local" if nested_archive_member else "zip_mha_local",
                    "archive_path": archive_path.as_posix(),
                    "nested_archive_member": nested_archive_member,
                    "member": member_path,
                    "data_offset": data_offset,
                    "dim_size": dim_size,
                    "element_type": element_type,
                    "byte_order_msb": _byte_order_msb(header),
                }
            else:
                raw_member = _raw_member_for_header(member_path, header)
                if raw_member:
                    voxel_access = {
                        "kind": "nested_zip_raw_member" if nested_archive_member else "zip_raw_member",
                        "archive_path": archive_path.as_posix(),
                        "nested_archive_member": nested_archive_member,
                        "header_member": member_path,
                        "raw_member": raw_member,
                        "data_offset": 0,
                        "dim_size": dim_size,
                        "element_type": element_type,
                        "byte_order_msb": _byte_order_msb(header),
                    }
        records.append(
            _brain_volume_record(
                archive_name=archive_name,
                member_name=member_name,
                header=header,
                locator=locator,
                retrieved_at=retrieved_at,
                voxel_access=voxel_access,
            )
        )
    elif lower.endswith(".txt") and "label" in lower:
        records.extend(
            _brain_region_label_records(
                archive_name=archive_name,
                member_name=member_name,
                text=data.decode("utf-8", errors="replace"),
                locator=locator,
                retrieved_at=retrieved_at,
            )
        )
    return records


def _mosquitobrains_records(artifact_dir: Path, *, retrieved_at: str) -> tuple[list[EvidenceRecord], list[str], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    html_path = artifact_dir / "mosquitobrains" / "downloads-and-links.html"
    if not html_path.exists():
        gaps.append({"source": NEUROBIOLOGY_SOURCE_ID, "lane": "neurobiology", "reason": "mosquitobrains_download_page_missing", "path": html_path.as_posix()})
        return records, raw_artifacts, gaps
    raw_artifacts.append(html_path.as_posix())
    html = html_path.read_text(encoding="utf-8", errors="replace")
    seen_ids: set[str] = set()
    for index, url in enumerate(sorted(set(re.findall(r"https://www\.dropbox\.com/[^\"']+", html))), start=1):
        label = "Segmentation Files" if "segment" in url.lower() else "Aedes Reference Brain"
        base_record_id = f"neuro:mosquitobrains:dropbox:{_slug(label)}"
        record_id = base_record_id if base_record_id not in seen_ids else f"{base_record_id}:{index}"
        seen_ids.add(record_id)
        records.append(
            _record(
                {
                    "record_id": record_id,
                    "record_type": "mosquitobrains_download_link",
                    "title": f"MosquitoBrains {label}",
                    "text": f"MosquitoBrains exposes a public Dropbox source link for {label}. The link is preserved as a raw source artifact locator.",
                    "species": "Aedes aegypti",
                    "url": url,
                    "locator": f"{html_path.as_posix()}#{url}",
                    "license": "public web page metadata",
                    "download_url": url,
                    "label": label,
                },
                retrieved_at=retrieved_at,
            )
        )
    download_dir = html_path.parent / "downloads"
    for path in sorted(download_dir.glob("*")):
        if not path.is_file():
            continue
        raw_artifacts.append(path.as_posix())
        label = path.stem.replace("-", " ").replace("_", " ")
        records.append(
            _record(
                {
                    "record_id": f"neuro:mosquitobrains:file:{path.name}",
                    "record_type": "mosquitobrains_downloaded_file",
                    "title": f"MosquitoBrains downloaded file {path.name}",
                    "text": f"MosquitoBrains downloaded artifact {path.name} is present in the local neurobiology cache. Size {path.stat().st_size} bytes.",
                    "species": "Aedes aegypti",
                    "url": "https://www.mosquitobrains.org/downloads-and-links",
                    "locator": path.as_posix(),
                    "license": "public web page metadata",
                    "path": path.as_posix(),
                    "label": label,
                    "size": path.stat().st_size,
                },
                retrieved_at=retrieved_at,
            )
        )
        if path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(path) as archive:
                    members = [info for info in archive.infolist() if not info.is_dir()]
            except zipfile.BadZipFile:
                gaps.append(
                    {
                        "source": NEUROBIOLOGY_SOURCE_ID,
                        "lane": "neurobiology",
                        "reason": "mosquitobrains_zip_not_readable",
                        "path": path.as_posix(),
                    }
                )
                continue
            for info in members:
                member_locator = f"{path.as_posix()}#{info.filename}"
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:mosquitobrains:zip-member:{path.name}:{info.filename}",
                            "record_type": "mosquitobrains_zip_member",
                            "title": f"MosquitoBrains ZIP member {info.filename}",
                            "text": (
                                f"MosquitoBrains archive {path.name} contains {info.filename}. "
                                f"Uncompressed size {info.file_size} bytes, compressed size {info.compress_size} bytes."
                            ),
                            "species": "Aedes aegypti",
                            "url": "https://www.mosquitobrains.org/downloads-and-links",
                            "locator": member_locator,
                            "license": "public web page metadata",
                            "archive": path.name,
                            "member": info.filename,
                            "file_size": info.file_size,
                            "compressed_size": info.compress_size,
                        },
                        retrieved_at=retrieved_at,
                    )
                )
                with zipfile.ZipFile(path) as archive:
                    data = archive.read(info.filename)
                if info.filename.lower().endswith(".zip"):
                    try:
                        with zipfile.ZipFile(io.BytesIO(data)) as nested:
                            for nested_info in nested.infolist():
                                if nested_info.is_dir():
                                    continue
                                nested_data = nested.read(nested_info.filename)
                                records.extend(
                                    _mosquitobrains_archive_detail_records(
                                        archive_name=path.name,
                                        member_name=f"{info.filename}:{nested_info.filename}",
                                        member_path=nested_info.filename,
                                        data=nested_data,
                                        locator=f"{member_locator}#{nested_info.filename}",
                                        archive_path=path,
                                        nested_archive_member=info.filename,
                                        retrieved_at=retrieved_at,
                                    )
                                )
                    except zipfile.BadZipFile:
                        gaps.append(
                            {
                                "source": NEUROBIOLOGY_SOURCE_ID,
                                "lane": "neurobiology",
                                "reason": "mosquitobrains_nested_zip_not_readable",
                                "path": path.as_posix(),
                                "member": info.filename,
                            }
                        )
                else:
                    records.extend(
                        _mosquitobrains_archive_detail_records(
                            archive_name=path.name,
                            member_name=info.filename,
                            member_path=info.filename,
                            data=data,
                            locator=member_locator,
                            archive_path=path,
                            nested_archive_member=None,
                            retrieved_at=retrieved_at,
                        )
                    )
    return records, raw_artifacts, gaps


def _connectome_records(artifact_dir: Path, *, retrieved_at: str) -> tuple[list[EvidenceRecord], list[str], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    root = artifact_dir / "connectome" / "aedes_public"
    repo_path = root / "repo.json"
    if not repo_path.exists():
        return records, raw_artifacts, gaps
    raw_artifacts.append(repo_path.as_posix())
    payload = json.loads(repo_path.read_text(encoding="utf-8"))
    html_url = str(payload.get("html_url") or "https://github.com/htem/aedes_public")
    records.append(
        _record(
            {
                "record_id": "neuro:connectome:aedes_public:repository",
                "record_type": "connectome_repository",
                "title": "Public Aedes EM/CATMAID repository metadata",
                "text": (
                    f"Repository {payload.get('full_name', 'htem/aedes_public')} is mapped as public Aedes connectome-adjacent metadata. "
                    f"Description: {payload.get('description', 'missing')}."
                ),
                "species": "Aedes aegypti",
                "url": html_url,
                "locator": repo_path.as_posix(),
                "license": str((payload.get("license") or {}).get("spdx_id", "GitHub public repository metadata")) if isinstance(payload.get("license"), dict) else "GitHub public repository metadata",
                "repository": payload,
                "keywords": ["connectome", "CATMAID", "EM", "CO2 circuit"],
            },
            retrieved_at=retrieved_at,
        )
    )
    readme_path = root / "README.md"
    catmaid_url = "https://radagast.hms.harvard.edu/catmaidaedes/?pid=1&zp=173280&yp=235408&xp=324692&tool=navigator&sid0=1&s0=1"
    if readme_path.exists():
        raw_artifacts.append(readme_path.as_posix())
        readme_text = readme_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"https://radagast\.hms\.harvard\.edu/catmaidaedes/\?[^)\s]+", readme_text)
        if match:
            catmaid_url = match.group(0)
        records.append(
            _record(
                {
                    "record_id": "neuro:connectome:aedes_public:readme",
                    "record_type": "connectome_repository_readme",
                    "title": "Aedes public repository README EM dataset locator",
                    "text": (
                        "The htem/aedes_public README maps the public Aedes EM dataset to a web-based CATMAID project. "
                        f"CATMAID URL: {catmaid_url}."
                    ),
                    "species": "Aedes aegypti",
                    "url": html_url,
                    "locator": readme_path.as_posix(),
                    "license": "GitHub public repository metadata",
                    "catmaid_url": catmaid_url,
                    "keywords": ["CATMAID", "EM dataset", "public Aedes connectome"],
                },
                retrieved_at=retrieved_at,
            )
        )
    catmaid_dir = root / "catmaid"
    projects_path = catmaid_dir / "projects.json"
    if projects_path.exists():
        raw_artifacts.append(projects_path.as_posix())
        projects_payload = json.loads(projects_path.read_text(encoding="utf-8"))
        if isinstance(projects_payload, list):
            for project in projects_payload:
                if not isinstance(project, dict):
                    continue
                project_id = str(project.get("id", "unknown"))
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:connectome:catmaid:project:{project_id}",
                            "record_type": "catmaid_project",
                            "title": f"CATMAID Aedes project {project_id}",
                            "text": (
                                f"Public CATMAID project {project_id} for Aedes EM data is accessible. "
                                f"Comment: {project.get('comment', '')}."
                            ),
                            "species": "Aedes aegypti",
                            "url": catmaid_url,
                            "locator": f"{projects_path.as_posix()}#project/{project_id}",
                            "license": "CATMAID public metadata",
                            "project": project,
                            "keywords": ["CATMAID", "EM dataset", "project"],
                        },
                        retrieved_at=retrieved_at,
                    )
                )
    stacks_path = catmaid_dir / "stacks.json"
    stack_info_by_id: dict[str, dict[str, object]] = {}
    for stack_info_path in sorted(catmaid_dir.glob("stack_*_info.json")):
        raw_artifacts.append(stack_info_path.as_posix())
        stack_id = stack_info_path.stem.removeprefix("stack_").removesuffix("_info")
        stack_payload = json.loads(stack_info_path.read_text(encoding="utf-8"))
        if isinstance(stack_payload, dict):
            stack_info_by_id[stack_id] = stack_payload
    if stacks_path.exists():
        raw_artifacts.append(stacks_path.as_posix())
        stacks_payload = json.loads(stacks_path.read_text(encoding="utf-8"))
        if isinstance(stacks_payload, list):
            for stack in stacks_payload:
                if not isinstance(stack, dict):
                    continue
                stack_id = str(stack.get("id", "unknown"))
                info = stack_info_by_id.get(stack_id, {})
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:connectome:catmaid:stack:{stack_id}",
                            "record_type": "catmaid_stack",
                            "title": f"CATMAID Aedes stack {stack.get('title', stack_id)}",
                            "text": (
                                f"Public CATMAID stack {stack.get('title', stack_id)} is accessible for Aedes EM image data. "
                                f"Dimensions: {info.get('dimension')}; resolution: {info.get('resolution')}."
                            ),
                            "species": "Aedes aegypti",
                            "url": catmaid_url,
                            "locator": f"{stacks_path.as_posix()}#stack/{stack_id}",
                            "license": "CATMAID public metadata",
                            "stack": stack,
                            "stack_info": info,
                            "keywords": ["CATMAID", "EM stack", "image data"],
                        },
                        retrieved_at=retrieved_at,
                    )
                )
    annotations_path = catmaid_dir / "annotations.json"
    if annotations_path.exists():
        raw_artifacts.append(annotations_path.as_posix())
        annotations_payload = json.loads(annotations_path.read_text(encoding="utf-8"))
        annotations = annotations_payload.get("annotations") if isinstance(annotations_payload, dict) else None
        if isinstance(annotations, list):
            for annotation in annotations:
                if not isinstance(annotation, dict):
                    continue
                annotation_id = str(annotation.get("id", "unknown"))
                name = str(annotation.get("name", annotation_id))
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:connectome:catmaid:annotation:{annotation_id}",
                            "record_type": "catmaid_annotation",
                            "title": f"CATMAID Aedes annotation {name}",
                            "text": f"Public CATMAID annotation {annotation_id} is named {name}.",
                            "species": "Aedes aegypti",
                            "url": catmaid_url,
                            "locator": f"{annotations_path.as_posix()}#annotation/{annotation_id}",
                            "license": "CATMAID public metadata",
                            "annotation": annotation,
                            "keywords": ["CATMAID", "annotation", name],
                        },
                        retrieved_at=retrieved_at,
                    )
                )
    volumes_path = catmaid_dir / "volumes.json"
    if volumes_path.exists():
        raw_artifacts.append(volumes_path.as_posix())
        volumes_payload = json.loads(volumes_path.read_text(encoding="utf-8"))
        columns = volumes_payload.get("columns") if isinstance(volumes_payload, dict) else None
        data = volumes_payload.get("data") if isinstance(volumes_payload, dict) else None
        if isinstance(columns, list) and isinstance(data, list):
            for row in data:
                if not isinstance(row, list):
                    continue
                volume = {str(column): row[index] if index < len(row) else None for index, column in enumerate(columns)}
                volume_id = str(volume.get("id", "unknown"))
                records.append(
                    _record(
                        {
                            "record_id": f"neuro:connectome:catmaid:volume:{volume_id}",
                            "record_type": "catmaid_volume",
                            "title": f"CATMAID Aedes volume {volume.get('name', volume_id)}",
                            "text": (
                                f"Public CATMAID volume {volume_id} is named {volume.get('name', '')}. "
                                f"Area: {volume.get('area')}; volume: {volume.get('volume')}."
                            ),
                            "species": "Aedes aegypti",
                            "url": catmaid_url,
                            "locator": f"{volumes_path.as_posix()}#volume/{volume_id}",
                            "license": "CATMAID public metadata",
                            "volume": volume,
                            "keywords": ["CATMAID", "volume", "EM dataset"],
                        },
                        retrieved_at=retrieved_at,
                    )
                )
    skeletons_path = catmaid_dir / "skeletons.json"
    skeleton_ids: list[int] = []
    if skeletons_path.exists():
        raw_artifacts.append(skeletons_path.as_posix())
        skeletons_payload = json.loads(skeletons_path.read_text(encoding="utf-8"))
        if isinstance(skeletons_payload, list):
            skeleton_ids = [int(skeleton_id) for skeleton_id in skeletons_payload if isinstance(skeleton_id, int)]
    threshold_paths = {
        "1": catmaid_dir / "skeletons_nodecount_gt_1.json",
        "10": catmaid_dir / "skeletons_nodecount_gt_10.json",
        "100": catmaid_dir / "skeletons_nodecount_gt_100.json",
    }
    threshold_sets: dict[str, set[int]] = {}
    for threshold, path in threshold_paths.items():
        if not path.exists():
            continue
        raw_artifacts.append(path.as_posix())
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            threshold_sets[threshold] = {int(skeleton_id) for skeleton_id in payload if isinstance(skeleton_id, int)}
            records.append(
                _record(
                    {
                        "record_id": f"neuro:connectome:catmaid:skeleton-filter:nodecount-gt-{threshold}",
                        "record_type": "catmaid_skeleton_filter",
                        "title": f"CATMAID Aedes skeleton filter nodecount_gt={threshold}",
                        "text": (
                            f"Public CATMAID skeleton filter nodecount_gt={threshold} returns "
                            f"{len(threshold_sets[threshold])} Aedes skeleton ID(s)."
                        ),
                        "species": "Aedes aegypti",
                        "url": f"https://radagast.hms.harvard.edu/catmaidaedes/1/skeletons/?nodecount_gt={threshold}",
                        "locator": path.as_posix(),
                        "license": "CATMAID public metadata",
                        "nodecount_gt": int(threshold),
                        "skeleton_count": len(threshold_sets[threshold]),
                        "sample_skeleton_ids": sorted(threshold_sets[threshold])[:20],
                        "keywords": ["CATMAID", "skeleton IDs", "nodecount filter", "bulk export"],
                    },
                    retrieved_at=retrieved_at,
                )
            )
    if skeleton_ids:
        endpoint_templates = {
            "list": "https://radagast.hms.harvard.edu/catmaidaedes/1/skeletons/",
            "compact_detail": "https://radagast.hms.harvard.edu/catmaidaedes/1/skeletons/{skeleton_id}/compact-detail",
            "cable_length": "https://radagast.hms.harvard.edu/catmaidaedes/1/skeletons/{skeleton_id}/cable-length",
            "connector_links": "https://radagast.hms.harvard.edu/catmaidaedes/1/connectors/links/?skeleton_ids={skeleton_id}",
        }
        records.append(
            _record(
                {
                    "record_id": "neuro:connectome:catmaid:skeleton-manifest",
                    "record_type": "catmaid_skeleton_manifest",
                    "title": "CATMAID Aedes skeleton export manifest",
                    "text": (
                        f"The public Aedes CATMAID API exposes {len(skeleton_ids)} skeleton ID(s) through GET /1/skeletons/. "
                        "Each skeleton has public GET endpoints for compact-detail morphology, cable length, and connector links. "
                        "This closes the CATMAID skeleton-ID export surface, but it is not the future Wellcome whole-brain bulk package."
                    ),
                    "species": "Aedes aegypti",
                    "url": endpoint_templates["list"],
                    "locator": skeletons_path.as_posix(),
                    "license": "CATMAID public metadata",
                    "skeleton_count": len(skeleton_ids),
                    "sample_skeleton_ids": skeleton_ids[:20],
                    "nodecount_gt_counts": {threshold: len(ids) for threshold, ids in threshold_sets.items()},
                    "endpoint_templates": endpoint_templates,
                    "keywords": ["CATMAID", "skeleton manifest", "bulk download", "skeleton IDs", "export"],
                },
                retrieved_at=retrieved_at,
            )
        )
        for skeleton_id in skeleton_ids:
            nodecount_gt = {threshold: skeleton_id in ids for threshold, ids in threshold_sets.items()}
            records.append(
                _record(
                    {
                        "record_id": f"neuro:connectome:catmaid:skeleton:{skeleton_id}",
                        "record_type": "catmaid_skeleton",
                        "title": f"CATMAID Aedes skeleton {skeleton_id}",
                        "text": (
                            f"Public CATMAID skeleton {skeleton_id} is listed in the Aedes EM project. "
                            "Compact-detail morphology, cable length, and connector-link endpoints are available by skeleton ID."
                        ),
                        "species": "Aedes aegypti",
                        "url": endpoint_templates["compact_detail"].format(skeleton_id=skeleton_id),
                        "locator": f"{skeletons_path.as_posix()}#skeleton/{skeleton_id}",
                        "license": "CATMAID public metadata",
                        "skeleton_id": skeleton_id,
                        "compact_detail_url": endpoint_templates["compact_detail"].format(skeleton_id=skeleton_id),
                        "cable_length_url": endpoint_templates["cable_length"].format(skeleton_id=skeleton_id),
                        "connector_links_url": endpoint_templates["connector_links"].format(skeleton_id=skeleton_id),
                        "nodecount_gt": nodecount_gt,
                        "keywords": ["CATMAID", "skeleton", "compact-detail", "connector links"],
                    },
                    retrieved_at=retrieved_at,
                )
            )
    csv_dir = root / "csvs"
    for csv_path in sorted(csv_dir.glob("*.csv")):
        raw_artifacts.append(csv_path.as_posix())
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fields = reader.fieldnames or []
        records.append(
            _record(
                {
                    "record_id": f"neuro:connectome:aedes_public:csv:{csv_path.name}",
                    "record_type": "connectome_csv",
                    "title": f"Aedes public connectome CSV {csv_path.name}",
                    "text": f"Public Aedes connectome-adjacent CSV {csv_path.name} has {len(rows)} row(s) and columns {', '.join(fields)}.",
                    "species": "Aedes aegypti",
                    "url": html_url,
                    "locator": csv_path.as_posix(),
                    "license": "GitHub public repository metadata",
                    "csv_file": csv_path.name,
                    "columns": fields,
                    "row_count": len(rows),
                    "sample_rows": rows[:5],
                },
                retrieved_at=retrieved_at,
            )
        )
    return records, raw_artifacts, gaps


def _connectome_gap(*, retrieved_at: str) -> tuple[EvidenceRecord, dict[str, object]]:
    url = "https://wellcome.org/research-funding/funding-portfolio/funded-grants/whole-brain-connectome-female-aedes-aegypti"
    gap = {
        "source": NEUROBIOLOGY_SOURCE_ID,
        "lane": "neurobiology",
        "reason": "whole_brain_connectome_download_not_public",
        "source_url": url,
        "note": "Wellcome grant metadata says the female Aedes aegypti whole-brain connectome dataset will be made publicly available; no downloadable whole-brain dataset is mapped yet.",
    }
    record = _record(
        {
            "record_id": "neuro:connectome:wellcome:source-gap",
            "record_type": "source_gap",
            "title": "Aedes aegypti connectome source gap",
            "text": (
                "Ask Insects has mapped Wellcome grant metadata for a whole-brain female Aedes aegypti connectome, "
                "but no public downloadable whole-brain connectome dataset is mapped yet. Public partial EM/CATMAID analysis records are indexed separately."
            ),
            "species": "Aedes aegypti",
            "url": url,
            "locator": f"{url}#grant-metadata",
            "license": "public web page metadata",
            "gap": gap,
            "keywords": ["connectome", "whole brain", "source gap", "neuron wiring"],
        },
        retrieved_at=retrieved_at,
    )
    return record, gap


def fetch_neurobiology_records(
    *,
    artifact_dir: Path | None = None,
    retrieved_at: str | None = None,
) -> NeurobiologyBuildResult:
    retrieved_at = retrieved_at or utc_now()
    records = [_record(atom, retrieved_at=retrieved_at) for atom in NEUROBIOLOGY_SOURCE_ATOMS]
    gaps: list[dict[str, object]] = []
    raw_artifacts = [str(atom["url"]) for atom in NEUROBIOLOGY_SOURCE_ATOMS]
    if artifact_dir is not None:
        artifact_dir = Path(artifact_dir)
        for parser in (_geo_records, _sra_records, _zenodo_records, _mosquitobrains_records, _connectome_records):
            parsed_records, parsed_raw_artifacts, parsed_gaps = parser(artifact_dir, retrieved_at=retrieved_at)
            records.extend(parsed_records)
            raw_artifacts.extend(parsed_raw_artifacts)
            gaps.extend(parsed_gaps)
        connectome_record, connectome_gap = _connectome_gap(retrieved_at=retrieved_at)
        records.append(connectome_record)
        gaps.append(connectome_gap)
    return NeurobiologyBuildResult(
        source_id=NEUROBIOLOGY_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=list(dict.fromkeys(raw_artifacts)),
    )
