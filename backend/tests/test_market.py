"""Official price parsing and search, checked against real government PDFs.

Expected values below were read directly from the published documents in tests/fixtures.
"""
from datetime import date, datetime
from pathlib import Path

import pytest

from app import market
from app.bootstrap import ensure_admin, purge_sample_data
from app.db import utcnow
from app.sources import da_dpi, dti_srp, open_data
from sample_data import seed

FIXTURES = Path(__file__).parent / "fixtures"
SRP_PDF = (FIXTURES / "dti_srp_2026-05-11.pdf").read_bytes()
DPI_PDF = (FIXTURES / "da_dpi_2026-10-30.pdf").read_bytes()
SRP_URL = "https://dti.example/bulletin.pdf"
DPI_URL = "https://da.example/2026-10-30.pdf"


@pytest.fixture(scope="module")
def srp():
    return dti_srp.parse_bulletin(SRP_PDF)


@pytest.fixture(scope="module")
def dpi():
    return da_dpi.parse_report(DPI_PDF)


@pytest.fixture()
def loaded(client, db, srp, dpi):
    market.store_report(db, "dti_srp", SRP_URL, srp)
    market.store_report(db, "da_dpi", DPI_URL, dpi)
    return db


def find(rows, commodity, specification=""):
    return next(r for r in rows if r["commodity"] == commodity and r["specification"] == specification)


def test_srp_bulletin_reads_every_price_on_the_page(srp):
    assert srp["report_date"] == date(2026, 5, 11)
    assert len(srp["rows"]) == 167


@pytest.mark.parametrize("commodity,size,centavos,category", [
    ("Saba Philippines Sardines", "155g", 2150, "Canned Sardines In Tomato Sauce"),
    ("Bear Brand", "135g", 5000, "Powdered Milk"),
    ("Pinoy Tasty", "450g", 4400, "Bread"),
    ("Lasap Iodized Salt", "1kg", 3150, "Iodized Salt"),
    ("Argentina", "175g", 4175, "Corned Beef"),
])
def test_srp_rows_match_the_bulletin(srp, commodity, size, centavos, category):
    row = find(srp["rows"], commodity, size)
    assert row["price_centavos"] == centavos and row["category"] == category


def test_srp_wrapped_names_stay_whole(srp):
    budget = find(srp["rows"], "Budget Bar (WHITE ANTI BAC, FABCON, KALAMANSI, POWER BLUE, SPECKLED BLUE) - Luzon", "330g")
    assert budget["price_centavos"] == 2100
    palmolive = next(r for r in srp["rows"] if r["commodity"].startswith("Palmolive Naturals"))
    assert palmolive["commodity"].endswith("White with Natural Milk") and palmolive["price_centavos"] == 1700


def test_srp_groups_are_assigned(srp):
    assert find(srp["rows"], "Bear Brand", "135g")["group"] == "Basic Necessities"
    assert find(srp["rows"], "Bingo", "150g")["group"] == "Prime Commodities"


def test_srp_refuses_a_page_with_unaccounted_prices(monkeypatch):
    monkeypatch.setattr(dti_srp, "MIN_ROWS", 9999)
    with pytest.raises(ValueError):
        dti_srp.parse_bulletin(SRP_PDF)


def test_latest_bulletin_is_the_may_2026_file_not_a_backup():
    url = dti_srp.latest_bulletin_url((FIXTURES / "dti_listing.xml").read_bytes())
    assert "11%20MAY%202026" in url


def test_dpi_reads_date_and_rows(dpi):
    assert dpi["report_date"] == date(2026, 10, 30)
    assert sum(r["price_centavos"] is not None for r in dpi["rows"]) > 150


@pytest.mark.parametrize("commodity,specification,centavos,unit", [
    ("Premium Rice, Local", "5% broken", 5387, "kg"),
    ("Bangus, Medium", "Medium (3-4 pcs/kg)", 24733, "kg"),
    ("Chicken Egg (White, Medium)", "56-60 grams/pc", 824, "piece"),
    ("Cooking Oil (Palm)", "1 Liter/bottle", 10239, "bottle"),
    ("Tomato", "15-18 pcs/kg", 9864, "kg"),
])
def test_dpi_rows_match_the_report(dpi, commodity, specification, centavos, unit):
    rows = [r for r in dpi["rows"] if r["commodity"] == commodity and r["specification"] == specification]
    assert rows and rows[-1]["price_centavos"] == centavos and rows[-1]["unit"] == unit


def test_dpi_keeps_not_available_as_missing_never_zero(dpi):
    assert next(r for r in dpi["rows"] if r["commodity"] == "Lamb Meat")["price_centavos"] is None


def test_dpi_rejects_a_report_with_no_date():
    with pytest.raises(Exception):
        da_dpi.parse_report(b"not a pdf")


def test_daily_links_exclude_weekly_reports():
    html = '''
    <a href="https://www.da.gov.ph/wp-content/uploads/2026/10/October-30-2026-DPI-AFC.pdf">a</a>
    <a href="https://www.da.gov.ph/wp-content/uploads/2026/10/Daily-Price-Index-October-29-2026.pdf">b</a>
    <a href="https://www.da.gov.ph/wp-content/uploads/2026/10/Weekly-Average-Prices-October-19-25-2026.pdf">c</a>
    '''
    urls = da_dpi.daily_report_urls(html)
    assert len(urls) == 2 and urls[0].endswith("DPI-AFC.pdf")


def test_failed_report_keeps_previous_prices(client, db, srp):
    class Http:
        def get(self, url):
            class R:
                content = b"broken"
                def raise_for_status(self): pass
            return R()

    market.store_report(db, "dti_srp", SRP_URL, srp)
    market._ingest_pdf(db, Http(), "dti_srp", "https://dti.example/new.pdf", dti_srp.parse_bulletin)
    assert market.latest_date(db, "dti_srp") == "2026-05-11"
    assert db.market_reports.find_one({"_id": "https://dti.example/new.pdf"})["status"] == "failed"


def search(client, **params):
    response = client.get("/api/v1/market/prices", params=params)
    assert response.status_code == 200, response.text
    return response.json()["results"]


@pytest.mark.parametrize("query,expected", [
    ("sardines", "Saba Philippines Sardines"),
    ("corned beef", "Argentina"),
    ("rice", "Premium Rice, Imported"),
    ("tilapia", "Tilapia"),
    ("eggs", "Chicken Egg (White, Medium)"),
    ("garlic", "Garlic, Native/Local"),
    ("cooking oil", "Cooking Oil (Palm)"),
    ("lucky me", None),
    ("BEAR BRAND", "Bear Brand"),
])
def test_live_search_cases(loaded, client, query, expected):
    rows = search(client, q=query)
    assert rows, query
    if expected:
        assert expected in {r["commodity"] for r in rows}


def test_search_nothing_returns_empty_not_error(loaded, client):
    assert search(client, q="unicorn steak") == []


def test_every_row_cites_source_and_date(loaded, client):
    for row in search(client):
        assert row["source_url"] and row["report_date"] and row["price"] > 0 and row["region"]


def test_source_and_category_filters(loaded, client):
    assert {r["source"] for r in search(client, source="dti_srp")} == {"dti_srp"}
    assert {r["category"] for r in search(client, category="Corned Beef")} == {"Corned Beef"}


def test_day_on_day_change_uses_consecutive_reports(loaded, client, db, dpi):
    earlier = {"report_date": date(2026, 10, 29), "rows": [
        {**r, "price_centavos": r["price_centavos"] - 100 if r["price_centavos"] else None} for r in dpi["rows"]
    ]}
    market.store_report(db, "da_dpi", "https://da.example/2026-10-29.pdf", earlier)
    row = search(client, q="tilapia")[0]
    assert row["report_date"] == "2026-10-30" and row["change"] == 1.0 and len(row["trend"]) == 2
    assert market.summary(db)["rising"] > 100


def test_regional_srp_items_follow_the_located_island(loaded, client):
    luzon = {r["commodity"] for r in search(client, q="fidel", island="Luzon")}
    visayas = {r["commodity"] for r in search(client, q="fidel", island="Visayas")}
    assert all("Visayas" not in c and "Mindanao" not in c for c in luzon)
    assert all("Luzon" not in c for c in visayas) and luzon and visayas
    assert search(client, q="sardines", island="Mindanao"), "nationwide SRPs apply everywhere"


def test_basket_totals_exact_official_prices(loaded, client):
    body = {"items": [{"query": "Bear Brand", "quantity": 2}, {"query": "tilapia", "quantity": 3}, {"query": "unicorn"}]}
    data = client.post("/api/v1/market/basket", json=body).json()
    assert data["total"] == round(50.00 * 2 + 157.30 * 3, 2)
    assert data["items_matched"] == 2 and data["items_unmatched"] == 1


def test_basket_user_can_pick_exact_size(loaded, client):
    first = client.post("/api/v1/market/basket", json={"items": [{"query": "cooking oil"}]}).json()["lines"][0]
    other = next(c for c in first["candidates"] if c["id"] != first["selected"]["id"])
    pinned = client.post("/api/v1/market/basket", json={"items": [{"query": "cooking oil", "price_id": other["id"]}]}).json()
    assert pinned["lines"][0]["selected"]["id"] == other["id"] and pinned["total"] == other["price"]


@pytest.mark.parametrize("query", [
    "mega sardines", "piatos", "junk food", "nova", "chips", "utensils", "appliances", "rice cooker",
    "dog food", "cat food", "pet", "perfume", "cologne", "diapers",
])
def test_brands_outside_official_lists_are_searchable(client, query):
    items = client.get("/api/v1/market/catalog").json()
    tokens = query.split()
    assert any(all(t in item["keywords"] for t in tokens) for item in items)


def test_catalog_never_contains_prices(client):
    for item in client.get("/api/v1/market/catalog").json():
        assert not any("price" in key for key in item)


def test_catalog_item_waits_for_a_shelf_price(loaded, client):
    data = client.post("/api/v1/market/basket", json={"items": [{"query": "piatos"}]}).json()
    assert data["lines"][0]["status"] == "needs_price" and data["total"] == 0
    assert data["items_need_price"] == 1 and "Piatos" in data["lines"][0]["label"]


def test_official_price_wins_over_the_catalog(loaded, client):
    line = client.post("/api/v1/market/basket", json={"items": [{"query": "Bear Brand"}]}).json()["lines"][0]
    assert line["status"] == "matched"


def test_shelf_price_counts_in_the_total(loaded, client):
    body = {"items": [{"query": "piatos", "quantity": 2, "custom_price": 45.5}, {"query": "Bear Brand"}]}
    data = client.post("/api/v1/market/basket", json=body).json()
    assert data["lines"][0]["status"] == "custom" and data["lines"][0]["line_total"] == 91.0
    assert data["total"] == 141.0 and data["items_matched"] == 2


def test_negative_shelf_price_is_refused(client):
    body = {"items": [{"query": "piatos", "custom_price": -1}]}
    assert client.post("/api/v1/market/basket", json=body).status_code == 422


def test_sample_data_is_removed_and_real_prices_stay(client, db, loaded):
    purge_sample_data(db)
    assert db.organizations.count_documents({}) == 0 and db.users.count_documents({}) == 0
    assert db.products.count_documents({}) == 0 and db.store_products.count_documents({}) == 0
    assert db.market_prices.count_documents({}) > 300


def test_purge_keeps_real_retailers(client, db):
    db.organizations.insert_one({"_id": "real", "name": "Real Retailer"})
    purge_sample_data(db)
    assert db.organizations.find_one({"_id": "real"})


def test_admin_created_once(client, db, monkeypatch):
    monkeypatch.setattr("app.bootstrap.ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setattr("app.bootstrap.ADMIN_PASSWORD", "a-strong-password")
    ensure_admin(db)
    ensure_admin(db)
    assert db.users.count_documents({"email": "owner@example.com"}) == 1


def shelf(client, name="Leslie's Cheezy Corn Crunch 70g", store="SM Hypermarket", price=33.5, lat=10.31, lon=123.89):
    body = dict(name=name, store_name=store, latitude=lat, longitude=lon, city="Cebu City", price=price)
    return client.post("/api/v1/market/shelf-prices", json=body)


def test_snacks_have_small_and_large_sizes(client):
    items = [i for i in client.get("/api/v1/market/catalog").json() if "Cheezy Corn Crunch" in i["name"]]
    assert {i["variant"] for i in items} == {"Small", "Large"} and {i["size"] for i in items} == {"30g", "70g"}


def test_reported_price_replaces_no_price(client):
    assert shelf(client).status_code == 201
    body = {"items": [{"query": "Cheezy Corn Crunch 70g", "quantity": 2}], "city": "Cebu City"}
    line = client.post("/api/v1/market/basket", json=body).json()["lines"][0]
    assert line["status"] == "reported" and line["line_total"] == 67.0
    assert line["report"]["store_name"] == "SM Hypermarket"


def test_reports_stay_in_their_city(client):
    shelf(client)
    body = {"items": [{"query": "Cheezy Corn Crunch 70g"}], "city": "Davao City"}
    assert client.post("/api/v1/market/basket", json=body).json()["lines"][0]["status"] == "needs_price"


def test_official_price_wins_over_a_report(loaded, client):
    shelf(client, name="Bear Brand", price=1)
    line = client.post("/api/v1/market/basket", json={"items": [{"query": "Bear Brand"}]}).json()["lines"][0]
    assert line["status"] == "matched" and line["unit_price"] == 50


def test_newest_report_per_store_counts(client):
    shelf(client, price=40)
    shelf(client, price=35)
    data = client.post("/api/v1/market/best-stores", json={"items": ["Cheezy Corn Crunch 70g"]}).json()
    assert data["best"]["total"] == 35


def test_cheapest_store_for_the_list_is_ranked_first(client):
    for store, chips, soda, lat in (("SM Market", 30, 80, 10.31), ("Robinsons", 34, 70, 10.32), ("Corner Store", 20, 0, 10.33)):
        shelf(client, name="Piatos Cheese 85g", store=store, price=chips, lat=lat)
        if soda:
            shelf(client, name="Coca-Cola Regular 1.5L", store=store, price=soda, lat=lat)
    body = {"items": ["piatos", "coca-cola"], "latitude": 10.3157, "longitude": 123.8854, "city": "Cebu City"}
    data = client.post("/api/v1/market/best-stores", json=body).json()
    assert data["best"]["store_name"] == "Robinsons" and data["best"]["total"] == 104
    assert data["best"]["items_found"] == 2 and data["best"]["distance_km"] is not None
    assert data["items_priced"] == 2


def test_no_reports_means_no_store_is_named(client):
    data = client.post("/api/v1/market/best-stores", json={"items": ["piatos"]}).json()
    assert data["best"] is None and data["items_priced"] == 0


def test_outlier_is_held_for_review_and_can_be_approved(client, admin):
    for index, store in enumerate(("A Mart", "B Mart", "C Mart")):
        shelf(client, store=store, price=30 + index)
    response = shelf(client, store="D Mart", price=500).json()
    assert response["held_for_review"] is True
    best = client.post("/api/v1/market/best-stores", json={"items": ["Cheezy 70g"]}).json()
    assert "D Mart" not in {s["store_name"] for s in best["stores"]}
    held = next(r for r in client.get("/api/v1/admin/shelf-prices", headers=admin).json() if r["status"] == "flagged")
    assert client.post(f"/api/v1/admin/shelf-prices/{held['id']}/approve", headers=admin).status_code == 200
    best = client.post("/api/v1/market/best-stores", json={"items": ["Cheezy 70g"]}).json()
    assert "D Mart" in {s["store_name"] for s in best["stores"]}


def test_admin_can_remove_a_report(client, admin, supervisor):
    shelf(client)
    report = client.get("/api/v1/admin/shelf-prices", headers=admin).json()[0]
    assert client.delete(f"/api/v1/admin/shelf-prices/{report['id']}", headers=supervisor).status_code == 403
    assert client.delete(f"/api/v1/admin/shelf-prices/{report['id']}", headers=admin).status_code == 200
    assert client.get("/api/v1/admin/shelf-prices", headers=admin).json() == []


def test_old_reports_expire(client, db):
    shelf(client)
    db.shelf_reports.update_many({}, {"$set": {"created_at": datetime(2026, 1, 1)}})
    assert client.post("/api/v1/market/best-stores", json={"items": ["Cheezy"]}).json()["best"] is None


@pytest.mark.parametrize("change", [{"price": 0}, {"price": -5}, {"latitude": 1.3}, {"store_name": "x"}])
def test_bad_shelf_prices_are_refused(client, change):
    body = dict(name="Piatos", store_name="SM", latitude=10.3, longitude=123.9, city="Cebu City", price=30)
    assert client.post("/api/v1/market/shelf-prices", json={**body, **change}).status_code == 422


FOOD = {"code": "4800016", "product_name": "Cheezy Corn Crunch", "brands": "Leslie's,Other", "quantity": "70 g",
        "categories_tags": ["en:snacks", "en:corn-snacks"], "image_small_url": "https://img/x.jpg"}
PRICE = {"id": 9, "product_code": "4800016", "price": 33.5, "date": "2026-10-01", "price_is_discounted": False, "price_per": None,
         "product": {"product_name": "Cheezy Corn Crunch", "brands": "Leslie's", "quantity": "70 g"},
         "location": {"osm_name": "SM Hypermarket", "osm_lat": 10.31, "osm_lon": 123.89, "osm_address_city": "Cebu City"}}


class Page:
    def __init__(self, body, code=200):
        self.body, self.status_code = body, code

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


class Http:
    def __init__(self, *pages):
        self.pages = list(pages)
        self.params = []

    def get(self, url, params=None):
        self.params.append(params)
        return self.pages.pop(0)


def test_open_data_product_is_cleaned_up():
    doc = open_data.product_doc(FOOD, "food")
    assert doc["_id"] == "off:4800016" and doc["name"] == "Leslie's Cheezy Corn Crunch"
    assert doc["size"] == "70 g" and doc["category"] == "Corn Snacks" and doc["barcode"] == "4800016"


@pytest.mark.parametrize("bad", [{"code": "", "product_name": "x y"}, {"code": "1", "product_name": ""}, {"code": "1", "product_name": None}])
def test_unusable_products_are_skipped(bad):
    assert open_data.product_doc(bad, "food") is None


def test_products_sync_in_pages_and_become_searchable(client, db):
    full = {"products": [{**FOOD, "code": str(n)} for n in range(100)]}
    http = Http(Page(full), Page({"products": [FOOD]}))
    assert open_data.sync_product_page(db, http, "food") is True
    assert open_data.sync_product_page(db, http, "food") is False
    assert [p["page"] for p in http.params] == [1, 2]
    found = client.get("/api/v1/market/catalog", params={"q": "cheezy 70"})
    assert int(found.headers["X-Total-Count"]) >= 1 and any(i["barcode"] == "4800016" for i in found.json())


def test_a_busy_service_keeps_our_place(client, db):
    db.sync_state.insert_one({"_id": "food", "page": 7, "finished_at": None})
    assert open_data.sync_product_page(db, Http(Page({}, 503)), "food") is False
    assert db.sync_state.find_one({"_id": "food"})["page"] == 7


def test_finished_site_rests_until_refresh(client, db):
    db.sync_state.insert_one({"_id": "food", "page": 1, "finished_at": utcnow()})
    http = Http()
    assert open_data.sync_product_page(db, http, "food") is False and http.params == []


def test_removed_product_stays_removed_after_sync(client, db, admin):
    open_data.sync_product_page(db, Http(Page({"products": [FOOD]})), "food")
    assert client.delete("/api/v1/admin/catalog/off:4800016", headers=admin).status_code == 200
    db.sync_state.delete_many({})
    open_data.sync_product_page(db, Http(Page({"products": [FOOD]})), "food")
    assert client.get("/api/v1/market/catalog", params={"q": "4800016"}).json() == []


def test_open_price_reaches_receipt_chart_and_cheapest_store(client, db):
    open_data.sync_product_page(db, Http(Page({"products": [FOOD]})), "food")
    assert open_data.sync_prices(db, Http(Page({"items": [PRICE], "pages": 1}))) == 1
    body = {"items": [{"query": "cheezy corn crunch 70", "quantity": 2}], "city": "Cebu City"}
    line = client.post("/api/v1/market/basket", json=body).json()["lines"][0]
    assert line["status"] == "reported" and line["line_total"] == 67 and line["report"]["origin"] == "Open Prices"
    best = client.post("/api/v1/market/best-stores", json={"items": ["cheezy corn crunch"]}).json()["best"]
    assert best["store_name"] == "SM Hypermarket"
    points = client.get("/api/v1/market/catalog/off:4800016/prices").json()["points"]
    assert [p["price"] for p in points] == [33.5] and points[0]["store"] == "SM Hypermarket"


@pytest.mark.parametrize("change", [{"price_is_discounted": True}, {"price_per": "KILOGRAM"}, {"location": {}}, {"price": 0}])
def test_only_standard_located_prices_are_kept(change):
    assert open_data.price_doc({**PRICE, **change}) is None


def test_regex_characters_in_search_are_harmless(client):
    assert client.get("/api/v1/market/catalog", params={"q": "(.*)+["}).status_code == 200
