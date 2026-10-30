"""Acceptance criteria AC-01 to AC-08 plus the spec's ranking rules."""
from app.comparison import haversine_km

CEBU = dict(latitude=10.3157, longitude=123.8854)


def search(client, **params):
    response = client.get("/api/v1/products/search", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_ac01_search_returns_matches(client):
    names = {r["product_name"] for r in search(client, q="rice")["results"]}
    assert "Jasmine Rice" in names and "Brown Rice" in names


def test_search_by_brand_size_and_barcode(client):
    assert {r["brand"] for r in search(client, q="dairy valley")["results"]} == {"Dairy Valley"}
    sized = search(client, q="cooking oil 1L")["results"]
    assert sized and {r["package_size"] for r in sized} == {"1 L"}
    assert search(client, q="480000000005")["results"][0]["product_name"] == "Cooking Oil"


def test_ac02_prices_ascending(client):
    prices = [r["price"] for r in search(client, q="soy sauce")["results"]]
    assert prices == sorted(prices) and len(prices) >= 3


def test_ac05_distance_sort(client):
    distances = [r["distance_km"] for r in search(client, q="soy sauce", sort_by="distance_asc", **CEBU)["results"]]
    assert distances == sorted(distances)


def test_ac06_radius_excludes_far_stores(client):
    results = search(client, q="soy sauce", radius_km=3, **CEBU)["results"]
    assert results and all(r["distance_km"] <= 3 for r in results)
    assert len(results) < len(search(client, q="soy sauce", **CEBU)["results"])


def test_search_without_location_still_works_ac04(client):
    assert all(r["distance_km"] is None for r in search(client, q="rice")["results"])


def test_half_a_location_is_rejected(client):
    assert client.get("/api/v1/products/search", params={"q": "x", "latitude": 10}).status_code == 422


def test_invalid_coordinates_rejected(client):
    assert client.get("/api/v1/products/search", params={"latitude": 91, "longitude": 0}).status_code == 422


def test_ac08_freshness_exposed(client):
    for row in search(client, q="rice")["results"]:
        assert row["last_synced_at"].endswith("Z") and row["price_status"] in {"fresh", "aging"}


def test_stale_excluded_by_default_and_shown_separately(client):
    default = search(client, q="soy sauce")
    assert "Test Supermarket Lapu-Lapu" not in {r["store_name"] for r in default["results"]}
    assert default["stale_hidden"] == 1
    shown = search(client, q="soy sauce", include_stale=True)
    assert [r["store_name"] for r in shown["stale_results"]] == ["Test Supermarket Lapu-Lapu"]
    assert shown["stale_results"][0]["price_status"] == "stale"


def test_labels_are_per_comparable_product(client):
    results = search(client, q="jasmine rice", **CEBU)["results"]
    by_size = {}
    for row in results:
        by_size.setdefault(row["package_size"], []).append(row)
    assert set(by_size) == {"1 kg", "5 kg"}
    for rows in by_size.values():
        assert sum("Lowest Price" in r["labels"] for r in rows) == 1
        cheapest = min(r["price"] for r in rows)
        assert next(r for r in rows if "Lowest Price" in r["labels"])["price"] == cheapest
        assert sum("Nearest Store" in r["labels"] for r in rows) == 1


def test_unavailable_never_ranked(client, db):
    store = db.stores.find_one({"name": "Demo Grocer Mandaue"})
    listing = db.store_products.find_one({"store_id": store["_id"]})
    db.store_products.update_one({"_id": listing["_id"]}, {"$set": {"availability_status": "unavailable"}})
    prices = client.get(f"/api/v1/products/{listing['product_id']}/prices").json()
    assert "Demo Grocer Mandaue" not in {r["store_name"] for r in prices["results"]}


def test_haversine_known_points():
    # Cebu City to Manila, about 570 km great-circle.
    assert 560 < haversine_km(10.3157, 123.8854, 14.5995, 120.9842) < 580


def test_ac07_product_and_store_details(client):
    row = search(client, q="corned beef", **CEBU)["results"][0]
    assert client.get(f"/api/v1/products/{row['product_id']}").json()["brand"] == "Rancho"
    store = client.get(f"/api/v1/stores/{row['store_id']}", params=CEBU).json()
    assert store["distance_km"] == row["distance_km"]
    assert client.get(f"/api/v1/stores/{row['store_id']}/products").json()


def test_nearby_stores_sorted(client):
    stores = client.get("/api/v1/stores/nearby", params=CEBU).json()
    assert [s["distance_km"] for s in stores] == sorted(s["distance_km"] for s in stores)
