from dataclasses import dataclass

from .formspec import NOT_SURE

# Which representative modelled house (archetype) a home is compared with. Only the questions the
# form asks are used: building form and construction period.
# PLACEHOLDER WEIGHTS AND ARCHETYPES: replace with the real archetype library and its weights.
WEIGHTS = {
    "building_form": 5,
    "year_of_construction": 4,
}

ARCHETYPES = [
    {
        "id": "detached_pre1941",
        "idf_file": "idf/detached_pre1941.idf",
        "profile": {"building_form": "Detached house", "year_of_construction": "Pre 1941"},
    },
    {
        "id": "detached_gen1",
        "idf_file": "idf/detached_gen1.idf",
        "profile": {"building_form": "Detached house", "year_of_construction": "Generation 1 (1941 - 1996)"},
    },
    {
        "id": "detached_gen3",
        "idf_file": "idf/detached_gen3.idf",
        "profile": {"building_form": "Detached house", "year_of_construction": "Generation 3 (2011 - 2016)"},
    },
    {
        "id": "semi_detached_gen1",
        "idf_file": "idf/semi_detached_gen1.idf",
        "profile": {"building_form": "Semi-detached house", "year_of_construction": "Generation 1 (1941 - 1996)"},
    },
    {
        "id": "townhouse_gen2",
        "idf_file": "idf/townhouse_gen2.idf",
        "profile": {"building_form": "Townhouse", "year_of_construction": "Generation 2 (1997 - 2010)"},
    },
    {
        "id": "lowrise_apartment_gen2",
        "idf_file": "idf/lowrise_apartment_gen2.idf",
        "profile": {"building_form": "Low-rise apartment", "year_of_construction": "Generation 2 (1997 - 2010)"},
    },
]


@dataclass
class BaselineMatch:
    archetype_id: str
    idf_file: str
    profile: dict
    confidence: float  # share of the weighted questions that matched (unanswered count half)
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
            elif given in (None, NOT_SURE):
                score += weight / 2
            else:
                mismatched.append(field)
        if best is None or score > best[0]:
            best = (score, archetype, mismatched)
    score, archetype, mismatched = best
    return BaselineMatch(
        archetype_id=archetype["id"],
        idf_file=archetype["idf_file"],
        profile=archetype["profile"],
        confidence=round(score / total, 2),
        mismatched=mismatched,
    )
