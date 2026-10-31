"""The Price Agent: checks every permitted source, then fills in and refreshes prices.

It runs by itself inside the backend, and on demand from the dashboard or with:

    python -m app.agent

Every price it saves is traceable to a source. A product with no evidence stays blank,
and the coverage report says how many, because a guessed price is worse than none.
"""
import ipaddress
import logging
import os
import re
import socket
from urllib.parse import urlparse

import httpx
from pymongo.database import Database

from . import comparison as cmp
from . import community, ingestion, live, market, proofs
from . import search as meaning
from .db import new_id, utcnow

log = logging.getLogger("grocery.agent")
HEADERS = {"User-Agent": "GroceryPriceFinder/1.0 (+https://github.com/galangec24/grocery-app)"}
HISTORY = 50


def _safe_url(url: str) -> str:
    """Connectors are set by administrators, but must never reach private addresses."""
    parts = urlparse(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("connector address must use https")
    for info in socket.getaddrinfo(parts.hostname, 443):
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise ValueError("connector address must be public")
    return url


def fetch_connector(source: dict, http: httpx.Client) -> list[dict]:
    """Reads a retailer's JSON price API. Field names match the CSV feed columns."""
    connector = source["connector"]
    token = os.getenv(f'SOURCE_{re.sub(r"[^A-Z0-9]", "_", source["_id"].upper())}_TOKEN')
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = http.get(_safe_url(connector["url"]), headers=headers)
    response.raise_for_status()
    data = response.json()
    rows = data.get(connector.get("items_key") or "items", []) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("connector did not return a list of prices")
    return [{k: "" if v is None else str(v) for k, v in row.items()} for row in rows if isinstance(row, dict)]


def run_connectors(db: Database, http: httpx.Client) -> list[dict]:
    results = []
    for source in db.price_sources.find({"connector.url": {"$exists": True}}):
        if not ingestion.can_run(db, source["_id"]):
            continue
        try:
            outcome = ingestion.import_rows(db, source["_id"], fetch_connector(source, http))
            results.append({"source": source["name"], "status": "ok", "imported": outcome["imported"], "rejected": outcome["rejected"]})
        except Exception as error:
            log.warning("connector %s failed: %s", source["_id"], type(error).__name__)
            results.append({"source": source["name"], "status": "failed", "error": type(error).__name__})
    return results


def fingerprint(db: Database) -> tuple:
    """Changes whenever the price data does."""
    newest = lambda collection, field: (lambda d: d[field] if d else None)(collection.find_one(sort=[(field, -1)]))
    return (
        db.market_prices.count_documents({}), newest(db.market_prices, "report_date"),
        db.open_prices.count_documents({}), db.retail_prices.count_documents({}),
        newest(db.retail_prices, "verified_at"),
    )


def best_price(reports: list[dict], rows: list[dict], name: str) -> dict | None:
    seen = community.lowest_by_query(reports, name)
    if seen:
        return {
            "price": cmp.money(seen["price_centavos"]), "kind": "store",
            "label": seen["store_name"], "date": cmp.iso(seen["created_at"]),
        }
    guess = meaning.estimate(rows, name)
    if guess:
        return {"price": guess["price"], "kind": "estimate", "label": f'Estimate from {guess["count"]} similar official items', "date": None}
    return None


def fill_prices(db: Database) -> dict:
    """Saves the best supported price on every catalog product."""
    reports = community.current(db)
    rows = market.price_rows(db)
    filled = changed = total = 0
    for doc in db.catalog_items.find({"status": "active"}, {"name": 1, "size": 1, "auto_price": 1}):
        total += 1
        found = best_price(reports, rows, f'{doc["name"]} {doc["size"]}')
        filled += found is not None
        if found != doc.get("auto_price"):
            db.catalog_items.update_one({"_id": doc["_id"]}, {"$set": {"auto_price": found}})
            changed += 1
    return {"products": total, "priced": filled, "blank": total - filled, "updated": changed}


def run_cycle(db: Database, http: httpx.Client | None = None) -> dict:
    """One full pass. A failing source is recorded and never stops the others."""
    run = {"_id": new_id(), "started_at": utcnow(), "steps": [], "status": "ok"}
    before = fingerprint(db)
    try:
        market.ingest(db)
        run["steps"].append({"source": "Official prices and Open Prices", "status": "ok"})
    except Exception as error:
        run["status"] = "partial"
        run["steps"].append({"source": "Official prices and Open Prices", "status": "failed", "error": type(error).__name__})

    client = http or httpx.Client(headers=HEADERS, timeout=45)
    try:
        connector_results = run_connectors(db, client)
    finally:
        if http is None:
            client.close()
    run["steps"] += connector_results
    if any(step["status"] == "failed" for step in connector_results):
        run["status"] = "partial"

    run["photos_removed"] = proofs.purge_photos(db)
    run["coverage"] = fill_prices(db)
    run["data_changed"] = fingerprint(db) != before or run["coverage"]["updated"] > 0
    run["finished_at"] = utcnow()
    if run["data_changed"]:
        live.bump(db)
    live.checked(db)
    db.agent_runs.insert_one(run)
    for old in list(db.agent_runs.find({}, {"_id": 1}).sort("started_at", -1).skip(HISTORY)):
        db.agent_runs.delete_one({"_id": old["_id"]})
    return run


def status(db: Database) -> dict:
    runs = list(db.agent_runs.find().sort("started_at", -1).limit(10))
    return {
        "live": live.state(db),
        "coverage": runs[0]["coverage"] if runs else None,
        "runs": [{
            "started_at": cmp.iso(r["started_at"]), "finished_at": cmp.iso(r.get("finished_at")), "status": r["status"],
            "data_changed": r.get("data_changed", False), "steps": r["steps"], "coverage": r.get("coverage"),
        } for r in runs],
    }


def main() -> None:
    from .db import database, ensure_indexes
    from . import catalog

    logging.basicConfig(level=logging.INFO)
    ensure_indexes(database)
    catalog.seed(database)
    ingestion.seed(database)
    run = run_cycle(database)
    coverage = run["coverage"]
    print(f'Price Agent finished: {run["status"]}')
    for step in run["steps"]:
        print(f'  {step["source"]}: {step["status"]}')
    print(f'  Products: {coverage["products"]}, priced: {coverage["priced"]}, no evidence yet: {coverage["blank"]}')
    print(f'  Prices updated this run: {coverage["updated"]}')


if __name__ == "__main__":
    main()
