ITEMS = [{"query": "soy sauce", "quantity": 2}, {"query": "corned beef", "quantity": 3}]


def multi(client, items, **extra):
    response = client.post("/api/v1/products/multi-search", json={"items": items, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def test_each_item_is_resolved(client):
    data = multi(client, ITEMS)
    assert [i["status"] for i in data["items"]] == ["matched", "matched"]
    assert all(i["selected_product_id"] for i in data["items"])


def test_split_basket_is_cheapest_per_item_times_quantity(client):
    data = multi(client, ITEMS)
    expected = sum(i["offers"][0]["price"] * i["quantity"] for i in data["items"])
    assert data["split_basket"]["total"] == round(expected, 2)


def test_store_total_and_savings_are_consistent(client):
    data = multi(client, ITEMS)
    best = data["best_single_store"]
    assert best["items_missing"] == [] and best["total"] == min(
        s["total"] for s in data["stores"] if not s["items_missing"]
    )
    assert data["split_savings"] == round(best["total"] - data["split_basket"]["total"], 2)
    assert data["split_savings"] >= 0


def test_ambiguous_item_never_mixes_package_sizes(client):
    item = multi(client, [{"query": "jasmine rice"}])["items"][0]
    selected = next(c for c in item["candidates"] if c["product_id"] == item["selected_product_id"])
    assert {o["package_size"] for o in item["offers"]} == {selected["package_size"]}
    assert {c["package_size"] for c in item["candidates"]} == {"1 kg", "5 kg"}


def test_user_can_pin_a_specific_product_and_still_see_alternatives(client):
    item = multi(client, [{"query": "jasmine rice"}])["items"][0]
    other = next(c for c in item["candidates"] if c["product_id"] != item["selected_product_id"])
    pinned = multi(client, [{"query": "jasmine rice", "product_id": other["product_id"]}])["items"][0]
    assert pinned["selected_product_id"] == other["product_id"]
    assert {o["product_id"] for o in pinned["offers"]} == {other["product_id"]}
    assert len(pinned["candidates"]) == 2


def test_unknown_item_reported_without_breaking_the_rest(client):
    data = multi(client, [{"query": "soy sauce"}, {"query": "unicorn steak"}])
    assert [i["status"] for i in data["items"]] == ["matched", "no_match"]
    assert data["best_single_store"] is not None


def test_no_savings_claim_when_no_store_has_everything(client, db):
    grocer = db.stores.find_one({"name": "Demo Grocer Mandaue"})["_id"]
    soy = db.products.find_one({"name": "Soy Sauce"})["_id"]
    beef = db.products.find_one({"name": "Corned Beef"})["_id"]
    db.store_products.delete_many({"product_id": soy, "store_id": {"$ne": grocer}})
    db.store_products.delete_many({"product_id": beef, "store_id": grocer})
    data = multi(client, ITEMS)
    assert data["best_single_store"] is None and data["split_savings"] is None
    assert data["split_basket"]["store_count"] == 2


def test_radius_applies_to_baskets(client):
    near = multi(client, ITEMS, latitude=10.3157, longitude=123.8854, radius_km=3)
    assert near["stores"] and all(s["distance_km"] <= 3 for s in near["stores"])


def test_rejects_empty_duplicate_and_oversized_requests(client):
    url = "/api/v1/products/multi-search"
    assert client.post(url, json={"items": []}).status_code == 422
    assert client.post(url, json={"items": [{"query": "  "}]}).status_code == 422
    assert client.post(url, json={"items": [{"query": "a"}, {"query": "A"}]}).status_code == 422
    assert client.post(url, json={"items": [{"query": f"i{n}"} for n in range(31)]}).status_code == 422
    assert client.post(url, json={"items": [{"query": "a", "quantity": 0}]}).status_code == 422
