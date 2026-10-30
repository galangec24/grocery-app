"""Turns a device location into a real city and every supermarket and mall inside it.

Map data is from OpenStreetMap. Results are cached by rounded coordinates, so a
shopper's precise location is never stored.
"""
import re
import time

import httpx
from pymongo.database import Database

from . import comparison as cmp
from .db import utcnow

HEADERS = {"User-Agent": "GroceryPriceFinder/1.0 (+https://github.com/galangec24/grocery-app)"}
NOMINATIM = "https://nominatim.openstreetmap.org"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
ATTRIBUTION = "Map data © OpenStreetMap contributors"
CACHE_DAYS = 7
MAX_STORES = 80
VISAYAS = re.compile(r"visayas|negros", re.I)
MINDANAO = re.compile(r"mindanao|zamboanga|davao|soccsksargen|caraga|bangsamoro", re.I)


class LocationError(Exception):
    pass


def island_group(region: str) -> str:
    if VISAYAS.search(region):
        return "Visayas"
    return "Mindanao" if MINDANAO.search(region) else "Luzon"


def _place(data: dict) -> dict:
    address = data.get("address") or {}
    if address.get("country_code") != "ph":
        raise LocationError("Grocery Price Finder covers the Philippines only for now.")
    city = (
        address.get("city") or address.get("town") or address.get("municipality")
        or data.get("name") or address.get("county")
    )
    region = address.get("region") or address.get("state") or ""
    box = [float(v) for v in data["boundingbox"]]  # south, north, west, east
    return {
        "city": city, "region": region, "island": island_group(region),
        "metro_manila": "metro manila" in region.lower() or "national capital" in region.lower(),
        "box": box,
    }


def reverse_geocode(http: httpx.Client, latitude: float, longitude: float) -> dict:
    response = http.get(f"{NOMINATIM}/reverse", params={
        "format": "jsonv2", "lat": latitude, "lon": longitude, "zoom": 10, "addressdetails": 1,
    })
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise LocationError("We couldn't find a city at that location.")
    return _place(data)


def find_city(http: httpx.Client, name: str) -> tuple[dict, float, float]:
    response = http.get(f"{NOMINATIM}/search", params={
        "format": "jsonv2", "q": name, "countrycodes": "ph", "addressdetails": 1, "limit": 1,
    })
    response.raise_for_status()
    results = response.json()
    if not results:
        raise LocationError(f"We couldn't find “{name}” in the Philippines.")
    return _place(results[0]), float(results[0]["lat"]), float(results[0]["lon"])


def _from_overpass(http: httpx.Client, box: list[float]) -> list[dict] | None:
    south, north, west, east = box
    query = (
        f'[out:json][timeout:12];nwr["shop"~"^(supermarket|mall)$"]({south},{west},{north},{east});'
        "out center tags;"
    )
    for mirror in OVERPASS:
        try:
            response = http.post(mirror, data={"data": query}, timeout=httpx.Timeout(14, connect=5))
            response.raise_for_status()
            elements = response.json().get("elements", [])
        except (httpx.HTTPError, ValueError):
            continue
        stores = []
        for element in elements:
            tags = element.get("tags", {})
            stores.append({
                "name": tags.get("name") or tags.get("brand"),
                "type": "Mall" if tags.get("shop") == "mall" else "Supermarket",
                "latitude": element.get("lat") or element.get("center", {}).get("lat"),
                "longitude": element.get("lon") or element.get("center", {}).get("lon"),
            })
        return stores
    return None


def _from_nominatim(http: httpx.Client, box: list[float]) -> list[dict]:
    """Backup when Overpass is overloaded. Finds fewer stores, but they are just as real."""
    south, north, west, east = box
    stores = []
    for kind in ("supermarket", "mall"):
        time.sleep(1.1)  # Nominatim's usage policy allows one request per second.
        try:
            response = http.get(f"{NOMINATIM}/search", params={
                "q": kind, "format": "jsonv2", "limit": 40, "countrycodes": "ph", "bounded": 1,
                "viewbox": f"{west},{north},{east},{south}",
            })
            response.raise_for_status()
            results = response.json()
        except (httpx.HTTPError, ValueError):
            continue
        for result in results:
            if result.get("category") == "shop" and result.get("type") in ("supermarket", "mall"):
                stores.append({
                    "name": result.get("name"),
                    "type": "Mall" if result["type"] == "mall" else "Supermarket",
                    "latitude": float(result["lat"]), "longitude": float(result["lon"]),
                })
    return stores


def stores_in_box(http: httpx.Client, box: list[float]) -> list[dict]:
    found = _from_overpass(http, box)
    if not found:
        found = _from_nominatim(http, box)
    stores: dict[str, dict] = {}
    for store in found:
        if store["name"] and store["latitude"] is not None and store["longitude"] is not None:
            stores[f"{store['name']}|{store['latitude']:.3f}|{store['longitude']:.3f}"] = store
    return list(stores.values())


def _cached(db: Database, key: str, build) -> dict:
    cached = db.location_cache.find_one({"_id": key})
    if cached and (utcnow() - cached["cached_at"]).days < CACHE_DAYS:
        return cached["value"]
    value = build()
    if value["stores"]:  # An empty list may be a map outage, so ask again next time.
        db.location_cache.replace_one({"_id": key}, {"_id": key, "value": value, "cached_at": utcnow()}, upsert=True)
    return value


def resolve(db: Database, latitude: float | None, longitude: float | None, city: str | None) -> dict:
    with httpx.Client(headers=HEADERS, timeout=httpx.Timeout(30, connect=10)) as http:
        try:
            if city:
                key = f"city:{city.strip().lower()}"
                def build():
                    place, lat, lon = find_city(http, city)
                    return {**place, "latitude": lat, "longitude": lon, "stores": stores_in_box(http, place["box"])}
                value = _cached(db, key, build)
                latitude, longitude = value["latitude"], value["longitude"]
            else:
                key = f"geo:{latitude:.2f}:{longitude:.2f}"
                def build():
                    place = reverse_geocode(http, latitude, longitude)
                    return {**place, "stores": stores_in_box(http, place["box"])}
                value = _cached(db, key, build)
        except httpx.HTTPError:
            raise LocationError("The location service didn't respond. Please try again.")

    stores = [
        {**s, "distance_km": round(cmp.haversine_km(latitude, longitude, s["latitude"], s["longitude"]), 2)}
        for s in value["stores"]
    ]
    stores.sort(key=lambda s: s["distance_km"])
    return {
        "city": value["city"], "region": value["region"], "island": value["island"],
        "metro_manila": value["metro_manila"], "store_count": len(stores), "stores": stores[:MAX_STORES],
        "stores_available": bool(stores),
        "attribution": ATTRIBUTION,
    }
