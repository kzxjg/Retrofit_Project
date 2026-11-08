"""Tests for the report the tool produces (logic.py) and which modelled house it compares the home
to (baseline.py): weights, package ranking, budget flags and archetype matching."""

from django.test import SimpleTestCase

from .baseline import ARCHETYPES, WEIGHTS, match_baseline
from .formspec import (
    ADVANCED_MODE, BUILDING_FORMS, CRITERIA_IDS, NOT_SURE, PRIORITY_OPTIONS, SECONDARY_OPTIONS,
    SIMPLE_MODE, YEAR_OPTIONS,
)
from .logic import (
    PACKAGES, PRIORITY_WEIGHTS, REFERENCE_AREA_M2, SECONDARY_CRITERION, SECONDARY_SHARE, build_report,
    criterion_weights, score,
)

PRE_1941, GEN_1, GEN_2, GEN_3, GEN_4, GEN_5 = YEAR_OPTIONS


def answers(**changes):
    """Validated answers, as formspec.validate() hands them on."""
    base = {
        "postal_code": "N9A 1A1", "year_built": 1985, "year_of_construction": GEN_1,
        "floor_area": REFERENCE_AREA_M2, "building_form": "Detached house",
        "zone": "Zone 5", "zone_id": "zone5", "budget": 30000,
        "preference_mode": SIMPLE_MODE, "priority": "Balanced outcome",
    }
    return {**base, **changes}


def advanced(**weights):
    w = {c: 0 for c in CRITERIA_IDS}
    w.update(weights)
    return answers(preference_mode=ADVANCED_MODE, weights=w)


class CriterionWeightTests(SimpleTestCase):
    def test_weights_always_add_up_to_one(self):
        cases = [answers(priority=p) for p in PRIORITY_OPTIONS]
        cases += [answers(priority=p, secondary_priority=s) for p in PRIORITY_OPTIONS for s in SECONDARY_OPTIONS]
        cases += [advanced(payback=1), advanced(**{c: 100 for c in CRITERIA_IDS})]
        for a in cases:
            with self.subTest(a=(a.get("priority"), a.get("secondary_priority"), a.get("weights"))):
                w = criterion_weights(a)
                self.assertEqual(list(w), CRITERIA_IDS)
                self.assertAlmostEqual(sum(w.values()), 1)
                self.assertTrue(all(v >= 0 for v in w.values()))

    def test_each_simple_priority_leans_on_its_own_criterion(self):
        leans = {
            "Lowest upfront cost": "initial_cost", "Maximum energy savings": "energy_savings",
            "Lowest carbon emissions": "operational_carbon", "Shortest payback period": "payback",
            "Future climate resilience": "resilience",
        }
        for priority, criterion in leans.items():
            with self.subTest(priority=priority):
                w = criterion_weights(answers(priority=priority))
                self.assertEqual(max(w, key=w.get), criterion)

    def test_a_second_priority_adds_weight_to_its_criterion(self):
        plain = criterion_weights(answers())
        leaned = criterion_weights(answers(secondary_priority="Long-term performance"))
        self.assertGreater(leaned["resilience"], plain["resilience"])
        self.assertLess(leaned["initial_cost"], plain["initial_cost"])

    # Written out by hand, not read from logic.py: SECONDARY_CRITERION pairs the options with
    # criteria by list position, so reordering either list would swap them without this.
    SECONDARY_LEANS = {
        "Long-term performance": "resilience",
        "Energy savings": "energy_savings",
        "Lower carbon emissions": "operational_carbon",
        "Lower lifecycle cost": "payback",
        "Short payback": "payback",
    }

    def test_every_second_priority_leans_on_its_own_criterion_by_its_share(self):
        self.assertEqual(set(self.SECONDARY_LEANS), set(SECONDARY_OPTIONS))
        for priority in PRIORITY_OPTIONS:
            plain = criterion_weights(answers(priority=priority))
            for secondary, criterion in self.SECONDARY_LEANS.items():
                with self.subTest(priority=priority, secondary=secondary):
                    leaned = criterion_weights(answers(priority=priority, secondary_priority=secondary))
                    for c in CRITERIA_IDS:
                        expected = plain[c] * (1 - SECONDARY_SHARE) + (SECONDARY_SHARE if c == criterion else 0)
                        self.assertAlmostEqual(leaned[c], expected)

    def test_every_option_has_its_weights_and_none_are_left_over(self):
        # zip() would silently drop an option added without a matching entry.
        self.assertEqual(list(PRIORITY_WEIGHTS), PRIORITY_OPTIONS)
        self.assertTrue(all(len(w) == len(CRITERIA_IDS) for w in PRIORITY_WEIGHTS.values()))
        self.assertEqual(list(SECONDARY_CRITERION), SECONDARY_OPTIONS)
        self.assertTrue(set(SECONDARY_CRITERION.values()) <= set(CRITERIA_IDS))

    def test_no_second_priority_changes_nothing(self):
        for priority in PRIORITY_OPTIONS:
            with self.subTest(priority=priority):
                self.assertEqual(
                    criterion_weights(answers(priority=priority, secondary_priority=None)),
                    criterion_weights(answers(priority=priority)),
                )

    def test_advanced_weights_are_normalised(self):
        w = criterion_weights(advanced(payback=30, resilience=10))
        self.assertAlmostEqual(w["payback"], 0.75)
        self.assertAlmostEqual(w["resilience"], 0.25)
        self.assertEqual(w["initial_cost"], 0)

    def test_advanced_mode_ignores_a_leftover_simple_priority(self):
        a = advanced(payback=1)
        a["priority"] = "Lowest upfront cost"
        self.assertAlmostEqual(criterion_weights(a)["payback"], 1)


class RankingTests(SimpleTestCase):
    def ids(self, report):
        return [p["id"] for p in report["packages"]]

    def test_packages_are_sorted_best_score_first(self):
        report = build_report(answers())
        scores = [p["score"] for p in report["packages"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(sorted(self.ids(report)), sorted(p["id"] for p in PACKAGES))

    def test_caring_only_about_cost_puts_the_cheapest_package_first(self):
        cheapest = min(PACKAGES, key=lambda p: p["cost"])["id"]
        self.assertEqual(self.ids(build_report(advanced(initial_cost=100)))[0], cheapest)

    def test_caring_only_about_savings_puts_the_biggest_saver_first(self):
        best = max(PACKAGES, key=lambda p: p["saving_pct"])["id"]
        self.assertEqual(self.ids(build_report(advanced(energy_savings=100)))[0], best)

    def test_caring_only_about_payback_puts_the_quickest_payback_first(self):
        best = min(PACKAGES, key=lambda p: p["payback_yrs"])["id"]
        self.assertEqual(self.ids(build_report(advanced(payback=100)))[0], best)

    def test_a_score_is_the_weighted_criterion_values(self):
        only_resilience = {c: (1 if c == "resilience" else 0) for c in CRITERIA_IDS}
        for p in PACKAGES:
            self.assertAlmostEqual(score(p, only_resilience), p["resilience"] / 100)


class ReportTests(SimpleTestCase):
    def test_costs_scale_with_floor_area(self):
        small = build_report(answers(floor_area=REFERENCE_AREA_M2 / 2))
        full = build_report(answers())
        by_id = lambda r: {p["id"]: p for p in r["packages"]}
        for pid, p in by_id(full).items():
            self.assertEqual(p["cost"], next(x["cost"] for x in PACKAGES if x["id"] == pid))
            self.assertAlmostEqual(by_id(small)[pid]["cost"], p["cost"] / 2, delta=1)

    def test_incentive_and_net_cost_add_up(self):
        for p in build_report(answers())["packages"]:
            self.assertEqual(p["cost"] - p["incentive"], p["net_cost"])
            self.assertGreaterEqual(p["incentive"], 0)

    def test_within_budget_is_cost_at_or_under_the_budget(self):
        cost = next(p["cost"] for p in PACKAGES if p["id"] == "basic")
        for budget, expected in ((cost - 1, False), (cost, True), (cost + 1, True)):
            with self.subTest(budget=budget):
                report = build_report(answers(budget=budget))
                basic = next(p for p in report["packages"] if p["id"] == "basic")
                self.assertIs(basic["within_budget"], expected)
        self.assertFalse(any(p["within_budget"] for p in build_report(answers(budget=0))["packages"]))

    def test_baseline_grows_with_floor_area(self):
        a = build_report(answers(floor_area=100))["baseline"]
        b = build_report(answers(floor_area=200))["baseline"]
        self.assertEqual(b["energy_kwh"], 2 * a["energy_kwh"])
        self.assertLess(a["heating_kwh"] + a["cooling_kwh"], a["energy_kwh"])

    def test_the_report_names_the_archetype_and_echoes_the_budget(self):
        report = build_report(answers())
        self.assertEqual(report["archetype"]["id"], "detached_gen1")
        self.assertEqual(report["archetype"]["confidence"], 1.0)
        self.assertEqual(report["budget"], 30000)


class MatchBaselineTests(SimpleTestCase):
    def test_an_exact_copy_of_an_archetype_matches_it_fully(self):
        for archetype in ARCHETYPES:
            with self.subTest(archetype=archetype["id"]):
                match = match_baseline(archetype["profile"])
                self.assertEqual(match.archetype_id, archetype["id"])
                self.assertEqual(match.confidence, 1.0)
                self.assertEqual(match.mismatched, [])

    def test_unanswered_or_not_sure_counts_as_half_a_match(self):
        total = sum(WEIGHTS.values())
        for form in (None, NOT_SURE):
            with self.subTest(building_form=form):
                match = match_baseline({"building_form": form, "year_of_construction": GEN_1})
                self.assertEqual(match.confidence, round((WEIGHTS["building_form"] / 2 + WEIGHTS["year_of_construction"]) / total, 2))

    def test_a_wrong_answer_is_listed_and_lowers_the_confidence(self):
        match = match_baseline({"building_form": "Detached house", "year_of_construction": GEN_5})
        self.assertIn("year_of_construction", match.mismatched)
        self.assertLess(match.confidence, 1)

    def test_answers_matching_nothing_still_pick_an_archetype(self):
        match = match_baseline({})
        self.assertIn(match.archetype_id, [a["id"] for a in ARCHETYPES])
        self.assertTrue(0 <= match.confidence <= 1)

    def test_every_archetype_uses_real_answers_for_every_weighted_question(self):
        for archetype in ARCHETYPES:
            self.assertEqual(set(archetype["profile"]), set(WEIGHTS), archetype["id"])
            self.assertIn(archetype["profile"]["building_form"], BUILDING_FORMS)
            self.assertNotEqual(archetype["profile"]["building_form"], NOT_SURE)
            self.assertIn(archetype["profile"]["year_of_construction"], YEAR_OPTIONS)
