"""Tests for tools/make_zone_areas.py, the script that writes frontend/src/zoneAreas.ts.

They use small made-up maps instead of the Natural Earth download, so they need no
network. They are skipped when the tool's own packages (requirements-tools.txt) are not
installed, since the web app does not need them.
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import pyproj  # noqa: F401
    import shapely  # noqa: F401
except ImportError:  # pragma: no cover - depends on what is installed
    make_zone_areas = None
else:
    from tools import make_zone_areas

from recommendations.formspec import ZONES

REPO = Path(__file__).resolve().parent.parent


def box(west, south, east, north):
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


def feature(geometry, **properties):
    return {"type": "Feature", "properties": properties, "geometry": geometry}


# Most of Canada as one rectangle that stays inside the map frame, plus a US one the
# script must leave out.
WEST, SOUTH, EAST, NORTH = -130, 45, -60, 70
CANADA = box(WEST, SOUTH, EAST, NORTH)
PROVINCES = {"type": "FeatureCollection", "features": [
    feature(CANADA, iso_a2="CA", postal="XX"),
    feature(box(-125, 30, -70, 41), iso_a2="US", postal="ZZ"),
]}


def hot2000_map(field="HDD18"):
    """One strip of Canada per zone, west to east, each with a heating degree-day value inside that zone's range."""
    width = (EAST - WEST) / len(ZONES)
    features = []
    for i, zone in enumerate(ZONES):
        west = WEST + i * width
        features.append(feature(box(west, SOUTH, west + width, NORTH), **{field: zone["hdd_min"] + 1}))
    features.append(feature(box(-100, 50, -99, 51), **{field: None}))  # no value: ignored
    return {"type": "FeatureCollection", "features": features}


def read_areas(path):
    """The id, label, label position and path of every zone area in a written zoneAreas.ts."""
    text = Path(path).read_text(encoding="utf-8")
    entries = re.findall(
        r'\{ id: ("[^"]+"), label: ("[^"]+"), lx: ([-\d.]+), ly: ([-\d.]+),\n    d: ("[^"]*") \},', text)
    source = re.search(r"ZONE_AREAS_SOURCE: 'approximate' \| 'real' = (\"\w+\")", text)
    return text, json.loads(source.group(1)) if source else None, [
        {"id": json.loads(i), "label": json.loads(label), "lx": float(lx), "ly": float(ly), "d": json.loads(d)}
        for i, label, lx, ly, d in entries
    ]


@unittest.skipIf(make_zone_areas is None, "pip install -r requirements-tools.txt to test the map tool")
class MakeZoneAreasTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.ne_file = os.path.join(self.dir.name, "provinces.geojson")
        self.out_file = os.path.join(self.dir.name, "zoneAreas.ts")
        Path(self.ne_file).write_text(json.dumps(PROVINCES))
        for name, value in (("NE_FILE", self.ne_file), ("OUT_FILE", self.out_file)):
            patcher = mock.patch.object(make_zone_areas, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # The outlines are already "downloaded"; the tests must never reach the network.
        no_network = mock.patch.object(make_zone_areas.urllib.request, "urlretrieve",
                                       side_effect=AssertionError("tried to download"))
        no_network.start()
        self.addCleanup(no_network.stop)

    def run_tool(self, *args):
        with mock.patch.object(sys, "argv", ["make_zone_areas.py", *args]), \
                mock.patch("builtins.print"):
            make_zone_areas.main()
        return read_areas(self.out_file)

    def assert_valid_areas(self, areas):
        ids = [zone["id"] for zone in ZONES]
        self.assertEqual([a["id"] for a in areas], [z for z in ids if z in {a["id"] for a in areas}],
                         "areas are written in the zone order of formspec.py")
        for area in areas:
            self.assertTrue(re.fullmatch(r"(M[-\d. L]+Z)+", area["d"]), area["id"])
            self.assertTrue(0 <= area["lx"] <= make_zone_areas.VIEW_W and 0 <= area["ly"] <= make_zone_areas.VIEW_H,
                            f"label of {area['id']} is outside the map")
            zone = next(z for z in ZONES if z["id"] == area["id"])
            self.assertEqual(area["label"], zone["name"].replace("Zone ", ""))

    def test_approximate_areas_are_written_for_every_zone_with_a_known_city(self):
        text, source, areas = self.run_tool()
        self.assertEqual(source, "approximate")
        self.assertIn("approximate", text.split("ZONE_AREAS_NOTE = ")[1].split("\n")[0])
        with_cities = [z["id"] for z in ZONES
                       if any(c.strip() in make_zone_areas.CITY_COORDS for c in z["cities"].split(","))]
        self.assertEqual([a["id"] for a in areas], with_cities)
        self.assert_valid_areas(areas)

    def test_real_areas_follow_the_heating_degree_days(self):
        hot2000 = os.path.join(self.dir.name, "hot2000.geojson")
        Path(hot2000).write_text(json.dumps(hot2000_map()))
        _, source, areas = self.run_tool("--hot2000", hot2000)
        self.assertEqual(source, "real")
        self.assertEqual([a["id"] for a in areas], [z["id"] for z in ZONES])
        self.assert_valid_areas(areas)
        # The strips run west to east in zone order, so the labels must too.
        xs = [a["lx"] for a in areas]
        self.assertEqual(xs, sorted(xs))

    def test_the_degree_day_field_can_be_named(self):
        hot2000 = os.path.join(self.dir.name, "hot2000.geojson")
        Path(hot2000).write_text(json.dumps(hot2000_map(field="ANNUAL")))
        with self.assertRaises(SystemExit) as stopped, mock.patch("builtins.print"), \
                mock.patch.object(sys, "argv", ["make_zone_areas.py", "--hot2000", hot2000]):
            make_zone_areas.main()
        self.assertIn("--hdd-field", str(stopped.exception))
        self.assertFalse(os.path.exists(self.out_file), "nothing is written when the field is not found")

        _, _, areas = self.run_tool("--hot2000", hot2000, "--hdd-field", "ANNUAL")
        self.assertEqual(len(areas), len(ZONES))

    def test_the_file_it_writes_has_the_shape_the_page_imports(self):
        text, _, _ = self.run_tool()
        committed = (REPO / "frontend/src/zoneAreas.ts").read_text(encoding="utf-8")
        header = committed.split("export const ZONE_AREAS_SOURCE")[0]
        self.assertTrue(text.startswith(header), "the type and comments must match what the page imports")
        for name in ("ZONE_AREAS_SOURCE", "ZONE_AREAS_NOTE", "ZONE_AREAS"):
            self.assertIn(f"export const {name}", text)
        self.assertTrue(text.endswith("\n]\n"))

    def test_the_committed_map_lists_only_real_zones(self):
        _, source, areas = read_areas(REPO / "frontend/src/zoneAreas.ts")
        self.assertIn(source, ("approximate", "real"))
        self.assertTrue(areas)
        self.assertTrue({a["id"] for a in areas} <= {z["id"] for z in ZONES})
        self.assert_valid_areas(areas)
