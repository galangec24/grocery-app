"""Location rules, with OpenStreetMap replaced by recorded responses."""
import pytest

from app import location


CEBU = {
    "name": "Cebu City", "lat": "10.29", "lon": "123.90", "boundingbox": ["10.2463", "10.4962", "123.7595", "123.9302"],
    "address": {"city": "Cebu City", "region": "Central Visayas", "country_code": "ph"},
}
STORES = {"elements": [
    {"type": "node", "lat": 10.32, "lon": 123.90, "tags": {"name": "Near Mart", "shop": "supermarket"}},
    {"type": "way", "center": {"lat": 10.40, "lon": 123.90}, "tags": {"name": "Far Mall", "shop": "mall"}},
    {"type": "node", "lat": 10.33, "lon": 123.91, "tags": {"shop": "supermarket"}},
    {"type": "node", "lat": 10.32, "lon": 123.90, "tags": {"name": "Near Mart", "shop": "supermarket"}},
]}


class Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


@pytest.fixture()
def osm(monkeypatch):
    calls = {"reverse": 0, "stores": 0, "overpass_down": False, "backup": {}}
    monkeypatch.setattr(location.time, "sleep", lambda _: None)

    class Http:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            calls["reverse"] += 1
            if url.endswith("/search") and params.get("q") in ("supermarket", "mall"):
                return Response(calls["backup"].get(params["q"], []))
            return Response([CEBU] if url.endswith("/search") else CEBU)

        def post(self, url, data=None, timeout=None):
            calls["stores"] += 1
            calls["query"] = data["data"]
            if calls["overpass_down"]:
                raise location.httpx.ConnectTimeout("down")
            return Response(STORES)

    monkeypatch.setattr(location.httpx, "Client", Http)
    return calls


GEO = {"latitude": 10.3157, "longitude": 123.8854}


def test_true_location_finds_city_and_all_its_stores(client, osm):
    data = client.get("/api/v1/location/resolve", params=GEO).json()
    assert data["city"] == "Cebu City" and data["island"] == "Visayas" and data["metro_manila"] is False
    assert [s["name"] for s in data["stores"]] == ["Near Mart", "Far Mall"]
    assert data["stores"][0]["distance_km"] < data["stores"][1]["distance_km"]


def test_store_query_uses_the_city_boundary(client, osm):
    client.get("/api/v1/location/resolve", params=GEO)
    assert "(10.2463,123.7595,10.4962,123.9302)" in osm["query"]


def test_results_are_cached_without_precise_coordinates(client, db, osm):
    client.get("/api/v1/location/resolve", params=GEO)
    client.get("/api/v1/location/resolve", params={"latitude": 10.3161, "longitude": 123.8861})
    assert osm["stores"] == 1
    assert db.location_cache.find_one()["_id"] == "geo:10.32:123.89"


def test_location_denied_can_use_a_city_name(client, osm):
    data = client.get("/api/v1/location/resolve", params={"city": "Cebu City"}).json()
    assert data["city"] == "Cebu City" and data["store_count"] == 2


def test_outside_the_philippines_is_refused_clearly(client, osm):
    CEBU["address"]["country_code"] = "sg"
    try:
        response = client.get("/api/v1/location/resolve", params={"latitude": 1.3, "longitude": 103.8})
    finally:
        CEBU["address"]["country_code"] = "ph"
    assert response.status_code == 503 and "Philippines" in response.json()["detail"]


def test_backup_map_search_is_used_when_overpass_is_down(client, osm):
    osm["overpass_down"] = True
    osm["backup"] = {
        "mall": [{"name": "Backup Mall", "category": "shop", "type": "mall", "lat": "10.31", "lon": "123.89"}],
        "supermarket": [{"name": "A Cafe", "category": "amenity", "type": "cafe", "lat": "10.3", "lon": "123.8"}],
    }
    data = client.get("/api/v1/location/resolve", params=GEO).json()
    assert [s["name"] for s in data["stores"]] == ["Backup Mall"]


def test_city_still_resolves_when_every_store_map_is_down(client, db, osm):
    osm["overpass_down"] = True
    response = client.get("/api/v1/location/resolve", params=GEO)
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Cebu City" and data["island"] == "Visayas"
    assert data["stores"] == [] and data["stores_available"] is False
    assert db.location_cache.count_documents({}) == 0, "an outage must not be cached"


def test_requests_need_a_location_or_city(client):
    assert client.get("/api/v1/location/resolve").status_code == 422
    assert client.get("/api/v1/location/resolve", params={"latitude": 10}).status_code == 422
    assert client.get("/api/v1/location/resolve", params={"latitude": 99, "longitude": 1}).status_code == 422


@pytest.mark.parametrize("region,island", [
    ("Central Visayas", "Visayas"), ("Western Visayas", "Visayas"), ("Negros Island Region", "Visayas"),
    ("Davao Region", "Mindanao"), ("Northern Mindanao", "Mindanao"), ("Zamboanga Peninsula", "Mindanao"),
    ("Soccsksargen", "Mindanao"), ("Caraga", "Mindanao"), ("Bangsamoro", "Mindanao"),
    ("Metro Manila", "Luzon"), ("Calabarzon", "Luzon"), ("Ilocos Region", "Luzon"), ("Bicol Region", "Luzon"),
])
def test_island_groups(region, island):
    assert location.island_group(region) == island
