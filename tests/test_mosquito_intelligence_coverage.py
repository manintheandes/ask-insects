import unittest

from scripts.verify_mosquito_intelligence_coverage import (
    REQUIRED_DOMAINS,
    REQUIRED_GATES,
    load_coverage,
    verify_coverage,
)


class MosquitoIntelligenceCoverageTests(unittest.TestCase):
    def test_coverage_ledger_declares_world_aedes_scope(self):
        payload = load_coverage()

        self.assertEqual(payload["scope"]["primary_taxon"], "Aedes aegypti")
        self.assertIn("most comprehensive Aedes aegypti intelligence system in the world", payload["scope"]["strategy"])

    def test_coverage_ledger_has_all_required_domains_and_gates(self):
        payload = load_coverage()
        verify_coverage(payload)

        domains = {domain["id"]: domain for domain in payload["domains"]}
        self.assertEqual(set(domains), REQUIRED_DOMAINS)
        self.assertEqual(set(payload["source_contract_gates"]), REQUIRED_GATES)
        for domain in domains.values():
            self.assertEqual(set(domain["current_gates"]), REQUIRED_GATES)

    def test_unbuilt_domains_carry_next_sources_and_completion_evidence(self):
        payload = load_coverage()
        domains = {domain["id"]: domain for domain in payload["domains"]}

        for domain_id in ("behavior", "video", "vector_competence", "resistance", "ecology", "public_health"):
            domain = domains[domain_id]
            self.assertTrue(domain["required_next_sources"], domain_id)
            self.assertTrue(domain["completion_evidence"], domain_id)

    def test_literature_facet_backed_domains_are_not_marked_unmapped(self):
        payload = load_coverage()
        domains = {domain["id"]: domain for domain in payload["domains"]}

        for domain_id in ("behavior", "vector_competence", "resistance", "ecology", "public_health"):
            domain = domains[domain_id]
            self.assertEqual(domain["status"], "partial_source_grade")
            self.assertIn("aedes_literature_facets", domain["current_sources"])
            self.assertEqual(domain["current_gates"]["mapped"], "yes")
            self.assertEqual(domain["current_gates"]["accessible"], "yes")
            self.assertEqual(domain["current_gates"]["ask_surface_wired"], "yes")


if __name__ == "__main__":
    unittest.main()
