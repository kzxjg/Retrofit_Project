"""The home energy report: baseline estimate, and the retrofit packages ranked by the user's priorities.

PLACEHOLDER NUMBERS: the baseline intensity, package costs, savings and carbon below are sample values
for the interface. Replace them with the calibrated archetype, EnergyPlus, cost and carbon datasets
before real-world use. Combined packages must come from their own combined simulations, not from
adding up individual savings.
"""

from .baseline import match_baseline
from .formspec import ADVANCED_MODE, CRITERIA_IDS, PRIORITY_OPTIONS, SECONDARY_OPTIONS

# Baseline (illustrative): energy intensity, end-use shares and grid emission factor.
ENERGY_KWH_PER_M2 = 160
HEATING_SHARE = 0.70
COOLING_SHARE = 0.10
CARBON_T_PER_KWH = 0.00020

# Package costs below are for this floor area and scale with it.
REFERENCE_AREA_M2 = 180
INCENTIVE_SHARE = 0.10  # illustrative; eligibility must be verified against official programs

PACKAGES = [
    {"id": "basic", "name": "Targeted insulation & air sealing", "tag": "Budget-friendly",
     "description": "Attic insulation, targeted air sealing and selected envelope improvements.",
     "cost": 11500, "saving_pct": 22, "carbon_t": 1.25, "embodied_t": 1.2, "payback_yrs": 7.4, "resilience": 58},
    {"id": "heatpump", "name": "High-efficiency heat pump package", "tag": "Heating & cooling",
     "description": "Heating and cooling system upgrade with required electrical and distribution improvements.",
     "cost": 18500, "saving_pct": 31, "carbon_t": 1.65, "embodied_t": 2.0, "payback_yrs": 9.1, "resilience": 78},
    {"id": "envelope", "name": "Deep envelope retrofit", "tag": "Long-term performance",
     "description": "More comprehensive roof, wall, window and airtightness improvements.",
     "cost": 28500, "saving_pct": 39, "carbon_t": 1.9, "embodied_t": 4.2, "payback_yrs": 12.2, "resilience": 84},
    {"id": "combined", "name": "Whole-home coordinated package", "tag": "Best overall potential",
     "description": "Coordinated envelope, heat pump, controls and ventilation improvements.",
     "cost": 39000, "saving_pct": 58, "carbon_t": 2.7, "embodied_t": 5.8, "payback_yrs": 11.6, "resilience": 92},
]

# Weights for each "What matters most" answer, in CRITERIA_IDS order.
PRIORITY_WEIGHTS = dict(zip(PRIORITY_OPTIONS, [
    [.20, .22, .18, .10, .15, .15],  # Balanced outcome
    [.42, .12, .10, .08, .22, .06],  # Lowest upfront cost
    [.10, .38, .20, .06, .08, .18],  # Maximum energy savings
    [.08, .20, .38, .18, .06, .10],  # Lowest carbon emissions
    [.20, .12, .12, .06, .42, .08],  # Shortest payback period
    [.08, .18, .18, .08, .08, .40],  # Future climate resilience
]))

# The criterion each "Second priority" answer leans towards, and how far.
SECONDARY_CRITERION = dict(zip(SECONDARY_OPTIONS, [
    "resilience", "energy_savings", "operational_carbon", "payback", "payback",
]))
SECONDARY_SHARE = 0.20

#Priority sliders 6 weights that add up to 1
def criterion_weights(answers):
    """The user's weights, normalised to add up to 1, keyed by criterion id."""
    if answers.get("preference_mode") == ADVANCED_MODE:
        raw = [answers["weights"][c] for c in CRITERIA_IDS]
    else:
        raw = list(PRIORITY_WEIGHTS[answers["priority"]])
        second = SECONDARY_CRITERION.get(answers.get("secondary_priority"))
        if second:
            total = sum(raw)
            raw = [w / total * (1 - SECONDARY_SHARE) for w in raw]
            raw[CRITERIA_IDS.index(second)] += SECONDARY_SHARE
    total = sum(raw)
    return {c: w / total for c, w in zip(CRITERIA_IDS, raw)}


#Rates package from 0 to 1 on each of the 6 criteria. 
def criterion_values(package):
    """How well a package does on each criterion, from 0 (worst) to about 1 (best)."""
    return {
        "initial_cost": 1 - package["cost"] / 45000,
        "energy_savings": package["saving_pct"] / 65,
        "operational_carbon": package["carbon_t"] / 3.2,
        "embodied_carbon": 1 - package["embodied_t"] / 7,
        "payback": 1 - package["payback_yrs"] / 16,
        "resilience": package["resilience"] / 100,
    }

#Gets the overall score of the 6 weights
def score(package, weights):
    values = criterion_values(package)
    return sum(values[c] * weights[c] for c in CRITERIA_IDS)


#Estimates energy, heating, cooling and emissions as floor area x first rates
def baseline_energy(area_m2):
    energy = round(area_m2 * ENERGY_KWH_PER_M2)
    return {
        "energy_kwh": energy,
        "heating_kwh": round(energy * HEATING_SHARE),
        "cooling_kwh": round(energy * COOLING_SHARE),
        "carbon_t": round(energy * CARBON_T_PER_KWH, 1),
    }


def build_report(answers):
    """Everything the report pages show, from validated answers (formspec.validate)."""
    area = answers["floor_area"]
    budget = answers["budget"]
    weights = criterion_weights(answers)
    match = match_baseline(answers)

    packages = []
    for p in PACKAGES:
        cost = round(p["cost"] * area / REFERENCE_AREA_M2)
        incentive = round(cost * INCENTIVE_SHARE)
        packages.append({
            "id": p["id"], "name": p["name"], "tag": p["tag"], "description": p["description"],
            "cost": cost, "incentive": incentive, "net_cost": cost - incentive,
            "saving_pct": p["saving_pct"], "carbon_t": p["carbon_t"], "embodied_t": p["embodied_t"],
            "payback_yrs": p["payback_yrs"], "resilience": p["resilience"],
            "score": round(score(p, weights), 4),
            "within_budget": cost <= budget,
        })
    packages.sort(key=lambda p: p["score"], reverse=True)

    return {
        "archetype": {
            "id": match.archetype_id,
            "building_form": match.profile["building_form"],
            "period": match.profile["year_of_construction"],
            "confidence": match.confidence,
        },
        "baseline": baseline_energy(area),
        "budget": budget,
        "weights": {c: round(w, 4) for c, w in weights.items()},
        "packages": packages,
    }
