"""Retail Grocery Product Data Integration Layer.

Every price source is registered here with its type and permission status, and nothing
is imported from a source that hasn't granted permission. Each price records its
retailer, product size, when it was last verified, and its scope: a price for one
branch, or a chain or online price that does not apply to every branch.
"""
import csv
import io
from datetime import datetime, timedelta

from fastapi import HTTPException
from pymongo.database import Database

from . import comparison as cmp
from . import live
from .db import new_id, utcnow

KINDS = {"manual", "retailer_api", "retailer_feed", "retailer_website", "comparison_site", "open_data", "government", "community"}
PERMISSIONS = {"open_license", "granted", "pending", "refused"}
USABLE = {"open_license", "granted"}
MAX_PRICE_AGE_DAYS = 30
MAX_STORED_REJECTIONS = 50
REQUIRED_COLUMNS = {"retailer", "product", "size", "price", "verified_at"}

SOURCES = [
    ("dti-srp", "DTI SRP Bulletin", "government", "open_license", True, "https://www.dti.gov.ph/konsyumer/", "Official standard prices."),
    ("da-dpi", "DA Daily Price Index", "government", "open_license", True, "https://www.da.gov.ph/price-monitoring/", "Metro Manila wet market averages."),
    ("open-food-facts", "Open Food Facts", "open_data", "open_license", True, "https://world.openfoodfacts.org/terms-of-use", "Product catalog under ODbL."),
    ("open-prices", "Open Prices", "open_data", "open_license", True, "https://prices.openfoodfacts.org", "Crowdsourced store prices under ODbL."),
    ("shoppers", "Shopper reports", "community", "granted", True, "", "Prices shoppers choose to share."),
    ("budolista", "Budolista", "comparison_site", "pending", False, "https://budolista.ph/terms",
     "Terms allow personal, non-commercial use only. Needs written permission from Baptiste Group."),
    ("manual", "Admin price updates", "manual", "granted", True, "", "Prices entered by administrators."),
    ("sm-markets", "SM Markets", "retailer_website", "pending", False, "https://smmarkets.ph/robots.txt",
     "Product pages are public, but prices vary by branch and use needs SM's permission. Needs a partnership or a data feed."),
    ("waltermart", "WalterMart", "retailer_website", "pending", False, "", "Needs a partnership or written permission."),
    ("metromart", "MetroMart", "retailer_website", "pending", False, "", "Needs a partnership or written permission."),
]


def seed(db: Database) -> None:
    for source_id, name, kind, permission, enabled, terms_url, notes in SOURCES:
        if not db.price_sources.find_one({"_id": source_id}):
            db.price_sources.insert_one({
                "_id": source_id, "name": name, "kind": kind, "permission": permission, "enabled": enabled,
                "terms_url": terms_url, "notes": notes, "last_import_at": None, "created_at": utcnow(),
            })
        elif permission == "pending":
            db.price_sources.update_one({"_id": source_id, "permission": "pending"}, {"$set": {"notes": notes}})


def can_run(db: Database, source_id: str) -> bool:
    """The single gate every import passes through."""
    source = db.price_sources.find_one({"_id": source_id})
    return bool(source and source["enabled"] and source["permission"] in USABLE)


def source_json(db: Database, source: dict) -> dict:
    return {
        "id": source["_id"], "name": source["name"], "kind": source["kind"], "permission": source["permission"],
        "enabled": source["enabled"], "terms_url": source["terms_url"], "notes": source["notes"],
        "can_run": source["enabled"] and source["permission"] in USABLE,
        "prices": db.retail_prices.count_documents({"source_id": source["_id"]}),
        "last_import_at": cmp.iso(source.get("last_import_at")),
        "connector_url": (source.get("connector") or {}).get("url"),
    }


def create_source(db: Database, name: str, kind: str, terms_url: str, notes: str) -> dict:
    if kind not in KINDS:
        raise HTTPException(422, "Unknown source type")
    source = {
        "_id": new_id(), "name": name.strip(), "kind": kind, "permission": "pending", "enabled": False,
        "terms_url": terms_url, "notes": notes, "last_import_at": None, "created_at": utcnow(),
    }
    db.price_sources.insert_one(source)
    return source


def set_connector(db: Database, source_id: str, url: str, items_key: str) -> dict:
    source = db.price_sources.find_one({"_id": source_id})
    if source is None:
        raise HTTPException(404, "Source not found")
    if not url.startswith("https://"):
        raise HTTPException(422, "Connector address must start with https://")
    connector = {"url": url, "items_key": items_key}
    db.price_sources.update_one({"_id": source_id}, {"$set": {"connector": connector}})
    source["connector"] = connector
    return source


def update_source(db: Database, source_id: str, permission: str | None, enabled: bool | None, notes: str | None) -> dict:
    source = db.price_sources.find_one({"_id": source_id})
    if source is None:
        raise HTTPException(404, "Source not found")
    changes = {k: v for k, v in {"permission": permission, "enabled": enabled, "notes": notes}.items() if v is not None}
    final_permission = changes.get("permission", source["permission"])
    if changes.get("permission") == "granted" and not (notes or "").strip():
        raise HTTPException(422, "Record who granted permission and when in the notes")
    if changes.get("enabled") and final_permission not in USABLE:
        raise HTTPException(409, "A source can only be turned on after permission is granted")
    if final_permission not in USABLE:
        changes["enabled"] = False
    if changes:
        db.price_sources.update_one({"_id": source_id}, {"$set": changes})
        source.update(changes)
    return source


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=None) - (parsed.utcoffset() or timedelta(0))


def _row(row: dict, source_id: str, now: datetime) -> tuple[dict | None, str | None]:
    field = lambda name: (row.get(name) or "").strip()
    for name in ("retailer", "product", "size"):
        if not field(name):
            return None, f"{name} is required"
    try:
        price = float(field("price"))
    except ValueError:
        return None, "price is not a number"
    if not 0 < price <= 999999 or price != price:
        return None, "price must be above zero"
    try:
        verified = _parse_time(field("verified_at"))
    except ValueError:
        return None, "verified_at must be a date, like 2026-10-31"
    if verified > now + timedelta(days=1):
        return None, "verified_at is in the future"
    branch = field("branch")
    latitude, longitude = field("latitude"), field("longitude")
    try:
        lat = float(latitude) if latitude else None
        lon = float(longitude) if longitude else None
    except ValueError:
        return None, "latitude and longitude must be numbers"
    if (lat is None) != (lon is None) or (lat is not None and not (4 <= lat <= 22 and 116 <= lon <= 127.5)):
        return None, "latitude and longitude must both be set, inside the Philippines"
    if lat is not None and not branch:
        return None, "a location needs a branch name"
    return {
        "source_id": source_id, "retailer": field("retailer"), "branch": branch or None,
        # A price without a named branch is never treated as true for every branch.
        "scope": "branch" if branch else "chain",
        "product": field("product"), "size": field("size"), "barcode": field("barcode") or None,
        "price_centavos": round(price * 100), "currency": "PHP", "verified_at": verified, "imported_at": now,
        "latitude": lat, "longitude": lon, "city": field("city") or None, "url": field("url") or None,
    }, None


def import_feed(db: Database, source_id: str, content: bytes) -> dict:
    if not can_run(db, source_id):
        raise HTTPException(403, "This source doesn't have permission to supply prices yet")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        raise HTTPException(422, "File is not a valid UTF-8 CSV")
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise HTTPException(422, f"CSV is missing columns: {', '.join(sorted(missing))}")

    return import_rows(db, source_id, rows)


def import_rows(db: Database, source_id: str, rows: list[dict]) -> dict:
    """Validates and stores prices from any feed or connector."""
    if not can_run(db, source_id):
        raise HTTPException(403, "This source doesn't have permission to supply prices yet")
    now = utcnow()
    imported, rejections = 0, []
    for number, row in enumerate(rows, start=2):  # Row 1 is the header.
        record, reason = _row(row, source_id, now)
        if record is None:
            rejections.append({"row": number, "reason": reason})
            continue
        key = {k: record[k] for k in ("source_id", "retailer", "branch", "product", "size")}
        db.retail_prices.update_one(key, {"$set": record, "$setOnInsert": {"_id": new_id()}}, upsert=True)
        imported += 1
    db.price_sources.update_one({"_id": source_id}, {"$set": {"last_import_at": now}})
    if imported:
        live.bump(db)
    return {"rows": len(rows), "imported": imported, "rejected": len(rejections), "rejections": rejections[:MAX_STORED_REJECTIONS]}


def feed_reports(db: Database, city: str | None) -> list[dict]:
    """Current prices shaped as store reports. Chain prices carry no location."""
    cutoff = utcnow() - timedelta(days=MAX_PRICE_AGE_DAYS)
    usable = {s["_id"]: s for s in db.price_sources.find({"enabled": True, "permission": {"$in": list(USABLE)}})}
    reports = []
    for row in db.retail_prices.find({"verified_at": {"$gte": cutoff}, "source_id": {"$in": list(usable)}}):
        if row["scope"] == "branch" and city and row.get("city") and row["city"].lower() != city.lower():
            continue
        store = f'{row["retailer"]} {row["branch"]}' if row["branch"] else row["retailer"]
        name = f'{row["product"]} {row["size"]}'
        reports.append({
            "item_key": " ".join(cmp.tokenize(name)), "item_name": name, "store_name": store, "retailer": row["retailer"],
            "city": row.get("city") or "", "latitude": row["latitude"], "longitude": row["longitude"],
            "price_centavos": row["price_centavos"], "created_at": row["verified_at"], "status": "visible",
            "origin": "Branch price" if row["scope"] == "branch" else f'{row["retailer"]} chain price, branches may differ',
        })
    return reports
