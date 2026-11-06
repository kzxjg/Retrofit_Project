"""Tests for what the tool actually recommends (logic.py) and which modelled house
it compares the home to (baseline.py), including the exact score boundaries."""

from django.test import SimpleTestCase

from .baseline import ARCHETYPES, WEIGHTS, match_baseline
from .formspec import YEAR_OPTIONS
from .logic import envelope_score, recommend_package

PRE_1941, GEN_1, GEN_2, GEN_3, GEN_4, GEN_5 = YEAR_OPTIONS

NO_UPGRADE = "No Upgrade Recommended"
ELECTRIFY = "Equipment Electrification"
BASIC = "Basic Envelope + Equipment Electrification"
CURRENT_CODE = "Current Code Envelope + Equipment Electrification"
BEYOND_CODE = "Beyond Code Envelope + Equipment Electrification"


def home(**answers):
    """A home that scores 0: new, triple glazed, insulation known, no drafts, gas heated."""
    base = {
        "year_of_construction": GEN_5, "window_type": "Triple glazing",
        "insulation_type": "Fibreglass", "door_drafts": "No",
        "heating_fuel": "Natural gas", "cooling_system": "Central air conditioner",
    }
    return {**base, **answers}


ALL_ELECTRIC = {"heating_fuel": "Electricity", "cooling_system": "Heat pump"}


class EnvelopeScoreTests(SimpleTestCase):
    def test_points_for_each_age_of_house(self):
        for year, points in zip(YEAR_OPTIONS, [3, 2, 1, 0, 0, 0]):
            with self.subTest(year=year):
                self.assertEqual(envelope_score(home(year_of_construction=year)), points)

    def test_points_for_each_window_type(self):
        for window, points in {"Single glazing": 2, "Double glazing": 1, "Triple glazing": 0, "Unknown": 1}.items():
            with self.subTest(window=window):
                self.assertEqual(envelope_score(home(window_type=window)), points)

    def test_unknown_insulation_and_drafty_doors_add_a_point_each(self):
        self.assertEqual(envelope_score(home(insulation_type="Unknown")), 1)
        self.assertEqual(envelope_score(home(door_drafts="Yes")), 1)
        self.assertEqual(envelope_score(home(door_drafts="Unknown")), 0)

    def test_a_question_left_unanswered(self):
        # insulation is optional; leaving it out counts the same as answering "Unknown"
        no_insulation = home()
        del no_insulation["insulation_type"]
        self.assertEqual(envelope_score(no_insulation), 1)
        # an age or window type the table does not know counts as the middle value, 1
        self.assertEqual(envelope_score(home(year_of_construction=None)), 1)
        self.assertEqual(envelope_score(home(window_type=None)), 1)

    def test_lowest_and_highest_possible_scores(self):
        self.assertEqual(envelope_score(home()), 0)
        worst = home(year_of_construction=PRE_1941, window_type="Single glazing",
                     insulation_type="Unknown", door_drafts="Yes")
        self.assertEqual(envelope_score(worst), 7)


class RecommendPackageTests(SimpleTestCase):
    # one home for every score from 0 to 7, so each boundary is tried from both sides
    HOME_FOR_SCORE = {
        0: home(),
        1: home(window_type="Double glazing"),
        2: home(window_type="Single glazing"),
        3: home(year_of_construction=GEN_2, window_type="Single glazing"),
        4: home(year_of_construction=GEN_1, window_type="Single glazing"),
        5: home(year_of_construction=PRE_1941, window_type="Single glazing"),
        6: home(year_of_construction=PRE_1941, window_type="Single glazing", door_drafts="Yes"),
        7: home(year_of_construction=PRE_1941, window_type="Single glazing", door_drafts="Yes",
                insulation_type="Unknown"),
    }

    def test_the_homes_used_here_have_the_scores_they_claim(self):
        for score, answers in self.HOME_FOR_SCORE.items():
            self.assertEqual(envelope_score(answers), score)

    def test_package_at_every_score(self):
        expected = {0: ELECTRIFY, 1: ELECTRIFY, 2: BASIC, 3: BASIC,
                    4: CURRENT_CODE, 5: CURRENT_CODE, 6: BEYOND_CODE, 7: BEYOND_CODE}
        for score, package in expected.items():
            with self.subTest(score=score):
                self.assertEqual(recommend_package(self.HOME_FOR_SCORE[score]), package)

    def test_an_efficient_all_electric_home_needs_no_upgrade(self):
        for score in (0, 1):
            for cooling in ("Heat pump", "Ductless mini-split", "None"):
                with self.subTest(score=score, cooling=cooling):
                    answers = {**self.HOME_FOR_SCORE[score], "heating_fuel": "Electricity", "cooling_system": cooling}
                    self.assertEqual(recommend_package(answers), NO_UPGRADE)

    def test_all_electric_only_matters_for_an_efficient_envelope(self):
        # from score 2 up the envelope decides, whatever the equipment
        for score in range(2, 8):
            with self.subTest(score=score):
                self.assertEqual(
                    recommend_package({**self.HOME_FOR_SCORE[score], **ALL_ELECTRIC}),
                    recommend_package(self.HOME_FOR_SCORE[score]),
                )

    def test_electric_heat_with_other_cooling_is_not_all_electric(self):
        for cooling in ("Central air conditioner", "Window air conditioner", "Portable air conditioner",
                        "Other", "Unknown", None):
            with self.subTest(cooling=cooling):
                answers = home(heating_fuel="Electricity", cooling_system=cooling)
                self.assertEqual(recommend_package(answers), ELECTRIFY)

    def test_heat_pump_cooling_with_non_electric_heat_is_not_all_electric(self):
        self.assertEqual(recommend_package(home(heating_fuel="Natural gas", cooling_system="Heat pump")), ELECTRIFY)
        self.assertEqual(recommend_package(home(heating_fuel="Unknown", cooling_system="Heat pump")), ELECTRIFY)

    def test_every_package_is_one_of_the_five_known_ones(self):
        known = {NO_UPGRADE, ELECTRIFY, BASIC, CURRENT_CODE, BEYOND_CODE}
        for answers in self.HOME_FOR_SCORE.values():
            for equipment in ({}, ALL_ELECTRIC):
                self.assertIn(recommend_package({**answers, **equipment}), known)


class MatchBaselineTests(SimpleTestCase):
    """These follow WEIGHTS and ARCHETYPES, whatever they hold, so they keep
    working when the placeholder weights are replaced with real ones."""

    def test_an_exact_copy_of_an_archetype_matches_it_fully(self):
        for archetype in ARCHETYPES:
            with self.subTest(archetype=archetype["id"]):
                match = match_baseline(dict(archetype["profile"]))
                self.assertEqual(match.archetype_id, archetype["id"])
                self.assertEqual(match.idf_file, archetype["idf_file"])
                self.assertEqual(match.confidence, 1.0)
                self.assertEqual(match.mismatched, [])

    def test_unanswered_questions_count_as_half_a_match(self):
        match = match_baseline({})
        self.assertEqual(match.confidence, 0.5)
        self.assertEqual(match.mismatched, [])

    def test_unknown_counts_as_half_unless_the_archetype_also_says_unknown(self):
        # Current rule: an "Unknown" answer fully matches an archetype whose own profile
        # says "Unknown", so such archetypes win ties among people who answered "Unknown".
        total = sum(WEIGHTS.values())
        unknown = {field: "Unknown" for field in WEIGHTS}
        best = max(
            sum(w if a["profile"][f] == "Unknown" else w / 2 for f, w in WEIGHTS.items())
            for a in ARCHETYPES
        )
        match = match_baseline(unknown)
        self.assertEqual(match.confidence, round(best / total, 2))
        self.assertEqual(match.mismatched, [])

    def test_a_tie_goes_to_the_first_archetype_in_the_list(self):
        self.assertEqual(match_baseline({}).archetype_id, ARCHETYPES[0]["id"])

    def test_a_wrong_answer_is_listed_and_lowers_the_confidence(self):
        archetype = ARCHETYPES[0]
        field = max(WEIGHTS, key=WEIGHTS.get)
        answers = {**archetype["profile"], field: "Something else"}
        match = match_baseline(answers)
        if match.archetype_id == archetype["id"]:
            self.assertEqual(match.mismatched, [field])
            self.assertAlmostEqual(match.confidence, round(1 - WEIGHTS[field] / sum(WEIGHTS.values()), 2))
        else:
            self.assertLess(match.confidence, 1.0)

    def test_confidence_is_always_between_0_and_1(self):
        profiles = [a["profile"] for a in ARCHETYPES]
        mixes = [{}, {f: "nonsense" for f in WEIGHTS}]
        mixes += [{**p, **{f: "nonsense" for f in list(WEIGHTS)[: i]}} for i, p in enumerate(profiles)]
        for answers in mixes:
            match = match_baseline(answers)
            self.assertGreaterEqual(match.confidence, 0.0)
            self.assertLessEqual(match.confidence, 1.0)
            self.assertTrue(set(match.mismatched) <= set(WEIGHTS))

    def test_answers_matching_nothing_still_pick_an_archetype(self):
        match = match_baseline({f: "nonsense" for f in WEIGHTS})
        self.assertEqual(match.confidence, 0.0)
        self.assertEqual(sorted(match.mismatched), sorted(WEIGHTS))
        self.assertIn(match.archetype_id, [a["id"] for a in ARCHETYPES])

    def test_every_archetype_describes_every_weighted_question(self):
        for archetype in ARCHETYPES:
            self.assertEqual(set(archetype["profile"]), set(WEIGHTS), archetype["id"])
