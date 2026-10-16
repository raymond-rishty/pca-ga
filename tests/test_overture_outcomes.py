import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("overture_catalogue_linker", SCRIPTS / "42_link_overture_catalogue.py")
LINKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LINKER)


def event(phase, outcome, action_text="", actor="Overtures Committee"):
    return {"phase": phase, "outcome": outcome, "action_text": action_text, "actor": actor}


class OvertureOutcomeTests(unittest.TestCase):
    def test_adopted_negative_recommendation_is_reported_as_the_answer(self):
        bundle = {"events": [
            event("committee recommendation", "Recommended answering the overture in the negative."),
            event("Assembly adoption", "The Assembly adopted this recommendation in gross."),
        ]}
        self.assertEqual(LINKER.concise_outcome(bundle, "Adopted (final)"), "Answered in the negative")

    def test_reference_answer_is_kept_short_and_specific(self):
        bundle = {"events": [
            event("committee recommendation", "Recommendation to answer by reference to Overture 29."),
            event("Assembly decision", "The Assembly adopted the recommendation in gross."),
        ]}
        self.assertEqual(LINKER.concise_outcome(bundle, "The Assembly adopted this recommendation in gross."),
                         "Answered by reference to Overture 29")

    def test_generic_reference_label_is_enriched_when_trail_names_the_reference(self):
        bundle = {"events": [event("committee recommendation", "Answered by reference to Overture 19.")]}
        self.assertEqual(LINKER.concise_outcome(bundle, "Answered by reference"),
                         "Answered by reference to Overture 19")

    def test_generic_reference_label_is_preserved_if_inference_is_not_a_reference(self):
        bundle = {"events": [event("Assembly decision", "Answered in the affirmative.")]}
        self.assertEqual(LINKER.concise_outcome(bundle, "Answered by reference"),
                         "Answered by reference")

    def test_generic_referral_is_more_specific_when_the_trail_names_study(self):
        bundle = {"events": [event("Assembly decision", "Referred the overture to the committee for further study.")]}
        self.assertEqual(LINKER.concise_outcome(bundle, "Referred"), "Referred for study")

    def test_commissioners_recommendation_wins_over_permanent_committee_proposal(self):
        bundle = {"events": [
            event("committee recommendation", "Permanent Committee recommended approval if the way was clear.",
                  "Approve the boundary change if the way is clear.", "MNA Permanent Committee"),
            event("committee recommendation", "The Committee recommended joint referral for consideration and possible presbytery action.",
                  "Refer the boundary proposal to the Inter-Presbytery Committee for consideration and possible subsequent action by the Presbyteries.",
                  "Committee of Commissioners on Mission to North America"),
            event("Assembly adoption", "The Assembly adopted the Committee of Commissioners' recommendation."),
        ]}
        self.assertEqual(LINKER.concise_outcome(bundle, "The Assembly adopted the Committee of Commissioners’ recommendation."),
                         "Referred for study")

    def test_referral_back_is_summarized_without_omnibus_procedure(self):
        bundle = {"events": [
            event("committee recommendation", "Recommendation to refer the overture back to Presbytery without prejudice."),
            event("Assembly adoption", "The recommendation was adopted in gross."),
        ]}
        self.assertEqual(LINKER.concise_outcome(bundle, "Overtures Committee recommendation 28 adopted in gross"),
                         "Referred back to Presbytery")

    def test_amended_report_without_a_clear_final_answer_is_preserved(self):
        self.assertEqual(LINKER.concise_outcome({}, "committee report adopted as amended"),
                         "committee report adopted as amended")

    def test_later_assembly_answer_wins_over_deferral_text_and_earlier_answer(self):
        bundle = {"vol": "ga47_2019", "events": [
            {**event("Assembly decision", "Answered in the negative by voice vote."),
             "source_volume": "ga47_2019"},
            {**event("Assembly deferral", "Did not act on the negative recommendation while awaiting committee action."),
             "source_volume": "ga47_2019"},
            {**event("Assembly decision", "Answered in the affirmative as amended, following the earlier negative answer."),
             "source_volume": "ga47_2019"},
        ]}
        self.assertEqual(LINKER.concise_outcome(bundle, "Adopted (final)"),
                         "Answered in the affirmative as amended")

    def test_later_assembly_can_reverse_an_earlier_ga_recommendation(self):
        bundle = {"vol": "ga07_1979", "events": [
            {**event("committee recommendation", "Recommended an affirmative answer."),
             "source_volume": "ga07_1979"},
            {**event("Assembly decision", "The affirmative recommendation did not take effect."),
             "source_volume": "ga07_1979"},
            {**event("committee recommendation", "Recommended a negative answer to the carried-over proposal."),
             "source_volume": "ga08_1980"},
            {**event("Assembly decision", "Adopted the negative answer to GA7 Overture 6."),
             "source_volume": "ga08_1980"},
        ]}
        self.assertEqual(LINKER.concise_outcome(bundle, "Adopted (final)"),
                         "Answered in the negative")

    def test_failed_presbytery_concurrence_overrides_initial_adoption(self):
        bundle = {"vol": "ga28_2000", "events": [
            event("Assembly approval", "The Assembly adopted the substitute amendment and sent it to the Presbyteries for concurrence."),
            event("later Assembly confirmation", "The required two-thirds presbytery concurrence was not received; the amendment was defeated."),
        ]}
        self.assertEqual(LINKER.concise_outcome(bundle, "Adopted (final)"), "Not ratified")

    def test_routing_a_recommendation_does_not_hide_its_answer(self):
        bundle = {"events": [
            event("committee recommendation", "affirmative recommendation pending companion; report says referred to Overtures Committee",
                  "The overture be answered in the affirmative pending the companion overture. 62-0-0 referred to the Overtures Committee.",
                  "Committee of Commissioners on MNA"),
            event("Assembly decision", "listed among recommendations adopted in gross without objection"),
        ]}
        self.assertEqual(LINKER.concise_outcome(bundle, "Adopted (final)"),
                         "Answered in the affirmative")

    def test_reference_to_another_year_keeps_the_overture_identifier_intact(self):
        bundle = {"events": [event("committee recommendation", "Answer by reference to the answer to Overture 2021-20.")]}
        self.assertEqual(LINKER.concise_outcome(bundle, "The Assembly adopted this recommendation in gross."),
                         "Answered by reference to Overture 2021-20")

    def test_defeated_subsidiary_motion_is_not_the_overture_outcome(self):
        bundle = {"events": [event("Assembly decision", "Defeated a motion to add a supporting reference.")]}
        self.assertEqual(LINKER._recommendation_outcome(bundle), "")

    def test_long_unresolved_outcome_is_shortened_without_claiming_approval(self):
        current = "GA2 approved tentative presbytery boundaries, then reconsidered the report; the minutes do not establish the final disposition."
        self.assertEqual(LINKER.concise_outcome({}, current), "Final disposition unclear")

    def test_long_ratification_history_keeps_the_final_bco_stage(self):
        current = "Answered affirmatively at GA8; after two-thirds Presbytery approval, enacted at GA9 as BCO 14-1-11."
        self.assertEqual(LINKER.concise_outcome({}, current), "Approved and enacted")


if __name__ == "__main__":
    unittest.main()
