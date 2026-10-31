"""The data integration layer: permission gates, price scope and verification dates."""
import io
from datetime import timedelta

import pytest

from app import community, ingestion
from app.db import utcnow

COLUMNS = "retailer,branch,latitude,longitude,city,product,size,barcode,price,verified_at\n"
TODAY = utcnow().date().isoformat()


def grant(client, admin, source="waltermart"):
    response = client.patch(f"/api/v1/admin/sources/{source}", headers=admin,
                            json={"permission": "granted", "notes": "Signed agreement, 2026-10-31", "enabled": True})
    assert response.status_code == 200, response.text


def upload(client, admin, body, source="waltermart"):
    return client.post(f"/api/v1/admin/sources/{source}/import", headers=admin,
                       files={"file": ("feed.csv", io.BytesIO(body.encode()), "text/csv")})


def test_budolista_starts_blocked_with_the_reason_on_record(client, admin):
    sources = {s["id"]: s for s in client.get("/api/v1/admin/sources", headers=admin).json()}
    assert sources["budolista"]["permission"] == "pending" and sources["budolista"]["can_run"] is False
    assert "non-commercial" in sources["budolista"]["notes"]
    assert sources["open-prices"]["can_run"] is True


def test_import_is_refused_without_permission(client, db, admin):
    response = upload(client, admin, COLUMNS + f"Budolista,,,,,Piatos,85g,,30,{TODAY}\n", "budolista")
    assert response.status_code == 403 and db.retail_prices.count_documents({}) == 0


def test_a_source_cannot_be_switched_on_without_permission(client, admin):
    response = client.patch("/api/v1/admin/sources/budolista", json={"enabled": True}, headers=admin)
    assert response.status_code == 409


def test_granting_permission_requires_a_record_of_it(client, admin):
    response = client.patch("/api/v1/admin/sources/budolista", json={"permission": "granted"}, headers=admin)
    assert response.status_code == 422


def test_withdrawn_permission_stops_the_source_and_its_prices(client, db, admin):
    grant(client, admin)
    upload(client, admin, COLUMNS + f"WalterMart,,,,,Piatos Cheese,85g,,30,{TODAY}\n")
    body = {"items": [{"query": "piatos cheese 85g"}]}
    assert client.post("/api/v1/market/basket", json=body).json()["lines"][0]["status"] == "reported"
    client.patch("/api/v1/admin/sources/waltermart", json={"permission": "refused"}, headers=admin)
    assert ingestion.can_run(db, "waltermart") is False
    assert client.post("/api/v1/market/basket", json=body).json()["lines"][0]["status"] == "estimated"


def test_only_system_admin_manages_sources(client, supervisor):
    assert client.get("/api/v1/admin/sources", headers=supervisor).status_code == 403


def test_chain_price_is_labelled_and_never_named_as_a_branch(client, admin):
    grant(client, admin)
    result = upload(client, admin, COLUMNS + f"WalterMart,,,,,Piatos Cheese,85g,,30,{TODAY}\n").json()
    assert result["imported"] == 1
    line = client.post("/api/v1/market/basket", json={"items": [{"query": "piatos cheese 85g"}]}).json()["lines"][0]
    assert line["unit_price"] == 30 and "branches may differ" in line["report"]["origin"]
    best = client.post("/api/v1/market/best-stores", json={"items": ["piatos cheese 85g"]}).json()
    assert best["best"] is None


def test_branch_price_reaches_the_cheapest_store_map(client, admin):
    grant(client, admin)
    upload(client, admin, COLUMNS + f"WalterMart,Cebu,10.31,123.89,Cebu City,Piatos Cheese,85g,,30,{TODAY}\n")
    body = {"items": ["piatos cheese 85g"], "city": "Cebu City"}
    assert client.post("/api/v1/market/best-stores", json=body).json()["best"]["store_name"] == "WalterMart Cebu"


def test_branch_price_stays_in_its_city(client, admin):
    grant(client, admin)
    upload(client, admin, COLUMNS + f"WalterMart,Cebu,10.31,123.89,Cebu City,Piatos Cheese,85g,,30,{TODAY}\n")
    body = {"items": ["piatos cheese 85g"], "city": "Davao City"}
    assert client.post("/api/v1/market/best-stores", json=body).json()["best"] is None


def test_small_and_large_sizes_stay_separate(client, db, admin):
    grant(client, admin)
    upload(client, admin, COLUMNS + f"WalterMart,,,,,Piatos Cheese,85g,,30,{TODAY}\nWalterMart,,,,,Piatos Cheese,40g,,15,{TODAY}\n")
    assert db.retail_prices.count_documents({}) == 2


def test_reimport_updates_rather_than_duplicates(client, db, admin):
    grant(client, admin)
    upload(client, admin, COLUMNS + f"WalterMart,,,,,Piatos Cheese,85g,,30,{TODAY}\n")
    upload(client, admin, COLUMNS + f"WalterMart,,,,,Piatos Cheese,85g,,32,{TODAY}\n")
    assert db.retail_prices.count_documents({}) == 1 and db.retail_prices.find_one()["price_centavos"] == 3200


def test_old_prices_drop_out(client, db, admin):
    grant(client, admin)
    old = (utcnow() - timedelta(days=ingestion.MAX_PRICE_AGE_DAYS + 1)).date().isoformat()
    upload(client, admin, COLUMNS + f"WalterMart,,,,,Piatos Cheese,85g,,30,{old}\n")
    line = client.post("/api/v1/market/basket", json={"items": [{"query": "piatos cheese 85g"}]}).json()["lines"][0]
    assert line["status"] == "estimated"


@pytest.mark.parametrize("row,reason", [
    (f",,,,,Piatos,85g,,30,{TODAY}", "retailer"),
    (f"WalterMart,,,,,,85g,,30,{TODAY}", "product"),
    (f"WalterMart,,,,,Piatos,,,30,{TODAY}", "size"),
    (f"WalterMart,,,,,Piatos,85g,,abc,{TODAY}", "number"),
    (f"WalterMart,,,,,Piatos,85g,,0,{TODAY}", "above zero"),
    (f"WalterMart,,,,,Piatos,85g,,nan,{TODAY}", "above zero"),
    ("WalterMart,,,,,Piatos,85g,,30,", "verified_at"),
    ("WalterMart,,,,,Piatos,85g,,30,2099-01-01", "future"),
    (f"WalterMart,Cebu,1.3,103.8,,Piatos,85g,,30,{TODAY}", "Philippines"),
    (f"WalterMart,,10.3,123.9,,Piatos,85g,,30,{TODAY}", "branch name"),
])
def test_bad_rows_are_rejected_with_a_reason(client, db, admin, row, reason):
    grant(client, admin)
    result = upload(client, admin, COLUMNS + row + "\n").json()
    assert result["rejected"] == 1 and reason in result["rejections"][0]["reason"]
    assert result["rejections"][0]["row"] == 2 and db.retail_prices.count_documents({}) == 0


def test_missing_columns_stop_the_whole_file(client, admin):
    grant(client, admin)
    assert upload(client, admin, "retailer,price\nWalterMart,30\n").status_code == 422


def test_new_sources_start_without_permission(client, admin):
    body = dict(name="New Mart API", kind="retailer_api", terms_url="https://example.com/terms")
    source = client.post("/api/v1/admin/sources", json=body, headers=admin).json()
    assert source["permission"] == "pending" and source["can_run"] is False


def test_mall_search_lists_real_prices_by_mall(client, admin):
    grant(client, admin)
    feed = f"WalterMart,Cebu,10.31,123.89,Cebu City,Piatos Cheese,85g,,40,{TODAY}\nWalterMart,,,,,Nova BBQ,78g,,35,{TODAY}\n"
    upload(client, admin, COLUMNS + feed)
    malls = {m["name"]: m for m in client.get("/api/v1/market/malls").json()}
    assert malls["WalterMart"]["prices"] == 2 and malls["SM"]["prices"] == 0
    found = client.get("/api/v1/market/mall-prices", params={"mall": "waltermart", "q": "piatos"}).json()
    assert found["count"] == 1 and found["results"][0]["store_name"] == "WalterMart Cebu" and found["results"][0]["price"] == 40
    chain = client.get("/api/v1/market/mall-prices", params={"mall": "WalterMart", "q": "nova"}).json()["results"][0]
    assert "branches may differ" in chain["origin"]


def test_branches_group_under_their_chain(client):
    assert client.get("/api/v1/market/mall-prices", params={"mall": "SM"}).json()["count"] == 0
    assert community.chain_of("SM Hypermarket Cebu") == community.chain_of("SM") == "SM"
    assert community.chain_of("SMART Store") == "SMART Store"


def test_location_filter_lists_places_with_prices(client, admin):
    grant(client, admin)
    upload(client, admin, COLUMNS + f"WalterMart,Cebu,10.31,123.89,Cebu City,Piatos Cheese,85g,,40,{TODAY}\nWalterMart,Davao,7.07,125.6,Davao City,Piatos Cheese,85g,,41,{TODAY}\n")
    assert {c["name"] for c in client.get("/api/v1/market/cities").json()} == {"Cebu City", "Davao City"}
    found = client.get("/api/v1/market/mall-prices", params={"mall": "WalterMart", "city": "Davao City"}).json()
    assert [r["store_name"] for r in found["results"]] == ["WalterMart Davao"]
