"""Products and prices from the Open Food Facts family of open databases (ODbL).

Search there is rate limited, so products are copied into our database in small batches
and shoppers search our copy. A busy response just ends the batch; the saved page number
lets the next run continue where this one stopped.
"""
import logging
from datetime import datetime, timedelta

import httpx
from pymongo.database import Database

from ..db import utcnow

log = logging.getLogger("grocery.open_data")
HEADERS = {"User-Agent": "GroceryPriceFinder/1.0 (+https://github.com/galangec24/grocery-app)"}
SITES = {
    "food": ("world.openfoodfacts.org", "Food & Groceries"),
    "pet": ("world.openpetfoodfacts.org", "Pet Supplies"),
    "beauty": ("world.openbeautyfacts.org", "Beauty & Fragrance"),
    "products": ("world.openproductsfacts.org", "Household & Other"),
}
PAGE_SIZE = 100
REFRESH_DAYS = 7
PRICES_URL = "https://prices.openfoodfacts.org/api/v1/prices"
FIELDS = "code,product_name,brands,quantity,categories_tags,image_small_url"


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _category(tags: list | None, fallback: str) -> str:
    for tag in reversed(tags or []):
        if isinstance(tag, str) and tag.startswith("en:"):
            return tag[3:].replace("-", " ").title()
    return fallback


def product_doc(raw: dict, site: str) -> dict | None:
    """A catalog entry, or None when the record has no usable name or barcode."""
    code = _clean(raw.get("code"))
    name = _clean(raw.get("product_name"))
    if not code or len(name) < 2:
        return None
    brand = _clean(raw.get("brands")).split(",")[0].strip()
    size = _clean(raw.get("quantity"))[:40]
    full_name = name if not brand or brand.lower() in name.lower() else f"{brand} {name}"
    category = _category(raw.get("categories_tags"), SITES[site][1])
    return {
        "_id": f"off:{code}", "name": full_name[:160], "brand": brand[:80], "category": category[:80], "size": size,
        "variant": "", "barcode": code, "image_url": raw.get("image_small_url"), "source": "open-data", "status": "active",
        "keywords": f"{full_name} {size} {category} {SITES[site][1]} {code}".lower(),
        "synced_at": utcnow(),
    }


def sync_product_page(db: Database, http: httpx.Client, site: str) -> bool:
    """Copies one page. Returns False when there is nothing to do or the service is busy."""
    state = db.sync_state.find_one({"_id": site}) or {"page": 1, "finished_at": None}
    finished = state.get("finished_at")
    if finished and utcnow() - finished < timedelta(days=REFRESH_DAYS):
        return False
    response = http.get(f"https://{SITES[site][0]}/api/v2/search", params={
        "countries_tags_en": "philippines", "page_size": PAGE_SIZE, "page": state["page"], "fields": FIELDS,
    })
    if response.status_code in (429, 503):
        log.info("%s is busy; will resume at page %s", site, state["page"])
        return False
    response.raise_for_status()
    products = response.json().get("products", [])
    for raw in products:
        doc = product_doc(raw, site)
        if doc:
            hidden = db.catalog_items.find_one({"_id": doc["_id"], "status": "hidden"}, {"_id": 1})
            if not hidden:  # An administrator's removal stays removed.
                db.catalog_items.replace_one({"_id": doc["_id"]}, doc, upsert=True)
    done = len(products) < PAGE_SIZE
    db.sync_state.replace_one({"_id": site}, {
        "_id": site, "page": 1 if done else state["page"] + 1,
        "finished_at": utcnow() if done else None, "updated_at": utcnow(),
    }, upsert=True)
    return not done


def price_doc(raw: dict) -> dict | None:
    """Standard-price records only. Discounts, weighed goods and unlocated prices are skipped."""
    location = raw.get("location") or {}
    product = raw.get("product") or {}
    if raw.get("price_is_discounted") or raw.get("price_per") or not raw.get("product_code"):
        return None
    if location.get("osm_lat") is None or location.get("osm_lon") is None or not raw.get("price"):
        return None
    name = _clean(product.get("product_name"))
    if not name:
        return None
    brand = _clean(product.get("brands")).split(",")[0].strip()
    size = _clean(product.get("quantity"))
    label = name if not brand or brand.lower() in name.lower() else f"{brand} {name}"
    return {
        "_id": raw["id"], "barcode": raw["product_code"], "item_name": f"{label} {size}".strip(),
        "price_centavos": round(float(raw["price"]) * 100),
        "date": datetime.fromisoformat(raw["date"]),
        "store_name": _clean(location.get("osm_name")) or "Unnamed store",
        "city": _clean(location.get("osm_address_city")),
        "latitude": float(location["osm_lat"]), "longitude": float(location["osm_lon"]),
    }


def sync_prices(db: Database, http: httpx.Client) -> int:
    page, stored = 1, 0
    while True:
        response = http.get(PRICES_URL, params={"currency": "PHP", "size": 100, "page": page, "order_by": "-date"})
        response.raise_for_status()
        data = response.json()
        for raw in data.get("items", []):
            doc = price_doc(raw)
            if doc:
                db.open_prices.replace_one({"_id": doc["_id"]}, doc, upsert=True)
                stored += 1
        if page >= data.get("pages", 1):
            return stored
        page += 1


def status(db: Database) -> dict:
    return {
        "products": db.catalog_items.count_documents({"source": "open-data"}),
        "open_prices": db.open_prices.count_documents({}),
        "shopper_prices": db.shelf_reports.count_documents({"status": "visible"}),
        "sites": [
            {"site": s["_id"], "page": s["page"], "finished_at": s.get("finished_at").isoformat() if s.get("finished_at") else None}
            for s in db.sync_state.find()
        ],
    }


