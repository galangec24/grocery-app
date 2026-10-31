"""The Price Agent: fills prices, keeps going past failures, and signals open apps."""
import pytest

from app import agent, ingestion, live, market
from app.db import utcnow
from sample_data import DEMO_PASSWORD  # noqa: F401
from test_market import SRP_URL, dti_srp, da_dpi, DPI_PDF, SRP_PDF

TODAY = utcnow().date().isoformat()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(market, "ingest", lambda db: None)


class Reply:
    def __init__(self, body, ok=True):
        self.body, self.ok = body, ok

    def raise_for_status(self):
        if not self.ok:
            raise agent.httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        return self.body


class Http:
    def __init__(self, reply):
        self.reply, self.urls, self.headers = reply, [], []

    def get(self, url, headers=None):
        self.urls.append(url)
        self.headers.append(headers)
        return self.reply


@pytest.fixture()
def public_dns(monkeypatch):
    monkeypatch.setattr(agent.socket, "getaddrinfo", lambda *a: [(0, 0, 0, "", ("93.184.216.34", 443))])


def connect(client, admin, source="waltermart", url="https://api.waltermart.example/prices"):
    client.patch(f"/api/v1/admin/sources/{source}", headers=admin, json={"permission": "granted", "notes": "Agreement 2026-10-31", "enabled": True})
    response = client.put(f"/api/v1/admin/sources/{source}/connector", headers=admin, json={"url": url})
    assert response.status_code == 200, response.text


PRICE = {"retailer": "WalterMart", "product": "Piatos Cheese", "size": "85g", "price": 39.75, "verified_at": TODAY}


def test_agent_saves_the_best_price_on_each_product(client, db):
    shelf = dict(name="Jack 'n Jill Piatos Cheese 85g", store_name="SM Hypermarket", latitude=10.31, longitude=123.89, city="Cebu City", price=41)
    client.post("/api/v1/market/shelf-prices", json=shelf)
    run = agent.run_cycle(db, Http(Reply([])))
    item = db.catalog_items.find_one({"name": "Jack 'n Jill Piatos Cheese", "size": "85g"})
    assert item["auto_price"]["price"] == 41 and item["auto_price"]["kind"] == "store"
    assert run["coverage"]["priced"] >= 1 and run["coverage"]["blank"] > 0
    shown = client.get("/api/v1/market/catalog", params={"q": "piatos cheese 85g"}).json()[0]
    assert shown["auto_price"]["label"] == "SM Hypermarket"


def test_agent_never_invents_a_price(client, db):
    agent.run_cycle(db, Http(Reply([])))
    assert db.catalog_items.find_one({"name": "Jack 'n Jill Piatos Cheese"}).get("auto_price") is None


def test_agent_estimates_from_official_items(client, db):
    market.store_report(db, "dti_srp", SRP_URL, dti_srp.parse_bulletin(SRP_PDF))
    agent.run_cycle(db, Http(Reply([])))
    item = db.catalog_items.find_one({"name": "Mega Sardines in Tomato Sauce"})
    assert item["auto_price"]["kind"] == "estimate" and item["auto_price"]["price"] > 0


def test_connector_prices_flow_in_automatically(client, db, admin, public_dns):
    connect(client, admin)
    http = Http(Reply({"items": [PRICE]}))
    run = agent.run_cycle(db, http)
    assert http.urls == ["https://api.waltermart.example/prices"]
    assert db.retail_prices.find_one()["price_centavos"] == 3975
    assert {"source": "WalterMart", "status": "ok", "imported": 1, "rejected": 0} in run["steps"]


def test_connector_token_comes_from_the_environment(client, db, admin, public_dns, monkeypatch):
    connect(client, admin)
    monkeypatch.setenv("SOURCE_WALTERMART_TOKEN", "secret-value")
    http = Http(Reply({"items": []}))
    run = agent.run_cycle(db, http)
    assert http.headers[0] == {"Authorization": "Bearer secret-value"}
    assert "secret-value" not in str(run)


def test_connector_without_permission_is_never_called(client, db, admin, public_dns):
    connect(client, admin)
    client.patch("/api/v1/admin/sources/waltermart", headers=admin, json={"permission": "refused"})
    http = Http(Reply({"items": [PRICE]}))
    agent.run_cycle(db, http)
    assert http.urls == [] and db.retail_prices.count_documents({}) == 0


def test_a_failing_source_does_not_stop_the_run(client, db, admin, public_dns):
    connect(client, admin)
    run = agent.run_cycle(db, Http(Reply({}, ok=False)))
    assert run["status"] == "partial" and run["coverage"]["products"] > 0
    assert agent.status(db)["runs"][0]["status"] == "partial"


def test_failed_official_check_is_recorded(client, db, monkeypatch):
    def boom(db):
        raise RuntimeError("down")

    monkeypatch.setattr(market, "ingest", boom)
    run = agent.run_cycle(db, Http(Reply([])))
    assert run["status"] == "partial" and run["steps"][0]["status"] == "failed"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1"])
def test_connector_cannot_reach_private_addresses(address, monkeypatch):
    monkeypatch.setattr(agent.socket, "getaddrinfo", lambda *a: [(0, 0, 0, "", (address, 443))])
    with pytest.raises(ValueError):
        agent._safe_url("https://internal.example/x")


def test_connector_must_use_https(client, admin):
    response = client.put("/api/v1/admin/sources/waltermart/connector", headers=admin, json={"url": "http://x.example/a"})
    assert response.status_code == 422


def test_only_changes_move_the_live_version(client, db):
    agent.run_cycle(db, Http(Reply([])))
    first = live.state(db)["version"]
    agent.run_cycle(db, Http(Reply([])))
    assert live.state(db)["version"] == first and live.state(db)["checked_at"]


def test_a_shared_price_reaches_open_apps_at_once(client, db):
    before = client.get("/api/v1/market/live").json()["version"]
    client.post("/api/v1/market/shelf-prices", json=dict(name="Piatos", store_name="SM Mart", latitude=10.3, longitude=123.9, city="Cebu City", price=30))
    assert client.get("/api/v1/market/live").json()["version"] == before + 1


def test_new_official_report_moves_the_live_version(client, db, monkeypatch):
    monkeypatch.setattr(market, "ingest", lambda db: market.store_report(db, "da_dpi", "https://da.example/x.pdf", da_dpi.parse_report(DPI_PDF)))
    before = live.state(db)["version"]
    assert agent.run_cycle(db, Http(Reply([])))["data_changed"] is True
    assert live.state(db)["version"] == before + 1


def test_agent_status_is_admin_only(client, admin, supervisor):
    assert client.get("/api/v1/admin/agent", headers=supervisor).status_code == 403
    assert client.get("/api/v1/admin/agent", headers=admin).status_code == 200
