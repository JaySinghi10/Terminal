"""IATA -> (latitude, longitude, ISO country), for the connection search.

    python tools/icao/geo.py            # writes airport_geo.py at the repo root

WHY IT EXISTS. The connection search prunes hubs by how far out of the way they
are (docs/connection-search.md §4) and classifies a connection as domestic or
international (§6). Both need an airport's position and country on the SERVER,
which until now knew only IATA -> ICAO.

WHY NOT THE PROVIDER. AeroDataBox's route list carries coordinates and country
codes, and §1 settles that anything taken from it is Contents under their terms,
capped at seven days. A table the server ships is a permanent cache. So this is
built from OurAirports, public domain, the same source as airport_icao.py and
the app's lib/airports.ts.

SCHEDULED-SERVICE AIRPORTS WITH AN IATA CODE. Where a code is claimed twice, the
larger airport wins (large > medium > small), and a tie is reported rather than
settled by file order.
"""
import csv
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RAW = os.path.join(HERE, "airports.csv")
OUT = os.path.join(ROOT, "airport_geo.py")

IATA_RE = re.compile(r"^[A-Z]{3}$")
SIZE = {"large_airport": 3, "medium_airport": 2, "small_airport": 1}

# The hubs and ends the tests and the first live search rely on.
MUST_RESOLVE = ["IDR", "COK", "BOM", "BLR", "HYD", "DEL", "MAA", "DXB", "LHR", "JFK", "SIN", "AMS", "SFO"]


def main():
    if not os.path.exists(RAW):
        sys.exit(f"{RAW} is missing; run tools/icao/run.py first, which fetches it.")
    rows = list(csv.DictReader(io.open(RAW, encoding="utf8", newline="")))
    best = {}
    ties = []
    for r in rows:
        code = (r.get("iata_code") or "").strip().upper()
        if not IATA_RE.match(code) or r.get("scheduled_service") != "yes":
            continue
        try:
            lat = round(float(r["latitude_deg"]), 4)
            lon = round(float(r["longitude_deg"]), 4)
        except (TypeError, ValueError):
            continue
        country = (r.get("iso_country") or "").strip().upper() or None
        size = SIZE.get(r.get("type"), 0)
        prev = best.get(code)
        if prev is None or size > prev[0]:
            best[code] = (size, lat, lon, country)
        elif size == prev[0]:
            ties.append(code)

    missing = [c for c in MUST_RESOLVE if c not in best]
    if missing:
        sys.exit(f"missing required airports: {missing}")

    lines = [
        '"""IATA -> (latitude, longitude, ISO country). GENERATED -- do not edit by hand.',
        "Regenerate with:  python tools/icao/geo.py",
        "Source: OurAirports (public domain), scheduled-service airports with an IATA code.",
        "Nothing here comes from AeroDataBox; see docs/connection-search.md section 1.",
        '"""',
        "AIRPORT_GEO = {",
    ]
    for code in sorted(best):
        _, lat, lon, country = best[code]
        lines.append(f"    {code!r}: ({lat}, {lon}, {country!r}),")
    lines.append("}")
    io.open(OUT, "w", encoding="utf8", newline="\n").write("\n".join(lines) + "\n")
    print(f"{len(best)} airports written to {OUT}; {len(set(ties))} same-size code clashes kept first-seen")


if __name__ == "__main__":
    main()
