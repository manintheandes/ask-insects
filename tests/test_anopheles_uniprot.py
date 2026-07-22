import copy
import json
import tempfile
import unittest
from pathlib import Path

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.anopheles_uniprot import (
    ANOPHELES_UNIPROT_SOURCE_ID,
    fetch_anopheles_uniprot_records,
)
from scripts.ingest_anopheles_uniprot import ingest_anopheles_uniprot
from tests.test_uniprot_proteins_source import PROTEOME_PAYLOAD, UNIPROTKB_PAYLOAD


def _anopheles_payloads() -> tuple[dict[str, object], dict[str, object]]:
    proteins = copy.deepcopy(UNIPROTKB_PAYLOAD)
    protein = proteins["results"][0]
    protein["primaryAccession"] = "A0A1S4G9D3"
    protein["uniProtkbId"] = "ORCO_ANOGA"
    protein["proteinDescription"]["recommendedName"]["fullName"]["value"] = "Odorant receptor coreceptor"
    protein["genes"] = [{"geneName": {"value": "Orco"}}]
    protein["organism"] = {"scientificName": "Anopheles gambiae", "taxonId": 7165}
    protein["comments"] = [{"commentType": "FUNCTION", "texts": [{"value": "Coreceptor for odorant receptor signaling."}]}]
    protein["uniProtKBCrossReferences"] = [
        {"database": "VectorBase", "id": "AGAP002560"},
        {"database": "GO", "id": "GO:0004984"},
    ]

    proteomes = copy.deepcopy(PROTEOME_PAYLOAD)
    proteome = proteomes["results"][0]
    proteome["id"] = "UP000007062"
    proteome["description"] = "Anopheles gambiae reference proteome"
    proteome["taxonomy"] = {"taxonId": 7165, "scientificName": "Anopheles gambiae"}
    return proteins, proteomes


def _fake_fetch(url: str) -> dict[str, object]:
    proteins, proteomes = _anopheles_payloads()
    if "/uniprotkb/search" in url:
        return proteins
    if "/proteomes/search" in url:
        return proteomes
    raise AssertionError(url)


def _aedes_protein() -> EvidenceRecord:
    return EvidenceRecord(
        record_id="uniprot:protein:AEDES1",
        lane="proteins",
        source="aedes_uniprot_proteins",
        title="Aedes protein",
        text="Aedes aegypti odorant receptor protein.",
        species="Aedes aegypti",
        url="https://www.uniprot.org/uniprotkb/AEDES1/entry",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_uniprot_proteins",
            locator="raw/uniprot/aedes.json#results/1",
            retrieved_at="2026-01-01T00:00:00Z",
            license="UniProt CC BY 4.0",
        ),
    )


class AnophelesUniProtTests(unittest.TestCase):
    def test_fetch_uses_verified_taxonomy_and_distinct_source_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_anopheles_uniprot_records(
                raw_dir=Path(tmpdir) / "raw",
                target_taxa=(("Anopheles gambiae", 7165),),
                protein_limit_per_taxon=5,
                proteome_limit_per_taxon=5,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )

        self.assertEqual(result.source_id, ANOPHELES_UNIPROT_SOURCE_ID)
        self.assertEqual(result.target_taxa, (("Anopheles gambiae", 7165),))
        self.assertEqual(result.gaps, [])
        record_ids = {record.record_id for record in result.records}
        self.assertEqual(
            record_ids,
            {"anopheles_uniprot:protein:A0A1S4G9D3", "anopheles_uniprot:proteome:UP000007062"},
        )
        protein = next(record for record in result.records if ":protein:" in record.record_id)
        self.assertEqual(protein.source, ANOPHELES_UNIPROT_SOURCE_ID)
        self.assertEqual(protein.species, "Anopheles gambiae")
        self.assertEqual(protein.payload["query_taxonomy_id"], 7165)
        self.assertIn("AGAP002560", protein.text)

    def test_ingest_preserves_aedes_and_writes_taxon_receipt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records([_aedes_protein()])

            result = ingest_anopheles_uniprot(
                artifact_dir=artifact_dir,
                target_taxa=(("Anopheles gambiae", 7165),),
                protein_limit_per_taxon=5,
                proteome_limit_per_taxon=5,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, count(*) as n from records where lane='proteins' group by source order by source",
                limit=10,
            )
            counts = {row["source"]: row["n"] for row in rows}
            self.assertEqual(counts["aedes_uniprot_proteins"], 1)
            self.assertEqual(counts[ANOPHELES_UNIPROT_SOURCE_ID], 2)
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            target = receipt[ANOPHELES_UNIPROT_SOURCE_ID]["target_taxa"][0]
            self.assertEqual(target, {"species": "Anopheles gambiae", "ncbi_taxonomy_id": 7165})

    def test_anopheles_protein_question_excludes_aedes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            fetched = fetch_anopheles_uniprot_records(
                raw_dir=artifact_dir / "raw" / "anopheles_uniprot",
                target_taxa=(("Anopheles gambiae", 7165),),
                protein_limit_per_taxon=5,
                proteome_limit_per_taxon=5,
                fetch_json=_fake_fetch,
                retrieved_at="2026-07-22T00:00:00Z",
            )
            index.upsert_records([_aedes_protein(), *fetched.records])

            answer = answer_question("show Anopheles gambiae UniProt proteins", artifact_dir=artifact_dir)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "genomics")
            self.assertEqual(answer["evidence"][0]["source"], ANOPHELES_UNIPROT_SOURCE_ID)
            self.assertTrue(all(item["species"] == "Anopheles gambiae" for item in answer["evidence"]))

            mechanism_answer = answer_question("What does Orco do in Anopheles gambiae?", artifact_dir=artifact_dir)
            self.assertTrue(mechanism_answer["ok"])
            self.assertEqual(mechanism_answer["evidence"][0]["record_id"], "anopheles_uniprot:protein:A0A1S4G9D3")


if __name__ == "__main__":
    unittest.main()
