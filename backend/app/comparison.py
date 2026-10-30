"""Search, freshness, ranking and multi-item basket logic (spec sections 8 and 10).

Prices are whole centavos throughout, so totals never pick up floating-point error.
"""
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from pymongo.database import Database

from .config import DEFAULT_FRESH_MINUTES, DEFAULT_STALE_MINUTES, NEARBY_RADIUS_KM
from .db import utcnow

SORTS = {"price_asc", "distance_asc", "best_nearby", "freshness"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance, not road distance; clients must label it as such."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin(math.radians(lat2 - lat1) / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def thresholds_by_org(db: Database) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    for row in db.retailer_integrations.find({"status": {"$ne": "disabled"}}):
        current = result.get(row["organization_id"])
        # With several integrations, the most lenient one governs that retailer's data.
        result[row["organization_id"]] = (
            (row["fresh_minutes"], row["stale_minutes"]) if current is None
            else (max(current[0], row["fresh_minutes"]), max(current[1], row["stale_minutes"]))
        )
    return result


def price_status(listing: dict, organization_id: str, thresholds: dict, now: datetime) -> str:
    if listing["availability_status"] == "unavailable":
        return "unavailable"
    synced = listing.get("last_synced_at")
    if synced is None:
        return "unknown"
    fresh, stale = thresholds.get(organization_id, (DEFAULT_FRESH_MINUTES, DEFAULT_STALE_MINUTES))
    age = (now - synced).total_seconds() / 60
    if age <= fresh:
        return "fresh"
    return "aging" if age <= stale else "stale"


def iso(value: datetime | None) -> str | None:
    return f"{value.isoformat(timespec='seconds')}Z" if value else None


def money(centavos: int) -> float:
    return round(centavos / 100, 2)


def tokenize(text: str) -> list[str]:
    # "1 L" and "1L" must find the same product.
    return re.findall(r"[a-z0-9.]+", re.sub(r"(\d)\s+(?=[a-z])", r"\1", text.lower()))


def haystack(product: dict) -> str:
    size = product["package_size"].lower()
    return " ".join([
        product["name"], product["brand"], product["category"], size, size.replace(" ", ""),
        product.get("barcode") or "", product["_id"],
    ]).lower()


def matches(tokens: list[str], text: str) -> bool:
    # Tolerates a simple plural in the query: "eggs" finds "egg", "oils" finds "oil".
    return all(t in text or (t.endswith("s") and t[:-1] in text) for t in tokens)


def find_products(db: Database, query: str, category_id: str | None = None) -> list[dict]:
    tokens = tokenize(query)
    criteria = {"status": "active"}
    if category_id:
        criteria["category_id"] = category_id
    products = list(db.products.find(criteria))
    return [p for p in products if matches(tokens, haystack(p))] if tokens else products


@dataclass
class Offer:
    listing: dict
    product: dict
    store: dict
    status: str
    distance_km: float | None
    labels: list[str] = field(default_factory=list)

    @property
    def price(self) -> int:
        return self.listing["price_centavos"]

    @property
    def store_id(self) -> str:
        return self.store["_id"]

    @property
    def product_id(self) -> str:
        return self.product["_id"]

    def json(self) -> dict:
        l, p, s = self.listing, self.product, self.store
        return {
            "product_id": p["_id"],
            "product_name": p["name"],
            "brand": p["brand"],
            "package_size": p["package_size"],
            "category": p["category"],
            "image_url": p.get("image_url"),
            "store_id": s["_id"],
            "store_name": s["name"],
            "store_address": s["address"],
            "latitude": s["latitude"],
            "longitude": s["longitude"],
            "price": money(l["price_centavos"]),
            "currency": l["currency"],
            "distance_km": None if self.distance_km is None else round(self.distance_km, 2),
            "availability": l["availability_status"],
            "price_status": self.status,
            "last_synced_at": iso(l.get("last_synced_at")),
            "price_effective_at": iso(l.get("price_effective_at")),
            "labels": self.labels,
        }


def build_offers(db: Database, products: list[dict], latitude=None, longitude=None) -> list[Offer]:
    if not products:
        return []
    by_id = {p["_id"]: p for p in products}
    stores = {s["_id"]: s for s in db.stores.find({"status": "active"})}
    thresholds = thresholds_by_org(db)
    now = utcnow()
    offers = []
    for listing in db.store_products.find({"product_id": {"$in": list(by_id)}}):
        store = stores.get(listing["store_id"])
        if store is None:
            continue
        distance = None
        if latitude is not None and longitude is not None:
            distance = haversine_km(latitude, longitude, store["latitude"], store["longitude"])
        status = price_status(listing, store["organization_id"], thresholds, now)
        offers.append(Offer(listing, by_id[listing["product_id"]], store, status, distance))
    return offers


def is_comparable(offer: Offer) -> bool:
    """Eligible for current-price comparison: not stale, not reported unavailable."""
    return offer.status in {"fresh", "aging"}


def apply_labels(offers: list[Offer]) -> None:
    """Derive labels per canonical product; 1 kg and 5 kg never compete for a label."""
    groups: dict[str, list[Offer]] = defaultdict(list)
    for offer in offers:
        groups[offer.product_id].append(offer)
    for group in groups.values():
        lowest = min(group, key=lambda o: (o.price, o.distance_km or 0))
        lowest.labels.append("Lowest Price")
        located = [o for o in group if o.distance_km is not None]
        if located:
            nearest = min(located, key=lambda o: (o.distance_km, o.price))
            nearest.labels.append("Nearest Store")
            nearby = [o for o in located if o.distance_km <= NEARBY_RADIUS_KM]
            if nearby:
                best = min(nearby, key=lambda o: (o.price, o.distance_km))
                if best is not lowest:
                    best.labels.append("Best Nearby Price")


def sort_offers(offers: list[Offer], sort_by: str) -> list[Offer]:
    far = float("inf")
    if sort_by == "distance_asc":
        key = lambda o: (o.distance_km if o.distance_km is not None else far, o.price)
    elif sort_by == "freshness":
        def key(o):
            synced = o.listing.get("last_synced_at")
            return (-(synced.timestamp() if synced else 0), o.price)
    else:
        key = lambda o: (o.price, o.distance_km if o.distance_km is not None else far)
    return sorted(offers, key=key)


def within_radius(offer: Offer, radius_km: float | None) -> bool:
    return radius_km is None or offer.distance_km is None or offer.distance_km <= radius_km


def split_offers(offers: list[Offer], radius_km: float | None) -> tuple[list[Offer], list[Offer]]:
    """Return (eligible, stale). Stale prices are never ranked with current ones."""
    in_range = [o for o in offers if within_radius(o, radius_km)]
    return [o for o in in_range if is_comparable(o)], [o for o in in_range if o.status == "stale"]


def _by_popularity(groups: dict[str, list[Offer]]) -> list[tuple[str, list[Offer]]]:
    return sorted(groups.items(), key=lambda kv: (-len({o.store_id for o in kv[1]}), min(o.price for o in kv[1])))


def multi_search(db: Database, items: list[dict], latitude, longitude, radius_km) -> dict:
    """Resolve every item to one canonical product, then cost the basket.

    Items resolve to a single exact product because totalling "rice" as 1 kg at one
    store and 5 kg at another would produce a meaningless comparison.
    """
    resolved = []
    for item in items:
        products = find_products(db, item["query"])
        eligible, stale = split_offers(build_offers(db, products, latitude, longitude), radius_km)

        alternatives: dict[str, list[Offer]] = defaultdict(list)
        for offer in eligible:
            alternatives[offer.product_id].append(offer)
        ordered = _by_popularity(alternatives)

        # A pin outside the text matches (say, a renamed query) is still honoured.
        pinned = item.get("product_id")
        if pinned and pinned not in alternatives:
            product = db.products.find_one({"_id": pinned, "status": "active"})
            if product:
                extra, extra_stale = split_offers(build_offers(db, [product], latitude, longitude), radius_km)
                alternatives[pinned] = extra
                stale += extra_stale
                ordered = _by_popularity({k: v for k, v in alternatives.items() if v})

        selected_id = pinned if alternatives.get(pinned) else (ordered[0][0] if ordered else None)
        selected = sort_offers(alternatives.get(selected_id, []), "price_asc")
        apply_labels(selected)
        status = "matched" if selected else ("no_eligible_price" if products or pinned else "no_match")

        resolved.append({
            "query": item["query"],
            "quantity": item["quantity"],
            "status": status,
            "selected_product_id": selected_id,
            "candidates": [
                {
                    "product_id": product_id,
                    "product_name": group[0].product["name"],
                    "brand": group[0].product["brand"],
                    "package_size": group[0].product["package_size"],
                    "min_price": money(min(o.price for o in group)),
                    "store_count": len({o.store_id for o in group}),
                }
                for product_id, group in ordered
            ],
            "offers": selected,
            "stale_offers": [o.json() for o in stale if o.product_id == selected_id],
        })

    stores: dict[str, dict] = {}
    for entry in resolved:
        for offer in entry["offers"]:
            store = stores.setdefault(offer.store_id, {
                "store_id": offer.store_id,
                "store_name": offer.store["name"],
                "distance_km": None if offer.distance_km is None else round(offer.distance_km, 2),
                "lines": {},
            })
            store["lines"][entry["query"]] = offer.price * entry["quantity"]

    matched = [e for e in resolved if e["status"] == "matched"]
    store_rows = [
        {
            "store_id": store["store_id"],
            "store_name": store["store_name"],
            "distance_km": store["distance_km"],
            "total": money(sum(store["lines"].values())),
            "items_found": len(store["lines"]),
            "items_missing": [e["query"] for e in matched if e["query"] not in store["lines"]],
        }
        for store in stores.values()
    ]
    store_rows.sort(key=lambda s: (-s["items_found"], s["total"], s["distance_km"] or 0))

    split_lines, split_total = [], 0
    for entry in matched:
        best = entry["offers"][0]
        line_total = best.price * entry["quantity"]
        split_total += line_total
        split_lines.append({
            "query": entry["query"],
            "product_id": best.product_id,
            "product_name": best.product["name"],
            "package_size": best.product["package_size"],
            "store_id": best.store_id,
            "store_name": best.store["name"],
            "quantity": entry["quantity"],
            "unit_price": money(best.price),
            "line_total": money(line_total),
        })

    complete = [s for s in store_rows if not s["items_missing"]]
    best_single = complete[0] if complete else None
    return {
        "currency": "PHP",
        "items": [{**e, "offers": [o.json() for o in e["offers"]]} for e in resolved],
        "stores": store_rows,
        "best_single_store": best_single,
        "split_basket": {
            "total": money(split_total),
            "store_count": len({line["store_id"] for line in split_lines}),
            "lines": split_lines,
        },
        # Only stated when one store really can supply the whole matched basket.
        "split_savings": round(best_single["total"] - money(split_total), 2) if best_single else None,
    }
