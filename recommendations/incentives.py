INCENTIVES = []

def incentives_for(zone):
    return [
        p for p in INCENTIVES
        if p["zones"] == "all" or (zone and zone in p["zones"])
    ]