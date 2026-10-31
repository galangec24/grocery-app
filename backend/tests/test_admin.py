"""AC-09 to AC-12, AC-15: imports, isolation, outages and audit."""
import io

import pytest

from app.sync import AdapterError, RetailerAdapter, run_sync

class FakeFeed(RetailerAdapter):
    def __init__(self, db, integration, outage=False):
        self.db, self.integration, self.outage = db, integration, outage

    def fetch(self):
        if self.outage:
            raise AdapterError("Retailer API did not respond (simulated outage)")
        return []


@pytest.fixture(autouse=True)
def fake_connector(monkeypatch):
    monkeypatch.setattr("app.admin.adapter_for", lambda db, i: FakeFeed(db, i, i["provider_name"].endswith("outage")))


HEADER = "store_id,retailer_product_id,price,currency,availability\n"


def csv_file(text):
    return {"file": ("prices.csv", io.BytesIO(text.encode()), "text/csv")}


def setup(db, name="Sample Mart Downtown"):
    store = db.stores.find_one({"name": name})
    listing = db.store_products.find_one({"store_id": store["_id"]})
    integration = db.retailer_integrations.find_one({"organization_id": store["organization_id"]})
    return store, listing, integration


def upload(client, integration, body, headers):
    return client.post("/api/v1/admin/imports/csv", data={"integration_id": integration["_id"]},
                       files=csv_file(body), headers=headers)


def price_of(db, listing):
    return db.store_products.find_one({"_id": listing["_id"]})["price_centavos"]


def test_ac09_csv_import_updates_price_and_history(client, db, admin):
    store, listing, integration = setup(db)
    before = db.price_history.count_documents({"store_product_id": listing["_id"]})
    body = HEADER + f"{store['_id']},{listing['retailer_product_id']},123.45,PHP,available\n"
    job = upload(client, integration, body, admin).json()
    assert job["status"] == "succeeded" and job["records_updated"] == 1
    assert price_of(db, listing) == 12345
    assert db.price_history.count_documents({"store_product_id": listing["_id"]}) == before + 1


def test_new_listing_needs_a_verified_barcode(client, db, admin):
    store, _, integration = setup(db)
    body = "store_id,retailer_product_id,price,currency,barcode\n" + f"{store['_id']},NEW-1,20,PHP,480000000000\n"
    job = upload(client, integration, body, admin).json()
    assert job["records_updated"] == 1 and job["records_rejected"] == 0
    assert db.store_products.find_one({"retailer_product_id": "NEW-1"})["price_centavos"] == 2000


def test_unchanged_price_keeps_effective_time_but_refreshes_sync(client, db, admin):
    store, listing, integration = setup(db)
    price = listing["price_centavos"] / 100
    body = HEADER + f"{store['_id']},{listing['retailer_product_id']},{price},PHP,available\n"
    assert upload(client, integration, body, admin).json()["records_updated"] == 0
    fresh = db.store_products.find_one({"_id": listing["_id"]})
    assert fresh["price_effective_at"] == listing["price_effective_at"]
    assert fresh["last_synced_at"] > listing["last_synced_at"]


def test_ac10_invalid_rows_rejected_valid_rows_kept(client, db, admin):
    store, listing, integration = setup(db)
    pid = listing["retailer_product_id"]
    sid = store["_id"]
    body = HEADER + "\n".join([
        f"{sid},{pid},-5,PHP,available",
        f"{sid},{pid},abc,PHP,available",
        f"{sid},{pid},NaN,PHP,available",
        f"{sid},{pid},1e99,PHP,available",
        f"{sid},{pid},10,USD,available",
        f"not-a-store,{pid},10,PHP,available",
        f"{sid},UNKNOWN-ITEM,10,PHP,available",
        f"{sid}",
    ]) + "\n"
    job = upload(client, integration, body, admin).json()
    assert job["status"] == "succeeded"
    assert job["records_rejected"] == 8 and job["records_updated"] == 0
    assert len(job["rejections"]) == 8
    assert price_of(db, listing) == listing["price_centavos"]


def test_batch_with_valid_and_invalid_rows_applies_only_valid(client, db, admin):
    store, listing, integration = setup(db)
    body = HEADER + f"{store['_id']},{listing['retailer_product_id']},50.00,PHP,available\n{store['_id']},X,-1,PHP,available\n"
    job = upload(client, integration, body, admin).json()
    assert job["records_updated"] == 1 and job["records_rejected"] == 1
    assert price_of(db, listing) == 5000


def test_cannot_import_into_another_organizations_store(client, db, admin):
    foreign, foreign_listing, _ = setup(db, "Demo Grocer Mandaue")
    _, _, integration = setup(db)
    body = HEADER + f"{foreign['_id']},{foreign_listing['retailer_product_id']},1.00,PHP,available\n"
    assert upload(client, integration, body, admin).json()["records_rejected"] == 1
    assert price_of(db, foreign_listing) == foreign_listing["price_centavos"]


def test_bad_csv_header_fails_job_and_keeps_prices(client, db, admin):
    _, listing, integration = setup(db)
    job = upload(client, integration, "wrong,columns\n1,2\n", admin).json()
    assert job["status"] == "failed" and "missing columns" in job["error_summary"]
    assert price_of(db, listing) == listing["price_centavos"]


def test_failure_while_committing_marks_job_failed(client, db, admin, monkeypatch):
    store, listing, integration = setup(db)

    def boom(*args, **kwargs):
        raise RuntimeError("connection string with secret")

    monkeypatch.setattr(db.store_products, "replace_one", boom)
    body = HEADER + f"{store['_id']},{listing['retailer_product_id']},50,PHP,available\n"
    job = upload(client, integration, body, admin).json()
    assert job["status"] == "failed" and job["error_summary"] == "Unexpected import failure"


def test_ac11_supervisor_is_scoped_to_their_organization(client, db, supervisor):
    _, _, own = setup(db)
    _, _, other = setup(db, "Demo Grocer Mandaue")
    assert client.get(f"/api/v1/admin/integrations/{own['_id']}/status", headers=supervisor).status_code == 200
    assert client.get(f"/api/v1/admin/integrations/{other['_id']}/status", headers=supervisor).status_code == 403
    assert client.post(f"/api/v1/admin/integrations/{other['_id']}/sync", headers=supervisor).status_code == 403
    assert client.patch(f"/api/v1/admin/integrations/{other['_id']}", json={"status": "disabled"},
                        headers=supervisor).status_code == 403
    assert upload(client, other, HEADER, supervisor).status_code == 403
    body = dict(organization_id=other["organization_id"], name="Rogue", address="x y", latitude=1, longitude=1)
    assert client.post("/api/v1/admin/stores", json=body, headers=supervisor).status_code == 403
    retailers = client.get("/api/v1/admin/overview", headers=supervisor).json()["retailers"]
    assert {r["organization"] for r in retailers} == {"Sample Mart"}
    jobs = client.get("/api/v1/admin/sync-jobs", headers=supervisor).json()
    assert jobs and {j["organization"] for j in jobs} == {"Sample Mart"}


def test_admin_endpoints_require_authentication(client):
    assert client.get("/api/v1/admin/overview").status_code == 401
    assert client.get("/api/v1/admin/overview", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_refresh_token_is_not_an_access_token(client):
    tokens = client.post("/api/v1/auth/login", json={"email": "admin@demo.local", "password": "demo-password"}).json()
    bad = {"Authorization": f"Bearer {tokens['refresh_token']}"}
    assert client.get("/api/v1/users/me", headers=bad).status_code == 401
    renewed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {renewed['access_token']}"}).status_code == 200


def test_password_hash_never_returned(client, admin):
    assert "password_hash" not in client.get("/api/v1/users/me", headers=admin).json()


def test_only_system_admin_creates_organizations(client, admin, supervisor):
    url = "/api/v1/admin/organizations"
    assert client.post(url, json={"name": "New Org"}, headers=supervisor).status_code == 403
    assert client.post(url, json={"name": "New Org"}, headers=admin).status_code == 201


def test_raw_secrets_refused_in_integration_config(client, db, admin):
    _, _, integration = setup(db)
    body = dict(organization_id=integration["organization_id"], integration_type="api",
                provider_name="vendor", configuration_reference="password=hunter2")
    assert client.post("/api/v1/admin/integrations", json=body, headers=admin).status_code == 422
    body["configuration_reference"] = "secret://vendor/api"
    assert client.post("/api/v1/admin/integrations", json=body, headers=admin).status_code == 201


def test_ac12_ac15_outage_keeps_prices_and_is_retryable(client, db, admin):
    _, listing, integration = setup(db, "Test Supermarket Lapu-Lapu")
    job = client.post(f"/api/v1/admin/integrations/{integration['_id']}/sync", headers=admin).json()
    assert job["status"] == "failed" and "outage" in job["error_summary"]
    assert price_of(db, listing) == listing["price_centavos"]
    integration = db.retailer_integrations.find_one({"_id": integration["_id"]})
    assert integration["status"] == "failed"
    retry = run_sync(db, integration, FakeFeed(db, integration))
    assert retry["status"] == "succeeded"
    assert db.retailer_integrations.find_one({"_id": integration["_id"]})["status"] == "active"


def test_disabled_integration_cannot_sync(client, db, admin):
    _, _, integration = setup(db)
    client.patch(f"/api/v1/admin/integrations/{integration['_id']}", json={"status": "disabled"}, headers=admin)
    assert client.post(f"/api/v1/admin/integrations/{integration['_id']}/sync", headers=admin).status_code == 409


def test_privileged_actions_are_audited(client, db, admin):
    _, _, integration = setup(db)
    client.patch(f"/api/v1/admin/integrations/{integration['_id']}", json={"fresh_minutes": 20}, headers=admin)
    assert db.audit_logs.count_documents({"action": "integration.updated"}) == 1


def test_overview_counts_add_up(client, admin):
    data = client.get("/api/v1/admin/overview", headers=admin).json()
    assert sum(data["freshness"].values()) == data["listings"] and data["freshness"]["stale"] > 0


def test_login_is_rate_limited(client):
    codes = [client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "n"}).status_code for _ in range(11)]
    assert codes[-1] == 429


@pytest.mark.parametrize("value,centavos", [("10", 1000), ("10.5", 1050), ("0.07", 7)])
def test_prices_convert_to_exact_centavos(client, db, admin, value, centavos):
    store, listing, integration = setup(db)
    upload(client, integration, HEADER + f"{store['_id']},{listing['retailer_product_id']},{value},PHP,available\n", admin)
    assert price_of(db, listing) == centavos


NEW_USER = dict(email="new@example.com", full_name="New Person", password="a-long-password", role="system_admin")


def test_admin_creates_and_lists_users_without_hashes(client, admin):
    assert client.post("/api/v1/admin/users", json=NEW_USER, headers=admin).status_code == 201
    users = client.get("/api/v1/admin/users", headers=admin).json()
    assert "new@example.com" in {u["email"] for u in users}
    assert all("password_hash" not in u for u in users)


def test_user_rules(client, db, admin, supervisor):
    url = "/api/v1/admin/users"
    assert client.get(url, headers=supervisor).status_code == 403
    assert client.post(url, json=NEW_USER, headers=supervisor).status_code == 403
    assert client.post(url, json={**NEW_USER, "password": "short"}, headers=admin).status_code == 422
    assert client.post(url, json={**NEW_USER, "role": "owner"}, headers=admin).status_code == 422
    assert client.post(url, json={**NEW_USER, "role": "supervisor"}, headers=admin).status_code == 422
    client.post(url, json=NEW_USER, headers=admin)
    assert client.post(url, json={**NEW_USER, "email": "NEW@example.com"}, headers=admin).status_code == 409


def test_suspended_user_cannot_sign_in_or_use_old_token(client, db, admin, supervisor):
    target = db.users.find_one({"email": "supervisor@demo.local"})
    assert client.patch(f"/api/v1/admin/users/{target['_id']}", json={"status": "suspended"}, headers=admin).status_code == 200
    assert client.get("/api/v1/users/me", headers=supervisor).status_code == 401
    login = {"email": "supervisor@demo.local", "password": "demo-password"}
    assert client.post("/api/v1/auth/login", json=login).status_code == 401


def test_admin_cannot_suspend_themselves(client, db, admin):
    me = client.get("/api/v1/users/me", headers=admin).json()
    assert client.patch(f"/api/v1/admin/users/{me['id']}", json={"status": "suspended"}, headers=admin).status_code == 409


def test_password_reset_is_audited_without_the_password(client, db, admin):
    target = db.users.find_one({"email": "supervisor@demo.local"})
    client.patch(f"/api/v1/admin/users/{target['_id']}", json={"password": "a-brand-new-password"}, headers=admin)
    entry = db.audit_logs.find_one({"action": "user.updated"})
    assert "brand-new" not in entry["detail"] and "password" in entry["detail"]
    login = {"email": "supervisor@demo.local", "password": "a-brand-new-password"}
    assert client.post("/api/v1/auth/login", json=login).status_code == 200


def test_admin_catalog_item_becomes_searchable_and_removable(client, admin, supervisor):
    item = dict(name="Local Brand Tuyo", brand="Local Brand", category="Dried Fish", size="100g")
    url = "/api/v1/admin/catalog"
    assert client.post(url, json=item, headers=supervisor).status_code == 403
    created = client.post(url, json=item, headers=admin).json()
    assert "Local Brand Tuyo" in {c["name"] for c in client.get("/api/v1/market/catalog").json()}
    line = client.post("/api/v1/market/basket", json={"items": [{"query": "local brand tuyo"}]}).json()["lines"][0]
    assert line["status"] == "estimated" and "Rough guide" in line["report"]["origin"]
    assert client.delete(f"{url}/{created['id']}", headers=admin).status_code == 200
    assert "Local Brand Tuyo" not in {c["name"] for c in client.get("/api/v1/market/catalog").json()}


def test_only_system_admin_runs_the_agent(client, admin, supervisor, monkeypatch):
    calls = []
    monkeypatch.setattr("app.admin.agent.run_cycle", lambda db: calls.append(1))
    assert client.post("/api/v1/admin/agent/run", headers=supervisor).status_code == 403
    assert client.post("/api/v1/admin/agent/run", headers=admin).status_code == 202
    assert calls == [1]


def test_admin_estimate_replaces_the_guide_but_never_a_real_price(client, db, admin, supervisor):
    item = client.get("/api/v1/market/catalog", params={"q": "piatos cheese 85g"}).json()[0]
    url = f'/api/v1/admin/catalog/{item["id"]}/estimate'
    assert client.put(url, json={"price": 44}, headers=supervisor).status_code == 403
    assert client.put(url, json={"price": 44}, headers=admin).status_code == 200
    shown = client.get("/api/v1/market/catalog", params={"q": "piatos cheese 85g"}).json()[0]["auto_price"]
    assert shown["price"] == 44 and shown["by_admin"] and "not a store price" in shown["label"]
    line = client.post("/api/v1/market/basket", json={"items": [{"query": "piatos cheese 85g"}]}).json()["lines"][0]
    assert line["status"] == "estimated" and line["unit_price"] == 44
    assert client.get("/api/v1/market/suggest", params={"q": "piatos cheese 85g"}).json()[0]["price"] == 44
    assert client.post("/api/v1/market/best-stores", json={"items": ["piatos cheese 85g"]}).json()["best"] is None
    db.catalog_items.update_one({"_id": item["id"]}, {"$set": {"auto_price": {"price": 41, "kind": "store", "label": "SM", "date": None}}})
    assert client.get("/api/v1/market/catalog", params={"q": "piatos cheese 85g"}).json()[0]["auto_price"]["price"] == 41


def test_clearing_an_estimate_restores_the_guide(client, admin):
    item = client.get("/api/v1/market/catalog", params={"q": "piatos cheese 85g"}).json()[0]
    url = f'/api/v1/admin/catalog/{item["id"]}/estimate'
    client.put(url, json={"price": 44}, headers=admin)
    client.put(url, json={"price": None}, headers=admin)
    assert client.get("/api/v1/market/catalog", params={"q": "piatos cheese 85g"}).json()[0]["auto_price"] == item["auto_price"]
    assert client.put(url, json={"price": -1}, headers=admin).status_code == 422
