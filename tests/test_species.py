import unittest
from askinsects.species import resolve_species


class ResolveSpeciesTests(unittest.TestCase):
    def test_returns_cleaned_row_value_when_present(self):
        self.assertEqual(resolve_species("  Aedes aegypti "), "Aedes aegypti")

    def test_returns_none_when_absent_and_no_scope(self):
        self.assertIsNone(resolve_species(""))
        self.assertIsNone(resolve_species(None))

    def test_returns_scope_only_when_absent_and_scope_given(self):
        self.assertEqual(resolve_species(None, scope="Aedes aegypti"), "Aedes aegypti")

    def test_row_value_wins_over_scope(self):
        self.assertEqual(resolve_species("Aedes albopictus", scope="Aedes aegypti"), "Aedes albopictus")

    def test_non_str_value_treated_as_absent(self):
        self.assertIsNone(resolve_species(123))

    def test_whitespace_only_scope_does_not_leak(self):
        self.assertIsNone(resolve_species(None, scope="   "))


if __name__ == "__main__":
    unittest.main()
