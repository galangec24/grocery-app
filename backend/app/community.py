"""Shelf prices reported by shoppers.

No public source publishes prices per store, so shoppers share what they see. Reports
are always labelled as shopper-reported, expire after 30 days, hold no personal data,
and a price far from the others is held back until an administrator reviews it.
"""
import re
from collections import defaultdict
from datetime import timedelta
from statistics import median

from pymongo.database import Database

from . import comparison as cmp
from .db import new_id, utcnow

MAX_AGE_DAYS = 30
OPEN_PRICE_MAX_AGE_DAYS = 365
OUTLIER_FACTOR = 3
MIN_REPORTS_TO_JUDGE = 3


def item_key(name: str) -> str:
    return " ".join(cmp.tokenize(name))


def add_report(db: Database, name: str, store_name: str, latitude: float, longitude: float, city: str, price: float) -> dict:
    key = item_key(name)
    centavos = round(price * 100)
    earlier = [r["price_centavos"] for r in current(db, city) if r["item_key"] == key]
    typical = median(earlier) if len(earlier) >= MIN_REPORTS_TO_JUDGE else None
    flagged = typical is not None and not (typical / OUTLIER_FACTOR <= centavos <= typical * OUTLIER_FACTOR)
    doc = {
        "_id": new_id(), "item_key": key, "item_name": name.strip(), "store_name": store_name.strip(),
        "latitude": latitude, "longitude": longitude, "city": city.strip(), "price_centavos": centavos,
        "status": "flagged" if flagged else "visible", "created_at": utcnow(),
    }
    db.shelf_reports.insert_one(doc)
    return doc


def open_price_reports(db: Database, city: str | None) -> list[dict]:
    """Open Prices records in the same shape. These are older, so they get a longer window."""
    criteria = {"date": {"$gte": utcnow() - timedelta(days=OPEN_PRICE_MAX_AGE_DAYS)}}
    if city:
        criteria["city"] = {"$regex": f"^{re.escape(city.replace(' City', ''))}", "$options": "i"}
    return [
        {**doc, "item_key": item_key(doc["item_name"]), "created_at": doc["date"], "status": "visible", "origin": "Open Prices"}
        for doc in db.open_prices.find(criteria)
    ]


def current(db: Database, city: str | None = None) -> list[dict]:
    """The newest visible report for each item at each store."""
    criteria = {"status": "visible", "created_at": {"$gte": utcnow() - timedelta(days=MAX_AGE_DAYS)}}
    if city:
        criteria["city"] = city
    newest: dict[tuple, dict] = {}
    rows = list(db.shelf_reports.find(criteria).sort("created_at", 1))
    for report in sorted(open_price_reports(db, city) + rows, key=lambda r: r["created_at"]):
        newest[(report["item_key"], report["store_name"], round(report["latitude"], 3))] = report
    return list(newest.values())


def matching(reports: list[dict], query: str) -> list[dict]:
    tokens = cmp.tokenize(query)
    return [r for r in reports if tokens and cmp.matches(tokens, r["item_key"])]


def report_json(report: dict) -> dict:
    return {
        "item_name": report["item_name"], "store_name": report["store_name"], "city": report["city"],
        "origin": report.get("origin", "Shopper report"),
        "latitude": report["latitude"], "longitude": report["longitude"],
        "price": cmp.money(report["price_centavos"]), "reported_at": cmp.iso(report["created_at"]),
    }


def best_stores(db: Database, queries: list[str], city: str | None, latitude, longitude) -> dict:
    """Ranks stores by how much of the list they cover, then by total, then by distance."""
    reports = current(db, city)
    stores: dict[tuple, dict] = {}
    priced = set()
    for query in queries:
        cheapest: dict[tuple, dict] = {}
        for report in matching(reports, query):
            key = (report["store_name"], round(report["latitude"], 3))
            if key not in cheapest or report["price_centavos"] < cheapest[key]["price_centavos"]:
                cheapest[key] = report
        for key, report in cheapest.items():
            priced.add(query)
            store = stores.setdefault(key, {
                "store_name": report["store_name"], "latitude": report["latitude"], "longitude": report["longitude"],
                "lines": [], "total_centavos": 0,
            })
            store["lines"].append({"query": query, **report_json(report)})
            store["total_centavos"] += report["price_centavos"]

    rows = []
    for store in stores.values():
        distance = None
        if latitude is not None and longitude is not None:
            distance = round(cmp.haversine_km(latitude, longitude, store["latitude"], store["longitude"]), 2)
        rows.append({
            "store_name": store["store_name"], "latitude": store["latitude"], "longitude": store["longitude"],
            "total": cmp.money(store["total_centavos"]), "items_found": len(store["lines"]),
            "distance_km": distance, "lines": store["lines"],
        })
    rows.sort(key=lambda s: (-s["items_found"], s["total"], s["distance_km"] or 0))
    return {
        "best": rows[0] if rows else None, "stores": rows[:10], "items_total": len(queries),
        "items_priced": len(priced), "generated_at": cmp.iso(utcnow()),
    }


def lowest_by_query(reports: list[dict], query: str) -> dict | None:
    found = matching(reports, query)
    return min(found, key=lambda r: r["price_centavos"]) if found else None


def history(db: Database, barcode: str | None, name: str) -> list[dict]:
    """Every known price for a product, oldest first, for its chart."""
    key = item_key(name)
    points = []
    if barcode:
        points += [
            {"date": cmp.iso(d["date"]), "price": cmp.money(d["price_centavos"]), "store": d["store_name"], "origin": "Open Prices"}
            for d in db.open_prices.find({"barcode": barcode})
        ]
    points += [
        {"date": cmp.iso(r["created_at"]), "price": cmp.money(r["price_centavos"]), "store": r["store_name"], "origin": "Shopper report"}
        for r in db.shelf_reports.find({"item_key": key, "status": "visible"})
    ]
    return sorted(points, key=lambda p: p["date"])


def summary_by_item(reports: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for report in reports:
        grouped[report["item_key"]].append(report)
    return {key: min(group, key=lambda r: r["price_centavos"]) for key, group in grouped.items()}
