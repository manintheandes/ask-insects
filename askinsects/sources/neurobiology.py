from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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


def _record(atom: dict[str, object], *, retrieved_at: str) -> EvidenceRecord:
    text = str(atom["text"])
    keywords = atom.get("keywords")
    if isinstance(keywords, list):
        text = f"{text} Keywords: {', '.join(str(keyword) for keyword in keywords)}."
    return EvidenceRecord(
        record_id=str(atom["record_id"]),
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


def fetch_neurobiology_records(*, retrieved_at: str | None = None) -> NeurobiologyBuildResult:
    retrieved_at = retrieved_at or utc_now()
    records = [_record(atom, retrieved_at=retrieved_at) for atom in NEUROBIOLOGY_SOURCE_ATOMS]
    return NeurobiologyBuildResult(
        source_id=NEUROBIOLOGY_SOURCE_ID,
        records=records,
        gaps=[],
        raw_artifacts=[str(atom["url"]) for atom in NEUROBIOLOGY_SOURCE_ATOMS],
    )
