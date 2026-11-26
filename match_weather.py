import re
import shutil
import sys
from pathlib import Path

from idftool import load_config
from weather_idf import load_stations, nearest_station



def site_location(idf_path):
    text = Path(idf_path).read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"!.*", "", text)
    for obj in text.split(";"):
        fields = [f.strip() for f in obj.split(",")]
        if fields[0].upper() == "SITE:LOCATION":
            if len(fields) < 4:
                sys.exit(f"{idf_path}: Site:Location has no latitude/longitude")
            try:
                return fields[1], float(fields[2]), float(fields[3])
            except ValueError:
                sys.exit(f"{idf_path}: Site:Location latitude/longitude are not numbers: {fields[2:4]}")
    return None


def next_numbered_folder(parent, prefix):
    """parent/<prefix>N for the first N above every existing one (test1, test2, ...)."""
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    used = [int(m.group(1)) for p in parent.glob(f"{prefix}*") if p.is_dir() and (m := pattern.match(p.name))]
    return parent / f"{prefix}{max(used, default=0) + 1}"


def match_weather(idf_file):
    idf_path = Path(idf_file)
    if not idf_path.is_file():
        sys.exit(f"{idf_path} not found")
    config = load_config()
    paths = config["paths"]

    location = site_location(idf_path)
    if location is None:
        sys.exit(f"{idf_path.name}: no Site:Location in the IDF, so it can't be matched to weather")
    site_name, lat, lon = location

    stations = load_stations(paths["stations"])
    station, km = nearest_station(lat, lon, stations)
    epw = paths["weather"] / station["epw"]

    print(f"IDF:          {idf_path.name}")
    print(f"House:        {site_name} ({lat}, {lon})")
    print(f"Station:      {station['station']}, {station['province']} (WMO {station['wmo']})")
    print(f"Distance:     {km:.1f} km")
    print(f"Weather file: {epw}")
    if km > config["far_station_km"]:
        print(f"Warning: nearest station is more than {config['far_station_km']} km away")
    if not epw.exists():
        sys.exit("That weather file is listed in stations.csv but is not in the weather folder, so nothing was copied.")

    # Put the IDF and its weather file side by side in the next numbered folder: downloads/test1, test2, ...
    folder = next_numbered_folder(paths["downloads"], config["download_prefix"])
    folder.mkdir(parents=True)
    shutil.copy2(idf_path, folder / idf_path.name)
    shutil.copy2(epw, folder / epw.name)
    print(f"Copied both files to {folder}")


if __name__ == "__main__":
    idf_files = Path(sys.argv[1])
    for idf_file in idf_files:
        match_weather(idf_file)
