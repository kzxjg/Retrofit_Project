import math
import re
import unicodedata
from datetime import date

from .incentives import incentives_for

CURRENT_YEAR = date.today().year  # at import; _sync_current_year() keeps the limits up to date


def _sync_current_year():
    """Move the "this year" limits forward when the calendar does, without a server restart."""
    year = date.today().year
    FIELD_BY_ID["year_built"]["max"] = year
    FIELD_BY_ID["renovation_history"]["year_range"][1] = year

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


#Zones 
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


METRIC = "Metric (m², kWh)"
IMPERIAL = "Imperial (ft², Btu)"
UNIT_SYSTEMS = {
    METRIC: {"area": "m²", "temperature": "°C", "length": "mm"},
    IMPERIAL: {"area": "ft²", "temperature": "°F", "length": "in"},
}


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


FLOOR_AREA_EDGES_M2 = [50, 100, 150, 200, 300, 400]
FLOOR_AREA_REPRESENTATIVE_M2 = [40, 75, 125, 175, 250, 350, 500]  


def _edge(m2, imperial):
    return f"{round(m2 / 0.09290304 / 10) * 10:,}" if imperial else f"{m2:,}"


def _floor_area_labels(imperial):
    unit = "ft²" if imperial else "m²"
    edges = FLOOR_AREA_EDGES_M2
    labels = [f"Under {_edge(edges[0], imperial)} {unit}"]
    labels += [f"{_edge(a, imperial)}–{_edge(b, imperial)} {unit}" for a, b in zip(edges, edges[1:])]
    labels.append(f"Over {_edge(edges[-1], imperial)} {unit}")
    return labels


FLOOR_AREA_OPTIONS = _floor_area_labels(imperial=False)
FLOOR_AREA_NUMERIC = dict(zip(FLOOR_AREA_OPTIONS, FLOOR_AREA_REPRESENTATIVE_M2))
STOREY_OPTIONS = [str(n) for n in range(1, 11)]
STOREY_NUMERIC = {option: int(option) for option in STOREY_OPTIONS}
OCCUPANT_OPTIONS = ["1", "2", "3 or above"]
OCCUPANT_NUMERIC = {"1": 1, "2": 2, "3 or above": 3}

RENOVATION_ELEMENTS = ["Walls", "Roof", "HVAC system", "Windows", "Doors"]


def _f(id, label, type, **kw):
    field = {"id": id, "label": label, "type": type, "required": False}
    field.update(kw)
    return field


#Form 
SECTIONS = [
    {
        "id": "general",
        "title": "General building information",
        "fields": [
            _f("postal_code", "Postal code", "text",
               required=True, format="postal_code", placement="top", placeholder="N9A 1A1"),
            _f("year_built", "Year built", "number",
               required=True, integer=True, min=1800, max=CURRENT_YEAR, placement="top",
               ranges=YEAR_RANGES, placeholder="e.g. 1985"),
            _f("zone", "Climate Zone", "select",
               required=True, options=ZONE_OPTIONS, placement="map",
               must_match_postal={"field": "postal_code",
                                  "zones_by_letter": {l: zones_for_postal_letter(l) for l in POSTAL_LETTERS}}),
            _f("preferred_units", "Preferred units", "radio",
               required=True, options=[METRIC, IMPERIAL], placement="top"),
            _f("floor_area", "Total floor area", "select", required=True, placement="top",
               options=FLOOR_AREA_OPTIONS, numeric=FLOOR_AREA_NUMERIC,
               labels_by_unit={IMPERIAL: _floor_area_labels(imperial=True)}),
            _f("storeys", "Number of storeys", "select", required=True, placement="top",
               options=STOREY_OPTIONS, numeric=STOREY_NUMERIC),
            _f("storeys_above_ground", "Number of storeys above ground", "select",
               required=True, placement="top", options=STOREY_OPTIONS, numeric=STOREY_NUMERIC,
               not_more_than={"field": "storeys",
                              "message": "Storeys above ground cannot be more than the total number of storeys."}),
            _f("occupants", "Number of occupants", "select", placement="top",
               options=OCCUPANT_OPTIONS, numeric=OCCUPANT_NUMERIC,
               help="Number of adults and kids living in the building."),
            _f("house_type", "Type of house", "select", required=True, placement="top",
               options=["Detached house", "Semi-detached house",
                        "Row house or townhouse", "Duplex or triplex", "Other"]),
            _f("basement_type", "Basement type", "select", placement="top",
               options=["Full basement", "Partial basement", "Crawlspace",
                        "Slab-on-grade", "Other", "Unknown"]),
            _f("basement_heating", "Basement heating status", "select",
               options=["Fully heated", "Partially heated", "Unheated", "Not applicable"]),
            _f("renovation_history", "Renovation history", "records",
               help="Add each previous renovation: the building element and the year it was done.",
               type_options=RENOVATION_ELEMENTS, max_records=20, year_range=[1900, CURRENT_YEAR]),
        ],
    },
    {
        "id": "energy",
        "title": "Energy consumption and indoor comfort",
        "fields": [
            _f("energy_bill_winter", "Typical monthly energy bill in winter", "currency",
               min=0, max=20000),
            _f("energy_bill_summer", "Typical monthly energy bill in summer", "currency",
               min=0, max=20000),
            _f("indoor_temperature", "Preferred indoor temperature", "number",
               unit_kind="temperature", min=10, max=30),
            _f("household_equipment", "Available household equipment", "multiselect",
               options=["Refrigerator", "Freezer", "Clothes washer", "Clothes dryer",
                        "Dishwasher", "Electric oven", "Electric stove", "Television",
                        "Computer"]),
        ],
    },
    {
        "id": "envelope",
        "title": "Building materials and envelope characteristics",
        "fields": [
            _f("wall_materials", "Exterior wall materials", "multiselect", other_text=True,
               options=["Brick", "Wood siding", "Vinyl siding", "Concrete", "Masonry", "Other", "Unknown"]),
            _f("roof_materials", "Roof materials", "multiselect", other_text=True,
               options=["Asphalt shingles", "Metal roofing", "Tiles", "Other"]),
            _f("window_materials", "Window materials", "multiselect", other_text=True,
               help="Known glazing and frame materials. Detailed glazing and frame types are collected below.",
               options=["Glass", "Wood", "Vinyl", "Aluminium", "Fibreglass", "Other"]),
            _f("door_materials", "Door materials", "multiselect", other_text=True,
               options=["Wood", "Steel", "Fibreglass", "Other"]),
            _f("wall_thickness", "Exterior wall thickness", "number", unit_kind="length", min=20, max=1500,
               help="Total thickness of the wall, if known."),
            _f("roof_thickness", "Roof thickness", "number", unit_kind="length", min=20, max=1500,
               help="Total thickness of the roof, if known."),
            _f("wall_construction", "Wall construction type", "select", required=True,
               options=["Wood frame", "Masonry", "Concrete", "Steel frame", "Other", "Unknown"]),
            _f("insulation_type", "Existing insulation type", "select",
               options=["Fibreglass", "Mineral wool", "Cellulose", "Foam", "Other", "Unknown"]),
            _f("roof_type", "Roof type", "select",
               options=["Gable", "Hip", "Flat", "Shed", "Other", "Unknown"]),
            _f("attic_type", "Attic type", "select",
               options=["Vented attic", "Unvented attic", "Cathedral ceiling",
                        "Flat roof", "Other", "Unknown"]),
            _f("window_type", "Window type", "select", required=True,
               options=["Single glazing", "Double glazing", "Triple glazing", "Unknown"]),
            _f("window_frame", "Window frame material", "select",
               options=["Wood", "Vinyl", "Aluminium", "Fibreglass", "Other", "Unknown"]),
            _f("exterior_doors", "Number of exterior doors", "number",
               integer=True, min=0, max=20),
            _f("door_insulation", "Exterior door insulation", "select",
               options=["Insulated", "Uninsulated", "Unknown"]),
            _f("door_weatherstripping", "Exterior door weatherstripping condition", "select",
               options=["Good", "Fair", "Poor", "Absent", "Unknown"]),
            _f("door_drafts", "Visible gaps or drafts around exterior doors", "radio",
               options=["Yes", "No", "Unknown"]),
            _f("foundation_type", "Foundation type", "select",
               options=["Poured concrete", "Concrete block", "Stone", "Crawlspace",
                        "Slab-on-grade", "Other", "Unknown"]),
        ],
    },
    {
        "id": "systems",
        "title": "Existing heating and cooling systems",
        "fields": [
            _f("primary_heating", "Primary heating system", "select", required=True,
               options=["Gas furnace", "Electric furnace", "Boiler", "Heat pump",
                        "Oil furnace", "Propane furnace", "Other", "Unknown"]),
            _f("secondary_heating", "Secondary heating system", "select",
               options=["Wood stove", "Fireplace", "Electric baseboard",
                        "Secondary heat pump", "None", "Other", "Unknown"]),
            _f("heating_fuel", "Heating fuel", "select", required=True,
               options=["Natural gas", "Electricity", "Heating oil", "Propane",
                        "Wood", "Other", "Unknown"]),
            _f("cooling_system", "Cooling system type", "select", required=True,
               options=["Central air conditioner", "Heat pump", "Ductless mini-split",
                        "Window air conditioner", "Portable air conditioner",
                        "None", "Other", "Unknown"]),
        ],
    },
    {
        "id": "objectives",
        "title": "Retrofit objectives and constraints",
        "fields": [
            _f("objectives", "Main retrofit objective", "checklist", required=True,
               options=["Reduce energy bills", "Reduce greenhouse gas emissions",
                        "Improve thermal comfort", "Improve indoor air quality",
                        "Increase resilience during extreme weather",
                        "Improve building durability", "Reduce maintenance",
                        "Increase property value"]),
            _f("renovation_time", "Acceptable renovation time", "select",
               options=["Within 1 week", "1–4 weeks", "1–3 months",
                        "More than 3 months", "Flexible"]),
            _f("max_budget", "Maximum retrofit budget", "currency", min=0, max=10000000),
            _f("budget_flexibility", "Budget flexibility", "select",
               options=["Fixed", "Somewhat flexible", "Highly flexible"]),
            _f("target_subsidies", "Expecting to target government subsidies", "radio",
               options=["Yes", "No", "Undecided"]),
            _f("subsidies", "Government subsidies", "incentives",
               show_if={"field": "target_subsidies", "equals": "Yes"},
               help="Programs that may apply to your province. Eligibility must be verified before applying."),
        ],
    },
    {
        "id": "renewables",
        "title": "Renewable energy systems",
        "fields": [
            _f("solar_existing", "Existing solar PV installation", "radio",
               options=["Yes", "No", "Planned"]),
            _f("solar_capacity_kw", "Existing solar PV capacity (kW), if known", "number",
               unit_kind="power", min=0.1, max=100,
               show_if={"field": "solar_existing", "equals": "Yes"}),
            _f("solar_interest", "Interest in installing solar PV", "radio",
               options=["Yes", "No", "Undecided"]),
        ],
    },
]

FIELDS = [field for section in SECTIONS for field in section["fields"]]
FIELD_BY_ID = {field["id"]: field for field in FIELDS}


MAX_ANSWERS = 100
MAX_ERRORS = 20
# Used with fullmatch: with match(), "$" would also accept a trailing newline.
SAFE_KEY_RE = re.compile(r"[a-z][a-z0-9_]{0,49}")


def public_spec():
    _sync_current_year()
    return {
        "unit_field": "preferred_units",
        "unit_systems": UNIT_SYSTEMS,
        "sections": SECTIONS,
    }


# Far beyond any real answer. Python ints have no size limit, and one too big to
# turn into a float would crash float() and math.isfinite().
MAX_MAGNITUDE = 10**15


def _is_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return abs(value) <= MAX_MAGNITUDE
    return isinstance(value, float) and math.isfinite(value) and abs(value) <= MAX_MAGNITUDE


def _clean_text(value, limit=200):
    value = unicodedata.normalize("NFC", value)
    value = "".join(ch for ch in value if not unicodedata.category(ch).startswith("C"))
    return value.strip()[:limit]


def _visible(field, data):
    cond = field.get("show_if")
    return not cond or data.get(cond["field"]) == cond["equals"]


def _canonical(value, kind, imperial):
    if imperial and kind == "area":
        return value * 0.09290304
    if imperial and kind == "temperature":
        return (value - 32) * 5 / 9
    if imperial and kind == "length":
        return value * 25.4
    return value


def _shown(limit, kind, imperial):
    """A limit (kept in metric) written in the units the user chose, e.g. 10 °C as 50 °F."""
    if limit is None or not imperial:
        return limit
    if kind == "area":
        value = limit / 0.09290304
    elif kind == "temperature":
        value = limit * 9 / 5 + 32
    elif kind == "length":
        value = limit / 25.4
    else:
        return limit
    value = round(value, 2)
    return int(value) if value == int(value) else value


def validate(data):
    _sync_current_year()
    errors = []
    clean = {}

    if not isinstance(data, dict):
        return {}, [{"field": "answers", "message": "Answers must be a JSON object."}]
    if len(data) > MAX_ANSWERS:
        return {}, [{"field": "answers", "message": "Too many fields in the request."}]

    def err(field_id, message):
        if len(errors) < MAX_ERRORS:
            errors.append({"field": field_id, "message": message})

    known = set(FIELD_BY_ID)
    known |= {f["id"] + "_other" for f in FIELDS if f.get("other_text")}
    for key in data:
        if key not in known:
            err(key if SAFE_KEY_RE.fullmatch(key) else "answers", "Unknown field.")

    units = data.get("preferred_units")
    imperial = isinstance(units, str) and units.startswith("Imperial")

    for field in FIELDS:
        fid, label, ftype = field["id"], field["label"], field["type"]
        if not _visible(field, data):
            continue  
        value = data.get(fid)
        if value is None or value == "" or value == []:
            if field["required"]:
                err(fid, f"{label} is required.")
            continue

        if ftype == "text":
            if not isinstance(value, str):
                err(fid, f"{label} must be text.")
            elif field.get("format") == "postal_code":
                cleaned = re.sub(r"\s+", "", value).upper()
                if not POSTAL_RE.fullmatch(cleaned):
                    err(fid, "Enter a valid Canadian postal code, e.g. N9A 1A1.")
                else:
                    clean[fid] = f"{cleaned[:3]} {cleaned[3:]}"
            else:
                clean[fid] = _clean_text(value)

        elif ftype in ("select", "radio"):
            if value not in field["options"]:
                err(fid, f"{label}: choose one of the listed options.")
            else:
                clean[fid] = field["numeric"][value] if "numeric" in field else value

        elif ftype in ("number", "currency"):
            if not _is_number(value):
                err(fid, f"{label} must be a number.")
                continue
            if field.get("integer") and not isinstance(value, int):
                err(fid, f"{label} must be a whole number, without a decimal point.")  # 1985.0 and 2e3 too
                continue
            value = value + 0  # -0.0 becomes 0.0
            canonical = _canonical(value, field.get("unit_kind"), imperial)
            lo, hi = field.get("min"), field.get("max")
            if (lo is not None and canonical < lo) or (hi is not None and canonical > hi):
                kind = field.get("unit_kind")
                system = IMPERIAL if imperial else METRIC
                unit = UNIT_SYSTEMS[system].get(kind, "") if kind else ""
                shown_lo, shown_hi = (_shown(limit, kind, imperial) for limit in (lo, hi))
                err(fid, f"{label} is outside the allowed range ({shown_lo} to {shown_hi} {unit}).".replace(" )", ")"))
                continue
            clean[fid] = round(canonical, 2) if field.get("unit_kind") else value

        elif ftype in ("checklist", "multiselect"):
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                err(fid, f"{label} must be a list of choices.")
                continue
            bad = [v for v in value if v not in field["options"]]
            if bad:
                err(fid, f"{label}: choose only from the listed options.")
                continue
            clean[fid] = list(dict.fromkeys(value))
            if field.get("other_text") and "Other" in value:
                other = data.get(fid + "_other")
                if other is not None and not isinstance(other, str):
                    err(fid + "_other", f"{label}: the other answer must be text.")
                    continue
                other = _clean_text(other) if other else ""
                if other:
                    clean[fid + "_other"] = other

        elif ftype == "records":
            lo, hi = field["year_range"]
            if not isinstance(value, list):
                err(fid, f"{label} must be a list.")
                continue
            if len(value) > field["max_records"]:
                err(fid, f"{label}: at most {field['max_records']} records.")
                continue
            records, ok = [], True
            for i, rec in enumerate(value, start=1):
                valid = (
                    isinstance(rec, dict)
                    and set(rec) == {"type", "year"}
                    and isinstance(rec["type"], str)
                    and 1 <= len(rec["type"].strip()) <= 100
                    and (not field.get("type_options") or rec["type"].strip() in field["type_options"])
                    and _is_number(rec["year"])
                    and isinstance(rec["year"], int)  # a year like 2015.0 is not a whole number here
                    and lo <= rec["year"] <= hi
                )
                if not valid:
                    err(fid, f"{label}: record {i} needs a building element and a year between {lo} and {hi}.")
                    ok = False
                    break
                records.append({"type": rec["type"].strip(), "year": rec["year"]})
            if ok:
                clean[fid] = records

        elif ftype == "incentives":
            zone_answer = data.get("zone")
            zone = ZONE_BY_OPTION.get(zone_answer) if isinstance(zone_answer, str) else None
            allowed = [p["name"] for p in incentives_for(zone["id"] if zone else None)]
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                err(fid, f"{label} must be a list of programs.")
            elif any(v not in allowed for v in value):
                err(fid, f"{label}: a selected program is not available for this climate zone.")
            else:
                clean[fid] = list(dict.fromkeys(value))

    for field in FIELDS:
        rule = field.get("not_more_than")
        if rule:
            mine, other = clean.get(field["id"]), clean.get(rule["field"])
            if mine is not None and other is not None and mine > other:
                err(field["id"], rule["message"])


    postal, zone_option = clean.get("postal_code"), data.get("zone")
    if postal and isinstance(zone_option, str) and "zone" in clean:
        zone = ZONE_BY_OPTION[zone_option]
        if zone["id"] not in zones_for_postal_letter(postal[0]):
            err("zone", f"{zone['name']} does not occur where postal code {postal} is. "
                        "Choose a climate zone for your area.")

    built, renovations = clean.get("year_built"), clean.get("renovation_history")
    if built and renovations:
        early = next((i for i, rec in enumerate(renovations, start=1) if rec["year"] < built), None)
        if early:
            err("renovation_history",
                f"Renovation {early} is dated before the building was built ({built}).")
            del clean["renovation_history"]

    if clean.get("year_built"):
        clean["year_of_construction"] = generation_for_year(clean["year_built"])

    return clean, errors




