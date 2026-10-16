import unittest

from scripts.overture_taxonomy import classify


class OvertureTaxonomyTests(unittest.TestCase):
    def test_bco_amendment_and_process_are_separate_facets(self):
        result = classify("Amend BCO 8-5 concerning the ordination of men", "GA approved; sent to presbyteries")
        self.assertEqual(result["type"], "Amendment")
        self.assertEqual(result["instrument"], "BCO")
        self.assertEqual(result["bco_stage"], "Presbytery review recorded")

    def test_struck_bco_amendment_has_no_presbytery_ratification_stage(self):
        result = classify(
            "Amend BCO 13-6 and 21-4",
            "Encouraged Presbyteries and Sessions to Adopt Policies; BCO amendments not sent down",
        )
        self.assertEqual(result["bco_stage"], "Not sent down for ratification")

    def test_adopted_report_amended_is_not_an_amendment_type(self):
        result = classify("Appoint a committee to study ministerial training", "Committee report adopted as amended")
        self.assertEqual(result["type"], "Study or committee request")
        self.assertEqual(result["bco_stage"], "—")

    def test_boundary_request_is_distinct_from_direct_action(self):
        result = classify("Revise presbytery boundaries")
        self.assertEqual(result["type"], "Presbytery structure or boundary")

    def test_proposed_instrument_text_change_is_an_amendment(self):
        result = classify("Provide in the BCO for optional rotation of ruling elders")
        self.assertEqual(result["type"], "Amendment")
        self.assertEqual(result["instrument"], "BCO")

    def test_committee_request_to_prepare_bco_material_is_not_an_amendment(self):
        result = classify("Appoint a committee to add Scripture proof texts to the BCO")
        self.assertEqual(result["type"], "Study or committee request")

    def test_primary_amendment_target_wins_when_another_instrument_is_cited(self):
        result = classify("Amend RAO 16-6 to eliminate conflict with BCO 40-5")
        self.assertEqual(result["type"], "Amendment")
        self.assertEqual(result["instrument"], "RAO")


if __name__ == "__main__":
    unittest.main()
