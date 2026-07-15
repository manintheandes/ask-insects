import unittest

from askinsects.planner import plan_question


class PlannerRoutingTests(unittest.TestCase):
    def test_domain_question_with_study_is_not_shadowed_to_literature(self):
        # "study"/"research" must not steal questions that belong to a domain lane.
        self.assertEqual(plan_question("study of kdr resistance in Aedes aegypti").answer_shape, "resistance")
        self.assertNotEqual(
            plan_question("studies of Drosophila suzukii crop damage in cherry").answer_shape, "literature"
        )

    def test_pure_literature_question_still_routes_to_literature(self):
        self.assertEqual(plan_question("what papers since 2020 discuss Wolbachia in Aedes aegypti").answer_shape, "literature")
        self.assertEqual(plan_question("show me studies about Aedes aegypti microbiota").answer_shape, "literature")

    def test_table_label_does_not_trigger_resistance(self):
        # "S12A" matches the mutation regex but is a table label here, not a mutation.
        self.assertNotEqual(plan_question("what does supplementary Table S12A show").answer_shape, "resistance")

    def test_real_mutation_code_still_triggers_resistance(self):
        self.assertEqual(plan_question("kdr V1016G mutation frequency in Aedes aegypti").answer_shape, "resistance")

    def test_swd_substring_not_matched_inside_words(self):
        self.assertNotEqual(plan_question("passwd reset for the trap logger").answer_shape, "management")

    def test_geo_substring_not_matched_inside_geographic(self):
        plan = plan_question("geographic range of Aedes aegypti")
        self.assertEqual(plan.answer_shape, "ecology")
        self.assertIn("observations", plan.lanes)

    def test_real_geo_question_still_expression(self):
        self.assertEqual(plan_question("show GEO RNA-seq expression for Aedes aegypti").answer_shape, "expression")

    def test_broad_swd_repellency_wording_routes_to_behavior(self):
        questions = (
            "What public evidence does Ask Insects have for non-contact repellency in spotted wing drosophila?",
            "What spatial repellency evidence exists for Drosophila suzukii?",
            "Is there odor-mediated avoidance evidence for SWD?",
            "What oviposition deterrence evidence exists for spotted wing drosophila?",
        )
        for question in questions:
            with self.subTest(question=question):
                plan = plan_question(question)
                self.assertEqual(plan.answer_shape, "behavior")
                self.assertEqual(plan.lanes[0], "behavior")


if __name__ == "__main__":
    unittest.main()
