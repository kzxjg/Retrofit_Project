"""Draws the climate zones on the Canada map. Writes frontend/src/zoneAreas.ts.

Run it from the Retrofit folder:

    pip install shapely pyproj
    python tools/make_zone_areas.py                          # approximate areas (see below)
    python tools/make_zone_areas.py --hot2000 zones.geojson  # real areas from NRCan's HOT2000 map

APPROXIMATE areas: each point of Canada is given the zone of the nearest city that the
zone lists in recommendations/formspec.py. This is an illustration, not a boundary.

REAL areas: the HOT2000 climate map holds many small areas, each with an annual HDD18
value. Each area goes into the zone whose range contains its value, and the areas of one
zone are joined together. Save the map as GeoJSON in latitude/longitude (EPSG:4326).

The zone ranges and the city lists come from recommendations/formspec.py, so change them there.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

import shapely
from pyproj import Transformer
from shapely.geometry import MultiPoint, MultiPolygon, Point, shape
from shapely.ops import transform, unary_union

sys.path.insert(0, os.getcwd())
from recommendations.formspec import ZONES, zone_for_hdd  # noqa: E402

# Pinned to the commit of release v5.1.2 so the input cannot change under us (a branch like
# "master" can). To update, pick a newer release's commit hash on GitHub.
NE_COMMIT = "f1890d9f152c896d250a77557a5751a93d494776"
NE_URL = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{NE_COMMIT}/geojson/ne_50m_admin_1_states_provinces.geojson"
NE_FILE = "tools/ne_provinces.geojson"
OUT_FILE = "frontend/src/zoneAreas.ts"


PROJECTION = "+proj=lcc +lat_1=49 +lat_2=77 +lat_0=63.390675 +lon_0=-91.86666666666666 +x_0=0 +y_0=0 +datum=WGS84 +units=m"
MINX, MAXY, SCALE = -2507878.7372606685, 2240812.6665194216, 0.00014282775076970305
VIEW_W, VIEW_H = 760, 654


CITY_COORDS = {
    "Vancouver": (49.2827, -123.1207), "Victoria": (48.4284, -123.3656),
    "Abbotsford": (49.0504, -122.3045), "Nanaimo": (49.1659, -123.9401),
    "Chilliwack": (49.1579, -121.9515), "Toronto": (43.6532, -79.3832),
    "Kelowna": (49.8880, -119.4960), "Windsor": (42.3149, -83.0364),
    "London": (42.9849, -81.2453), "Hamilton": (43.2557, -79.8711),
    "Kingston": (44.2312, -76.4860), "Ottawa": (45.4215, -75.6972),
    "Montreal": (45.5017, -73.5673), "Halifax": (44.6488, -63.5752),
    "Fredericton": (45.9636, -66.6431), "St. John's": (47.5615, -52.7126),
    "Québec City": (46.8139, -71.2080), "Calgary": (51.0447, -114.0719),
    "Edmonton": (53.5461, -113.4938), "Winnipeg": (49.8951, -97.1384),
    "Saskatoon": (52.1332, -106.6700), "Regina": (50.4452, -104.6189),
    "Thunder Bay": (48.3809, -89.2477), "Fort McMurray": (56.7265, -111.3790),
    "Yellowknife": (62.4540, -114.3718), "Iqaluit": (63.7467, -68.5170),
    "Whitehorse": (60.7212, -135.0568),
}

TO_XY = Transformer.from_crs("EPSG:4326", PROJECTION, always_xy=True)


def project(geom):
    return transform(lambda x, y, z=None: TO_XY.transform(x, y), geom)


def load_provinces():
    if not os.path.exists(NE_FILE):
        print("Downloading the province outlines (Natural Earth, public domain)...")
        # Download to a temporary name first so a failed download never leaves a half-written file.
        urllib.request.urlretrieve(NE_URL, NE_FILE + ".part")
        os.replace(NE_FILE + ".part", NE_FILE)
    with open(NE_FILE) as f:
        data = json.load(f)
    provinces = {}
    for f in data["features"]:
        if f["properties"].get("iso_a2") != "CA":
            continue
        g = project(shape(f["geometry"]))
        polys = list(g.geoms) if isinstance(g, MultiPolygon) else [g]
        polys = [p for p in polys if p.area > 3000e6]  # leave out tiny islands
        g = MultiPolygon(polys) if len(polys) > 1 else polys[0]
        provinces[f["properties"]["postal"]] = g.simplify(4000, preserve_topology=True)
    return provinces


def approximate_areas(land):
    points, point_zone = [], []
    for zone in ZONES:
        for name in (c.strip() for c in zone["cities"].split(",")):
            if name in CITY_COORDS:
                lat, lon = CITY_COORDS[name]
                points.append(Point(TO_XY.transform(lon, lat)))
                point_zone.append(zone["id"])
    cells = shapely.voronoi_polygons(MultiPoint(points), extend_to=land.buffer(2_000_000).envelope)
    by_zone = {}
    for cell in cells.geoms:
        for point, zone_id in zip(points, point_zone):
            if cell.contains(point):
                by_zone.setdefault(zone_id, []).append(cell)
    return {zone_id: unary_union(cells_).intersection(land) for zone_id, cells_ in by_zone.items()}


def real_areas(path, land, hdd_field):
    with open(path) as f:
        data = json.load(f)
    features = data["features"]
    if hdd_field is None:
        names = list(features[0]["properties"])
        found = [n for n in names if re.search(r"hdd|degree", n, re.I)]
        if not found:
            sys.exit("Could not find the heating degree-day field. The fields are: "
                     + ", ".join(names) + "\nRun again with --hdd-field NAME")
        hdd_field = found[0]
        print(f"Using the field {hdd_field!r} for annual heating degree days.")
    by_zone = {}
    for f in features:
        value = f["properties"].get(hdd_field)
        if value is None:
            continue
        by_zone.setdefault(zone_for_hdd(float(value))["id"], []).append(project(shape(f["geometry"])).buffer(0))
    return {zone_id: unary_union(parts).intersection(land) for zone_id, parts in by_zone.items()}


def ring(coords):
    pts = [(round((x - MINX) * SCALE, 1), round((MAXY - y) * SCALE, 1)) for x, y in coords]
    return "M" + "L".join(f"{x} {y}" for x, y in pts[:-1]) + "Z"


def to_path(geom):
    polys = [p for p in (geom.geoms if hasattr(geom, "geoms") else [geom]) if p.geom_type == "Polygon" and p.area > 2000e6]
    d = "".join(ring(p.exterior.coords) + "".join(ring(i.coords) for i in p.interiors) for p in polys)
    biggest = max(polys, key=lambda p: p.area)
    x, y = biggest.representative_point().coords[0]
    return d, round((x - MINX) * SCALE, 1), round((MAXY - y) * SCALE, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hot2000", help="GeoJSON of the NRCan HOT2000 climate map (latitude/longitude)")
    parser.add_argument("--hdd-field", help="name of the annual heating degree-day field")
    args = parser.parse_args()

    provinces = load_provinces()
    land = unary_union(list(provinces.values()))
    if args.hot2000:
        areas = real_areas(args.hot2000, land, args.hdd_field)
        source = "real"
        note = "Zone areas: NRCan HOT2000 climate map (Open Government Licence - Canada), grouped by zone."
    else:
        areas = approximate_areas(land)
        source = "approximate"
        note = "Zone areas are approximate: they follow the nearest listed city. Use the list to choose your zone."

    lines = []
    for zone in ZONES:
        geom = areas.get(zone["id"])
        if geom is None or geom.is_empty:
            print(f"No area found for {zone['id']}; it will not be drawn.")
            continue
        geom = geom.simplify(5000, preserve_topology=True)
        d, lx, ly = to_path(geom)
        label = zone["name"].replace("Zone ", "")
        lines.append(f'  {{ id: {json.dumps(zone["id"])}, label: {json.dumps(label)}, lx: {lx}, ly: {ly},\n    d: {json.dumps(d)} }},')
        print(f"{zone['id']:7} {geom.area / 1e6:12,.0f} km2")

    with open(OUT_FILE, "w", encoding="utf-8") as out:
        out.write(HEADER)
        out.write(f"export const ZONE_AREAS_SOURCE: 'approximate' | 'real' = {json.dumps(source)}\n")
        out.write(f"export const ZONE_AREAS_NOTE = {json.dumps(note, ensure_ascii=False)}\n\n")
        out.write("export const ZONE_AREAS: ZoneArea[] = [\n" + "\n".join(lines) + "\n]\n")
    print(f"Wrote {OUT_FILE}")


HEADER = """\
// Written by tools/make_zone_areas.py. Do not edit by hand: run the script again.
// The areas are drawn in the same 760 x 654 frame as the provinces in provinceData.ts.

export type ZoneArea = {
  id: string // matches the zone id in recommendations/formspec.py, e.g. "zone7a"
  label: string
  d: string // SVG path
  lx: number // label position
  ly: number
}

"""


if __name__ == "__main__":
    main()
