from .formspec import YEAR_OPTIONS



VINTAGE_POINTS = {name: pts for name, pts in zip(YEAR_OPTIONS, [3, 2, 1, 0, 0, 0])}
WINDOW_POINTS = {"Single glazing": 2, "Double glazing": 1, "Triple glazing": 0, "Unknown": 1}


def envelope_score(a):
    score = VINTAGE_POINTS.get(a.get("year_of_construction"), 1)
    score += WINDOW_POINTS.get(a.get("window_type"), 1)
    score += 1 if a.get("insulation_type", "Unknown") == "Unknown" else 0
    score += 1 if a.get("door_drafts") == "Yes" else 0
    return score


def recommend_package(a):
    score = envelope_score(a)
    all_electric = (
        a.get("heating_fuel") == "Electricity"
        and a.get("cooling_system") in ("Heat pump", "Ductless mini-split", "None")
    )
    if score <= 1:
        return "No Upgrade Recommended" if all_electric else "Equipment Electrification"
    if score <= 3:
        return "Basic Envelope + Equipment Electrification"
    if score <= 5:
        return "Current Code Envelope + Equipment Electrification"
    return "Beyond Code Envelope + Equipment Electrification"
