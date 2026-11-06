from dataclasses import dataclass


#FAKE WEIGHTS NEED THE REAL ONES FROM THE DATA AND THEN REDO THIS ENTIRE SECTION
WEIGHTS = {
    "house_type": 5,
    "year_of_construction": 4,
    "primary_heating": 3,
    "heating_fuel": 3,
    "cooling_system": 2,
    "window_type": 2,
    "insulation_type": 2,
    "wall_construction": 1,
    "basement_type": 1,
}

ARCHETYPES = [
    {
        "id": "detached_pre1941_gas",
        "idf_file": "idf/detached_pre1941_gas.idf",
        "profile": {
            "house_type": "Detached house", "year_of_construction": "Pre 1941",
            "primary_heating": "Gas furnace", "heating_fuel": "Natural gas",
            "cooling_system": "Central air conditioner", "window_type": "Single glazing",
            "insulation_type": "Unknown", "wall_construction": "Masonry",
            "basement_type": "Full basement",
        },
    },
    {
        "id": "detached_gen1_gas",
        "idf_file": "idf/detached_gen1_gas.idf",
        "profile": {
            "house_type": "Detached house", "year_of_construction": "Generation 1 (1941 - 1996)",
            "primary_heating": "Gas furnace", "heating_fuel": "Natural gas",
            "cooling_system": "Central air conditioner", "window_type": "Double glazing",
            "insulation_type": "Fibreglass", "wall_construction": "Wood frame",
            "basement_type": "Full basement",
        },
    },
    {
        "id": "detached_gen3_heatpump",
        "idf_file": "idf/detached_gen3_heatpump.idf",
        "profile": {
            "house_type": "Detached house", "year_of_construction": "Generation 3 (2011 - 2016)",
            "primary_heating": "Heat pump", "heating_fuel": "Electricity",
            "cooling_system": "Heat pump", "window_type": "Double glazing",
            "insulation_type": "Fibreglass", "wall_construction": "Wood frame",
            "basement_type": "Full basement",
        },
    },
    {
        "id": "townhouse_gen2_gas",
        "idf_file": "idf/townhouse_gen2_gas.idf",
        "profile": {
            "house_type": "Row house or townhouse", "year_of_construction": "Generation 2 (1997 - 2010)",
            "primary_heating": "Gas furnace", "heating_fuel": "Natural gas",
            "cooling_system": "Central air conditioner", "window_type": "Double glazing",
            "insulation_type": "Fibreglass", "wall_construction": "Wood frame",
            "basement_type": "Slab-on-grade",
        },
    },
]


@dataclass
class BaselineMatch:
    archetype_id: str
    idf_file: str
    confidence: float  
    mismatched: list  


def match_baseline(answers):
    total = sum(WEIGHTS.values())
    best = None
    for archetype in ARCHETYPES:
        score, mismatched = 0.0, []
        for field, weight in WEIGHTS.items():
            given = answers.get(field)
            if given == archetype["profile"][field]:
                score += weight
            elif given in (None, "Unknown"):
                score += weight / 2  
            else:
                mismatched.append(field)
        if best is None or score > best[0]:
            best = (score, archetype, mismatched)
    score, archetype, mismatched = best
    return BaselineMatch(
        archetype_id=archetype["id"],
        idf_file=archetype["idf_file"],
        confidence=round(score / total, 2),
        mismatched=mismatched,
    )
