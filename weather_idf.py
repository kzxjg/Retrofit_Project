import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

EARTH_RADIUS_KM = 6371.0


@dataclass
class WeatherMatch:
    site_name: str
    latitude: float
    longitude: float
    station: dict      
    distance_km: float
    epw_path: Path
    is_far: bool      


def load_stations(path):
    path = Path(path)
    if not path.exists():
        sys.exit(f"{path} not found; download the weather files first.")
    with open(path, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["status"] == "ok" and r["epw"]]
    if not rows:
        sys.exit(f"{path} has no usable stations (status ok with an epw file).")
    for r in rows:
        r["latitude"], r["longitude"] = float(r["latitude"]), float(r["longitude"])
    return rows


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest_station(lat, lon, stations):
    station = min(stations, key=lambda s: distance_km(lat, lon, s["latitude"], s["longitude"]))
    return station, distance_km(lat, lon, station["latitude"], station["longitude"])


def house_location(idf):
    sites = idf.idfobjects["SITE:LOCATION"]
    if not sites:
        return None
    site = sites[0]
    return site.Name, float(site.Latitude), float(site.Longitude)


def match_weather(idf, stations, weather_dir, far_station_km):
    location = house_location(idf)
    if location is None:
        return None
    site_name, lat, lon = location
    station, km = nearest_station(lat, lon, stations)
    return WeatherMatch(site_name=site_name, latitude=lat, longitude=lon, station=station,
                        distance_km=km, epw_path=Path(weather_dir) / station["epw"],
                        is_far=km > far_station_km)
