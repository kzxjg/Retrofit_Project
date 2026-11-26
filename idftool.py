import argparse
import csv
import glob
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tomllib
from itertools import combinations
from pathlib import Path

from weather_idf import load_stations, match_weather

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "idftool.toml"


TO_KWH = {"GJ": 277.7778, "MJ": 0.2777778, "kWh": 1.0, "kBtu": 0.2930711}


PATH_KEYS = ["input_idf", "output_idf", "baseline_runs", "baseline_results", "weather", "downloads"]


def load_config(path=DEFAULT_CONFIG):
    path = Path(path).resolve()
    if not path.exists():
        sys.exit(f"Config file {path} not found.")
    with open(path, "rb") as fh:
        try:
            cfg = tomllib.load(fh)
        except tomllib.TOMLDecodeError as e:
            sys.exit(f"{path}: {e}")

    def need(section, key):
        try:
            return cfg[section][key]
        except KeyError:
            sys.exit(f"{path}: missing [{section}] {key}")

    paths = {key: path.parent / need("paths", key) for key in PATH_KEYS}
    paths["stations"] = paths["weather"] / need("paths", "stations_file")

    far_km = need("weather", "far_station_km")
    if not isinstance(far_km, (int, float)) or far_km <= 0:
        sys.exit(f"{path}: [weather] far_station_km must be a positive number")

    retrofits = cfg.get("retrofits", [])
    keys = [m.get("key") for m in retrofits]
    for m in retrofits:
        if not m.get("key") or not m.get("object") or not m.get("fields"):
            sys.exit(f"{path}: every [[retrofits]] needs key, object and fields ({m})")
    if len(set(keys)) != len(keys):
        sys.exit(f"{path}: retrofit keys must be unique ({keys})")

    return {
        "paths": paths,
        "download_prefix": cfg["paths"].get("download_prefix", "test"),
        "far_station_km": far_km,
        "energyplus_dir": cfg.get("energyplus", {}).get("dir", ""),
        "energyplus_search": cfg.get("energyplus", {}).get("search", []),
        "retrofits": retrofits,
    }


#energy plus reading functions 

def energyplus_dir(config=None):
    config = config or load_config()
    path = os.environ.get("ENERGYPLUS_DIR", "").strip() or config["energyplus_dir"].strip()
    if path:
        path = Path(path)
        if not (path / "Energy+.idd").exists():
            sys.exit(f"No Energy+.idd in {path}; is that the EnergyPlus install folder?")
        return path
    found = [Path(p) for pattern in config["energyplus_search"] for p in glob.glob(pattern)
             if (Path(p) / "Energy+.idd").exists()]
    
    found.sort(key=lambda p: [int(n) for n in re.findall(r"\d+", p.name)])
    if not found:
        sys.exit("EnergyPlus not found. Install it (https://energyplus.net/downloads), or set [energyplus] dir "
                 "in idftool.toml or ENERGYPLUS_DIR to its folder.")
    return found[-1]


def energyplus_exe(folder):
    for name in ("energyplus.exe", "energyplus"):
        if (folder / name).exists():
            return folder / name
    sys.exit(f"No energyplus executable in {folder}")


def load_eppy(folder):
    from eppy.modeleditor import IDF
    IDF.setiddname(str(folder / "Energy+.idd"))
    return IDF


#simulation functions that run energy plus and read the results

def add_sql_output(idf):
    sqlite_objs = idf.idfobjects["OUTPUT:SQLITE"]
    if sqlite_objs:
        sqlite_objs[0].Option_Type = "SimpleAndTabular"
    else:
        idf.newidfobject("OUTPUT:SQLITE", Option_Type="SimpleAndTabular")

    reports = idf.idfobjects["OUTPUT:TABLE:SUMMARYREPORTS"]
    if not reports:
        idf.newidfobject("OUTPUT:TABLE:SUMMARYREPORTS", Report_1_Name="AllSummary")
    elif not any(str(v) in ("AllSummary", "AnnualBuildingUtilityPerformanceSummary")
                 for v in reports[0].fieldvalues):
        reports[0].Report_1_Name = "AllSummary"  


def run_energyplus(exe, idf_path, epw_path, out_dir):
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    proc = subprocess.run(
        [str(exe), "-w", str(epw_path), "-d", str(out_dir), "-x", str(idf_path)],
        capture_output=True, text=True,
    )
    end = out_dir / "eplusout.end"
    if proc.returncode != 0 or not end.exists() or "Completed Successfully" not in end.read_text(errors="replace"):
        return f"EnergyPlus failed, see {out_dir / 'eplusout.err'}"
    if not (out_dir / "eplusout.sql").exists():
        return "EnergyPlus finished but wrote no eplusout.sql"
    return None


def annual_energy(sql_path):

    con = sqlite3.connect(sql_path)
    try:
        rows = con.execute(
            "SELECT RowName, Units, Value FROM TabularDataWithStrings "
            "WHERE ReportName = 'AnnualBuildingUtilityPerformanceSummary' AND TableName = 'End Uses' "
            "AND ReportForString = 'Entire Facility' "
            "AND RowName IN ('Heating', 'Cooling', 'Total End Uses')"
        ).fetchall()
    finally:
        con.close()
    totals = {"Heating": 0.0, "Cooling": 0.0, "Total End Uses": 0.0}
    for row_name, units, value in rows:
        factor = TO_KWH.get((units or "").strip())
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if factor is not None:
            totals[row_name.strip()] += number * factor
    return {
        "heating_kwh": round(totals["Heating"]),
        "cooling_kwh": round(totals["Cooling"]),
        "total_kwh": round(totals["Total End Uses"]),
    }


RESULT_FIELDS = ["idf", "site_name", "house_latitude", "house_longitude", "station", "province", "wmo",
                 "distance_km", "epw", "heating_kwh", "cooling_kwh", "total_kwh", "status"]


def input_idfs(paths):
    idf_paths = sorted(paths["input_idf"].glob("*.idf"))
    if not idf_paths:
        sys.exit(f"No .idf files in {paths['input_idf']}")
    return idf_paths


def baseline(config):
    paths = config["paths"]
    ep_dir = energyplus_dir(config)
    exe = energyplus_exe(ep_dir)
    IDF = load_eppy(ep_dir)
    stations = load_stations(paths["stations"])

    results = []
    for idf_path in input_idfs(paths):
        row = dict.fromkeys(RESULT_FIELDS, "")
        row["idf"] = idf_path.name
        idf = IDF(str(idf_path))
        match = match_weather(idf, stations, paths["weather"], config["far_station_km"])
        if match is None:
            row["status"] = "no Site:Location in IDF"
            results.append(row)
            print(f"{idf_path.name}: skipped, no Site:Location")
            continue

        station = match.station
        row.update(site_name=match.site_name, house_latitude=match.latitude, house_longitude=match.longitude,
                   station=station["station"], province=station["province"], wmo=station["wmo"],
                   distance_km=round(match.distance_km, 1), epw=station["epw"])

        out_dir = paths["baseline_runs"] / idf_path.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        model = out_dir.parent / f"{idf_path.stem}.sim.idf"
        add_sql_output(idf)
        idf.saveas(str(model))

        error = run_energyplus(exe, model, match.epw_path, out_dir)
        if error:
            row["status"] = error
        else:
            row.update(annual_energy(out_dir / "eplusout.sql"))
            row["status"] = (f"ok, but nearest station is {match.distance_km:.0f} km away"
                             if match.is_far else "ok")
        results.append(row)
        print(f"{idf_path.name}: {station['station']} ({match.distance_km:.1f} km) -> {row['status']}")

    paths["baseline_results"].parent.mkdir(parents=True, exist_ok=True)
    with open(paths["baseline_results"], "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(results)
    print(f"Wrote {paths['baseline_results']}")


#retroit functions

def apply_retrofit(idf, measure):
    object_type = measure["object"].upper()
    try:
        objects = idf.idfobjects[object_type]
    except KeyError:
        sys.exit(f"Retrofit {measure['key']}: {object_type} is not an EnergyPlus object type")
    if "name" in measure:
        objects = [obj for obj in objects if obj.Name == measure["name"]]
    for obj in objects:
        for field, value in measure["fields"].items():
            setattr(obj, field, value)
    return len(objects)


def generate_retrofits(config):
    paths, measures = config["paths"], config["retrofits"]
    if not measures:
        sys.exit("No [[retrofits]] in the config.")
    IDF = load_eppy(energyplus_dir(config))
    paths["output_idf"].mkdir(parents=True, exist_ok=True)
    for idf_path in input_idfs(paths):
        warned = set()
        for n in range(1, len(measures) + 1):
            for combo in combinations(measures, n):
                idf = IDF(str(idf_path))
                for measure in combo:
                    if apply_retrofit(idf, measure) == 0 and measure["key"] not in warned:
                        warned.add(measure["key"])
                        target = f"{measure['object']} {measure.get('name', '')}".strip()
                        print(f"  warning: {idf_path.name} has no {target}; {measure['key']} changes nothing")
                out_name = f"{idf_path.stem}_{'_'.join(m['key'] for m in combo)}.idf"
                idf.saveas(str(paths["output_idf"] / out_name))
                print(f"Saved {out_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["baseline", "retrofits"])
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"settings file (default {DEFAULT_CONFIG.name})")
    args = parser.parse_args()
    config = load_config(args.config)
    baseline(config) if args.command == "baseline" else generate_retrofits(config)
