from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import json
import re
import tarfile
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
            gaps.append(
                {
                    "source": NEUROBIOLOGY_SOURCE_ID,
                    "lane": "neurobiology",
                    "reason": "h5ad_internal_matrix_not_parsed",
                    "path": path.as_posix(),
                    "member": member_name,
                    "note": "The H5AD file is downloaded and indexed as a ZIP member, but its internal AnnData matrix is not atomically parsed yet.",
                }
            )
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
                            "locator": f"{path.as_posix()}#{info.filename}",
                            "license": "public web page metadata",
                            "archive": path.name,
                            "member": info.filename,
                            "file_size": info.file_size,
                            "compressed_size": info.compress_size,
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
        "reason": "connectome_dataset_not_public",
        "source_url": url,
        "note": "Wellcome grant metadata says the female Aedes aegypti connectome dataset will be made publicly available; no downloadable dataset is mapped yet.",
    }
    record = _record(
        {
            "record_id": "neuro:connectome:wellcome:source-gap",
            "record_type": "source_gap",
            "title": "Aedes aegypti connectome source gap",
            "text": (
                "Ask Insects has mapped Wellcome grant metadata for a whole-brain female Aedes aegypti connectome, "
                "but no public downloadable connectome dataset is mapped yet. Treat complete connectome questions as a source gap."
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
        for parser in (_geo_records, _zenodo_records, _mosquitobrains_records):
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
