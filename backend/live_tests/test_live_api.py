"""End-to-end checks against the deployed backend with real data and real locations.

Run with: pytest live_tests
"""
import os
from datetime import date, timedelta

import httpx
import pytest

API = os.getenv("LIVE_API", "https://grocery-price-finder-api.onrender.com") + "/api/v1"
client = httpx.Client(timeout=90)


def get(path, **params):
    response = client.get(f"{API}{path}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_service_is_up():
    assert get("/health")["status"] == "ok"


def test_no_sample_data_remains():
    stats = get("/stats")
    assert stats["retailers"] == 0 and stats["listings"] == 0 and stats["products"] == 0


def test_both_official_sources_are_loaded():
    sources = {s["id"]: s for s in get("/market/summary")["sources"]}
    assert sources["dti_srp"]["rows"] >= 120
    assert sources["da_dpi"]["rows"] >= 100


def test_market_prices_are_recent():
    report = next(s for s in get("/market/summary")["sources"] if s["id"] == "da_dpi")
    assert date.fromisoformat(report["report_date"]) >= date.today() - timedelta(days=7)


@pytest.mark.parametrize("query,word", [
    ("rice", "rice"), ("tilapia", "tilapia"), ("eggs", "egg"), ("sardines", "sardines"),
    ("garlic", "garlic"), ("cooking oil", "cooking oil"), ("bear brand", "bear brand"),
])
def test_live_search_finds_real_items(query, word):
    rows = get("/market/prices", q=query)["results"]
    assert rows, query
    assert all(r["price"] > 0 and r["source_url"].startswith("https://") for r in rows)
    assert any(word in f'{r["commodity"]} {r["category"]}'.lower() for r in rows)


def test_search_with_no_match_is_empty():
    assert get("/market/prices", q="unicorn steak")["count"] == 0


@pytest.mark.parametrize("latitude,longitude,city,island", [
    (10.3157, 123.8854, "Cebu City", "Visayas"),
    (14.5547, 121.0244, "Makati", "Luzon"),
    (7.0731, 125.6128, "Davao City", "Mindanao"),
])
def test_true_location_resolves_city_and_its_stores(latitude, longitude, city, island):
    data = get("/location/resolve", latitude=latitude, longitude=longitude)
    assert city.lower() in data["city"].lower() and data["island"] == island
    assert data["store_count"] > 0
    distances = [s["distance_km"] for s in data["stores"]]
    assert distances == sorted(distances)


def test_prices_follow_the_located_island():
    visayas = get("/market/prices", q="fidel", island="Visayas")["results"]
    assert visayas and all("Luzon" not in r["commodity"] for r in visayas)


def test_city_name_fallback():
    assert "cebu" in get("/location/resolve", city="Cebu City")["city"].lower()


def test_basket_totals_real_prices():
    body = {"items": [{"query": "bear brand", "quantity": 2}, {"query": "tilapia"}]}
    response = client.post(f"{API}/market/basket", json=body)
    data = response.json()
    assert data["items_matched"] == 2
    assert data["total"] == round(sum(l["line_total"] for l in data["lines"]), 2)


def test_snacks_have_two_sizes():
    sizes = {item["variant"] for item in get("/market/catalog", q="piatos cheese") if item["variant"]}
    assert sizes == {"Small", "Large"}


def test_road_route_between_two_cebu_points():
    route = get("/location/route", from_lat=10.3157, from_lon=123.8854, to_lat=10.3439, to_lon=123.9118)
    assert len(route["path"]) >= 2 and route["distance_km"] > 0


def test_brand_catalog_finds_piatos_and_mega():
    assert any("Piatos" in item["name"] for item in get("/market/catalog", q="piatos"))
    assert any("Mega Sardines" in item["name"] for item in get("/market/catalog", q="mega sardines"))
