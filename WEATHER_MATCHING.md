# How each IDF is matched to its weather file

Every house model (IDF) needs one weather file (EPW) to be simulated in EnergyPlus. The choice is
automatic: you give `match_weather.py` an IDF, and it picks the weather file from the station
nearest to the house. There is no manual lookup. The same IDF always gets the same weather file.

## Running it

```bash
python3 match_weather.py "C:\path\to\your_house.idf"
```

Or run `python3 match_weather.py` with no file and paste the path when it asks. (On Windows, a
file window opens instead.) Paths copied from Explorer, quotes included, work in both Windows and
WSL; under WSL, `C:\...` is converted to `/mnt/c/...`.

It prints the match:

```
IDF:          house.idf
House:        Toronto House (43.67, -79.63)
Station:      Toronto-Pearson.Intl.AP, ON (WMO 716240)
Distance:     1.1 km
Weather file: .../weather/baseline/CAN_ON_Toronto-Pearson.Intl.AP.716240_CWEC2020.epw
Copied both files to .../downloads/test1
```

Then it copies the IDF and its weather file together into the next numbered folder:
`downloads/test1`, `test2`, and so on. The originals are not moved or changed.

## How the weather file is chosen

1. **Read the house location from the IDF.** The latitude and longitude come from the first
   `Site:Location` object in the IDF.

2. **Load the candidate stations.** The station list is `weather/baseline/stations.csv`. It has one
   row per CWEC2020 weather station, with its name, province, WMO number, latitude, longitude and
   EPW file name. Only rows with status `ok` and an EPW file name are candidates (564 stations at
   the time of writing).

3. **Measure the distance from the house to every station.** This is the great-circle distance:
   the shortest path over the Earth's surface, calculated with the haversine formula.

   ```
   d = 2R · asin( √( sin²(Δφ/2) + cos φ₁ · cos φ₂ · sin²(Δλ/2) ) )
   ```

   φ₁ and φ₂ are the latitudes of the house and the station, Δφ and Δλ are the differences in
   latitude and longitude (all in radians), and R = 6371 km is the Earth's mean radius.

4. **Pick the closest station.** The station with the smallest distance is chosen, and its EPW file
   is taken from `weather/baseline`. If two stations were exactly the same distance away, the one
   listed first in `stations.csv` would win.

5. **Check the distance.** If the chosen station is more than 50 km away (`far_station_km`), the
   script prints a warning. The match is still kept, because it is the closest weather data
   available, but it may not represent the house's climate well.

6. **Check the file exists.** If the EPW named in `stations.csv` is missing from the weather
   folder, the script stops and copies nothing.
