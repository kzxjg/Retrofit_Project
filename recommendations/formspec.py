import copy
import math
import re
from datetime import date

CURRENT_YEAR = date.today().year  # the import-time default; validate()/public_spec() use today


POSTAL_LETTERS = {
    "A": ["NL"], "B": ["NS"], "C": ["PE"], "E": ["NB"],
    "G": ["QC"], "H": ["QC"], "J": ["QC"],
    "K": ["ON"], "L": ["ON"], "M": ["ON"], "N": ["ON"], "P": ["ON"],
    "R": ["MB"], "S": ["SK"], "T": ["AB"], "V": ["BC"],
    "X": ["NT", "NU"], "Y": ["YT"],
}

# Climate zones that occur in each province or territory. Zones follow heating degree days, so a
# province spans several; this is deliberately generous (a zone is allowed if any part of the
# province falls in it) and exists to catch a postal code and zone that cannot belong together.
# PLACEHOLDER: replace with the official province-by-zone table when it is available.
PROVINCE_ZONES = {
    "BC": ["zone4", "zone5", "zone6", "zone7a", "zone7b", "zone8"],  # zone8: far north (e.g. Atlin)
    "AB": ["zone6", "zone7a", "zone7b", "zone8"],  # zone8: far north (e.g. High Level)
    "SK": ["zone7a", "zone7b", "zone8"],
    "MB": ["zone7a", "zone7b", "zone8"],
    "ON": ["zone5", "zone6", "zone7a", "zone7b", "zone8"],
    "QC": ["zone6", "zone7a", "zone7b", "zone8"],
    "NB": ["zone6", "zone7a"],
    "NS": ["zone5", "zone6"],
    "PE": ["zone6"],
    "NL": ["zone6", "zone7a", "zone7b", "zone8"],
    "YT": ["zone7b", "zone8"],
    "NT": ["zone7b", "zone8"],
    "NU": ["zone8"],
}

# [0-9], not \d: \d also matches non-Latin digits such as Arabic-Indic ones.
POSTAL_RE = re.compile(r"[ABCEGHJ-NPRSTVXY][0-9][ABCEGHJ-NPRSTV-Z][0-9][ABCEGHJ-NPRSTV-Z][0-9]")


# Zones
ZONES = [
    {
        "id": "zone4",
        "name": "Zone 4",
        "hdd_min": 0,
        "hdd_max": 3000,
        "description": "Mildest; mainly coastal southern BC",
        "cities": "Vancouver, Victoria, Abbotsford, Nanaimo, Chilliwack",
    },
    {
        "id": "zone5",
        "name": "Zone 5",
        "hdd_min": 3000,
        "hdd_max": 4000,
        "description": "Southern BC/Alberta and southern Ontario/Quebec",
        "cities": "Toronto, Kelowna, Windsor, London, Hamilton, Kingston, Vancouver-area locations",
    },
    {
        "id": "zone6",
        "name": "Zone 6",
        "hdd_min": 4000,
        "hdd_max": 5000,
        "description": "Much of southern/interior Canada",
        "cities": "Ottawa, Montreal, Halifax, Fredericton, St. John's, Québec City",
    },
    {
        "id": "zone7a",
        "name": "Zone 7A",
        "hdd_min": 5000,
        "hdd_max": 6000,
        "description": "Prairies and colder parts of central Canada",
        "cities": "Calgary, Edmonton, Winnipeg, Saskatoon, Regina, Thunder Bay",
    },
    {
        "id": "zone7b",
        "name": "Zone 7B",
        "hdd_min": 6000,
        "hdd_max": 7000,
        "description": "Very cold northern/interior areas",
        "cities": "Fort McMurray, Yellowhead/northern Alberta communities, northern Manitoba/Quebec communities",
    },
    {
        "id": "zone8",
        "name": "Zone 8",
        "hdd_min": 7000,
        "hdd_max": None,
        "description": "Far northern Canada",
        "cities": "Yellowknife, Iqaluit, Whitehorse and other far-northern communities",
    },
]


def zones_for_postal_letter(letter):
    """Zone ids that can occur where a postal code starting with this letter is."""
    allowed = set()
    for province in POSTAL_LETTERS.get(letter, []):
        allowed.update(PROVINCE_ZONES[province])
    return [z["id"] for z in ZONES if z["id"] in allowed]


ZONE_OPTIONS = [f"{z['name']}: {z['description']} ({z['cities']})" for z in ZONES]
ZONE_BY_OPTION = dict(zip(ZONE_OPTIONS, ZONES))


def zone_for_hdd(hdd):
    for zone in ZONES:
        if hdd >= zone["hdd_min"] and (zone["hdd_max"] is None or hdd < zone["hdd_max"]):
            return zone
    raise ValueError(f"No zone covers {hdd} HDD18")


# Construction periods the archetype library is organised by. Not asked directly: worked out
# from the year the user types (see validate()).
YEAR_RANGES = [
    {"label": "Pre 1941", "min": None, "max": 1940},
    {"label": "Generation 1 (1941 - 1996)", "min": 1941, "max": 1996},
    {"label": "Generation 2 (1997 - 2010)", "min": 1997, "max": 2010},
    {"label": "Generation 3 (2011 - 2016)", "min": 2011, "max": 2016},
    {"label": "Generation 4 (2017 - 2019)", "min": 2017, "max": 2019},
    {"label": "Generation 5 (From 2020)", "min": 2020, "max": None},
]
YEAR_OPTIONS = [r["label"] for r in YEAR_RANGES]


def generation_for_year(year):
    for r in YEAR_RANGES:
        if (r["min"] is None or year >= r["min"]) and (r["max"] is None or year <= r["max"]):
            return r["label"]


BUILDING_FORMS = ["Detached house", "Semi-detached house", "Townhouse", "Low-rise apartment", "Not sure"]
NOT_SURE = "Not sure"

SIMPLE_MODE = "Simple – choose what matters most"
ADVANCED_MODE = "Advanced – adjust numerical weights"

# The criteria every retrofit package is scored on (logic.py), with the starting slider values.
CRITERIA = [
    {"id": "initial_cost", "label": "Initial cost", "default": 20},
    {"id": "energy_savings", "label": "Energy savings", "default": 25},
    {"id": "operational_carbon", "label": "Operational carbon", "default": 20},
    {"id": "embodied_carbon", "label": "Embodied carbon", "default": 10},
    {"id": "payback", "label": "Payback", "default": 15},
    {"id": "resilience", "label": "Future resilience", "default": 10},
]
CRITERIA_IDS = [c["id"] for c in CRITERIA]

PRIORITY_OPTIONS = [
    "Balanced outcome", "Lowest upfront cost", "Maximum energy savings",
    "Lowest carbon emissions", "Shortest payback period", "Future climate resilience",
]
SECONDARY_OPTIONS = [
    "Long-term performance", "Energy savings", "Lower carbon emissions",
    "Lower lifecycle cost", "Short payback",
]


def _f(id, label, type, **kw):
    field = {"id": id, "label": label, "type": type, "required": False}
    field.update(kw)
    return field


# Form
SECTIONS = [
    {
        "id": "home",
        "title": "Tell us about your home",
        "fields": [
            _f("postal_code", "Postal code / location", "text",
               required=True, format="postal_code", placeholder="e.g. N9A 1A1"),
            _f("year_built", "Approximate construction year", "number",
               required=True, integer=True, min=1800, max=CURRENT_YEAR, placeholder="e.g. 1985"),
            _f("floor_area", "Approximate floor area (m²)", "number",
               required=True, min=30, max=1000, placeholder="e.g. 180"),
            _f("building_form", "Building form (if known)", "select", options=BUILDING_FORMS),
            _f("zone", "Climate zone", "select",
               required=True, options=ZONE_OPTIONS, placement="map",
               must_match_postal={"field": "postal_code",
                                  "zones_by_letter": {l: zones_for_postal_letter(l) for l in POSTAL_LETTERS}}),
        ],
    },
    {
        "id": "priorities",
        "title": "Set your budget and priorities",
        "fields": [
            _f("budget", "Available retrofit budget (CAD)", "currency",
               required=True, min=0, max=10_000_000, placeholder="e.g. 30000"),
            _f("preference_mode", "Preference setting", "select",
               required=True, options=[SIMPLE_MODE, ADVANCED_MODE]),
            _f("priority", "What matters most to you?", "select", required=True,
               options=PRIORITY_OPTIONS, show_if={"field": "preference_mode", "equals": SIMPLE_MODE}),
            _f("secondary_priority", "Second priority", "select",
               options=SECONDARY_OPTIONS, show_if={"field": "preference_mode", "equals": SIMPLE_MODE}),
            _f("weights", "Criteria weights", "weights", required=True,
               criteria=CRITERIA, min=0, max=100,
               help="Adjust the relative importance of each criterion. The values are normalized automatically for ranking.",
               show_if={"field": "preference_mode", "equals": ADVANCED_MODE}),
        ],
    },
]

FIELDS = [field for section in SECTIONS for field in section["fields"]]
FIELD_BY_ID = {field["id"]: field for field in FIELDS}


MAX_ANSWERS = 100
MAX_ERRORS = 20
# Used with fullmatch: with match(), "$" would also accept a trailing newline.
SAFE_KEY_RE = re.compile(r"[a-z][a-z0-9_]{0,49}")


#returns the JSON so the frontend can build off it 
def public_spec():
    """A per-request copy, so no caller can mutate the shared form definition.

    The copy also carries the current calendar year without writing into
    SECTIONS or FIELD_BY_ID.
    """
    sections = copy.deepcopy(SECTIONS)
    for section in sections:
        for field in section["fields"]:
            if field["id"] == "year_built":
                field["max"] = date.today().year
    return {"sections": sections}


# Far beyond any real answer. Python ints have no size limit, and one too big to
# turn into a float would crash float() and math.isfinite().
MAX_MAGNITUDE = 10**15

#Checks that a value is a real finite number. Rejects booleans infinity and Nan values.
def _is_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return abs(value) <= MAX_MAGNITUDE
    return isinstance(value, float) and math.isfinite(value) and abs(value) <= MAX_MAGNITUDE


def _visible(field, data):
    cond = field.get("show_if")
    return not cond or data.get(cond["field"]) == cond["equals"]


def validate(data):
    errors = []
    clean = {}

    if not isinstance(data, dict):
        return {}, [{"field": "answers", "message": "Answers must be a JSON object."}]
    if len(data) > MAX_ANSWERS:
        return {}, [{"field": "answers", "message": "Too many fields in the request."}]

    def err(field_id, message):
        if len(errors) < MAX_ERRORS:
            errors.append({"field": field_id, "message": message})

    for key in data:
        if key not in FIELD_BY_ID:
            err(key if SAFE_KEY_RE.fullmatch(key) else "answers", "Unknown field.")

    for field in FIELDS:
        fid, label, ftype = field["id"], field["label"], field["type"]
        if not _visible(field, data):
            continue
        value = data.get(fid)
        if value is None or value == "" or value == [] or value == {}:
            if field["required"]:
                err(fid, f"{label} is required.")
            continue

        if ftype == "text":
            if not isinstance(value, str):
                err(fid, f"{label} must be text.")
            else:  # every text question is a postal code (tests.py checks there is no other kind)
                cleaned = re.sub(r"\s+", "", value).upper()
                if not POSTAL_RE.fullmatch(cleaned):
                    err(fid, "Enter a valid Canadian postal code, e.g. N9A 1A1.")
                else:
                    clean[fid] = f"{cleaned[:3]} {cleaned[3:]}"

        elif ftype == "select":
            if value not in field["options"]:
                err(fid, f"{label}: choose one of the listed options.")
            else:
                clean[fid] = value

        elif ftype in ("number", "currency"):
            if not _is_number(value):
                err(fid, f"{label} must be a number.")
                continue
            if field.get("integer") and not isinstance(value, int):
                err(fid, f"{label} must be a whole number, without a decimal point.")  # 1985.0 and 2e3 too
                continue
            value = value + 0  # -0.0 becomes 0.0
            lo, hi = field.get("min"), field.get("max")
            if fid == "year_built":
                hi = date.today().year  # never mutate the shared spec for a calendar rollover
            if (lo is not None and value < lo) or (hi is not None and value > hi):
                err(fid, f"{label} is outside the allowed range ({lo} to {hi}).")
                continue
            clean[fid] = value

        elif ftype == "weights":
            lo, hi = field["min"], field["max"]
            ids = [c["id"] for c in field["criteria"]]
            if (
                not isinstance(value, dict)
                or set(value) != set(ids)
                or not all(_is_number(v) and isinstance(v, int) and lo <= v <= hi for v in value.values())
            ):
                err(fid, f"{label}: give each criterion a whole number from {lo} to {hi}.")
            elif sum(value.values()) == 0:
                err(fid, f"{label}: give at least one criterion a weight above 0.")
            else:
                clean[fid] = {i: value[i] for i in ids}

    postal, zone_option = clean.get("postal_code"), data.get("zone")
    if postal and isinstance(zone_option, str) and "zone" in clean:
        zone = ZONE_BY_OPTION[zone_option]
        if zone["id"] not in zones_for_postal_letter(postal[0]):
            err("zone", f"{zone['name']} does not occur where postal code {postal} is. "
                        "Choose a climate zone for your area.")

    if clean.get("year_built"):
        clean["year_of_construction"] = generation_for_year(clean["year_built"])
    if "zone" in clean:
        clean["zone_id"] = ZONE_BY_OPTION[clean["zone"]]["id"]

    return clean, errors
