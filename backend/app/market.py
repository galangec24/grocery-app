"""Official Philippine price data: DTI SRPs (nationwide) and DA prevailing prices (NCR).

Every price stored here comes from a government publication and keeps its source URL
and report date. Nothing is estimated, and a report that fails validation is discarded
so the previous good report stays in place.
"""
import logging
import re
import time
from collections import defaultdict
from datetime import timedelta

import httpx
from pymongo.database import Database

from . import community, estimates, ingestion
from . import search as meaning
from . import comparison as cmp
from .db import client, new_id, supports_transactions, utcnow
from .sources import da_dpi, dti_srp, open_data

log = logging.getLogger("grocery.market")
HEADERS = {"User-Agent": "GroceryPriceFinder/1.0 (+https://github.com/galangec24/grocery-app)"}
SOURCES = {  # In display order: fresh food and staples first.
    "da_dpi": {
        "label": "DA Daily Price Index", "kind": "prevailing",
        "coverage": "Average seen in covered Metro Manila wet markets",
        "home": da_dpi.LISTING_URL,
    },
    "dti_srp": {
        "label": "DTI Suggested Retail Price", "kind": "srp",
        "coverage": "Nationwide, supermarkets and wet markets, unless the item says otherwise",
        "home": "https://www.dti.gov.ph/konsyumer/latest-srps-basic-necessities-prime-commoditie",
    },
}
BACKFILL_REPORTS = 14
TREND_POINTS = 14
RETAIN_DAYS = 90
ROWS_CACHE_SECONDS = 60
_rows_cache: dict = {}
_image_cache: dict = {}


def _slug(*parts: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", " ".join(p for p in parts if p).lower()).strip("-")


def store_report(db: Database, source: str, url: str, parsed: dict) -> int:
    """Replace one report in a single step; a revised report overwrites its date."""
    report_date = parsed["report_date"].isoformat()
    seen: dict[str, int] = defaultdict(int)
    docs = []
    for row in parsed["rows"]:
        slug = _slug(row["commodity"], row["specification"])
        seen[slug] += 1
        if seen[slug] > 1:
            slug = f"{slug}-{seen[slug]}"
        key = f"{source}:{slug}"
        docs.append({
            "_id": f"{key}:{report_date}", "key": key, "source": source, "report_date": report_date,
            "group": row["group"], "category": row["category"], "commodity": row["commodity"],
            "specification": row["specification"], "unit": row["unit"],
            "price_centavos": row["price_centavos"], "source_url": url,
        })

    def replace(session=None):
        db.market_prices.delete_many({"source": source, "report_date": report_date}, session=session)
        db.market_prices.insert_many(docs, session=session)

    if supports_transactions():
        with client.start_session() as session:
            session.with_transaction(replace)
    else:
        replace()
    return len(docs)


def _record(db: Database, source: str, url: str, status: str, report_date=None, rows=0, error=None) -> None:
    db.market_reports.replace_one({"_id": url}, {
        "_id": url, "source": source, "status": status, "report_date": report_date,
        "rows": rows, "error": error, "checked_at": utcnow(),
    }, upsert=True)


def _ingest_pdf(db: Database, http: httpx.Client, source: str, url: str, parse) -> None:
    known = db.market_reports.find_one({"_id": url})
    if known and known["status"] == "ok":
        return
    try:
        response = http.get(url)
        response.raise_for_status()
        parsed = parse(response.content)
        rows = store_report(db, source, url, parsed)
        _record(db, source, url, "ok", parsed["report_date"].isoformat(), rows)
        log.info("stored %s %s (%d rows)", source, parsed["report_date"], rows)
    except Exception as error:
        log.warning("skipped %s: %s", url, error)
        _record(db, source, url, "failed", error=f"{type(error).__name__}: {error}"[:300])


def ingest(db: Database) -> None:
    """Fetch anything new. A failed source never touches stored prices."""
    with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True) as http:
        try:
            listing = http.get(dti_srp.LISTING_URL)
            listing.raise_for_status()
            _ingest_pdf(db, http, "dti_srp", dti_srp.latest_bulletin_url(listing.content), dti_srp.parse_bulletin)
        except Exception as error:
            log.warning("DTI check failed: %s", error)
            _record(db, "dti_srp", dti_srp.LISTING_URL, "failed", error=f"{type(error).__name__}: {error}"[:300])
        try:
            listing = http.get(da_dpi.LISTING_URL)
            listing.raise_for_status()
            for url in da_dpi.daily_report_urls(listing.text)[:BACKFILL_REPORTS]:
                _ingest_pdf(db, http, "da_dpi", url, da_dpi.parse_report)
        except Exception as error:
            log.warning("DA check failed: %s", error)
            _record(db, "da_dpi", da_dpi.LISTING_URL, "failed", error=f"{type(error).__name__}: {error}"[:300])

    try:
        if ingestion.can_run(db, "open-prices"):
            with httpx.Client(headers=open_data.HEADERS, timeout=45, follow_redirects=True) as http:
                open_data.sync_prices(db, http)
    except Exception as error:
        log.warning("Open Prices check failed: %s", error)

    cutoff = (utcnow() - timedelta(days=RETAIN_DAYS)).date().isoformat()
    db.market_prices.delete_many({"source": "da_dpi", "report_date": {"$lt": cutoff}})


def latest_date(db: Database, source: str) -> str | None:
    newest = db.market_prices.find_one({"source": source}, sort=[("report_date", -1)])
    return newest["report_date"] if newest else None


def row_region(doc: dict) -> str:
    if doc["source"] == "da_dpi":
        return "Metro Manila"
    text = doc["commodity"]
    has_vis_min = bool(re.search(r"visayas|mindanao", text, re.I))
    if re.search(r"luzon", text, re.I) and not has_vis_min:
        return "Luzon"
    return "Visayas and Mindanao" if has_vis_min else "Nationwide"


def _applies(doc: dict, island: str | None) -> bool:
    region = row_region(doc)
    if island is None or region in {"Nationwide", "Metro Manila"}:
        return True
    return (region == "Luzon") == (island == "Luzon")


def _row(doc: dict, history: list[dict]) -> dict:
    price = doc["price_centavos"]
    previous = history[-2]["price_centavos"] if len(history) > 1 else None
    change = price - previous if previous is not None else None
    meta = SOURCES[doc["source"]]
    return {
        "id": doc["key"], "source": doc["source"], "source_label": meta["label"], "kind": meta["kind"],
        "group": doc["group"], "category": doc["category"], "commodity": doc["commodity"],
        "specification": doc["specification"], "unit": doc["unit"], "region": row_region(doc),
        "price": cmp.money(price),
        "previous_price": cmp.money(previous) if previous is not None else None,
        "change": cmp.money(change) if change is not None else None,
        "change_pct": round(change / previous * 100, 1) if previous else None,
        "report_date": doc["report_date"], "source_url": doc["source_url"],
        "trend": [cmp.money(h["price_centavos"]) for h in history[-TREND_POINTS:]],
    }


def cached_rows(db: Database, island: str | None) -> list[dict]:
    """Search-as-you-type asks on every keystroke, so official prices are held briefly."""
    stamp, rows = _rows_cache.get(island, (0, []))
    if time.monotonic() - stamp > ROWS_CACHE_SECONDS or not rows:
        rows = price_rows(db, None, island)
        _rows_cache[island] = (time.monotonic(), rows)
    return rows


def reset_caches() -> None:
    _rows_cache.clear()
    _image_cache.clear()


def price_rows(db: Database, source: str | None = None, island: str | None = None) -> list[dict]:
    rows = []
    for name in ([source] if source else list(SOURCES)):
        date = latest_date(db, name)
        if date is None:
            continue
        history: dict[str, list[dict]] = defaultdict(list)
        for doc in db.market_prices.find(
            {"source": name, "price_centavos": {"$ne": None}}, {"key": 1, "price_centavos": 1, "report_date": 1},
        ).sort("report_date", 1):
            history[doc["key"]].append(doc)
        for doc in db.market_prices.find({"source": name, "report_date": date, "price_centavos": {"$ne": None}}):
            if _applies(doc, island):
                rows.append(_row(doc, history[doc["key"]]))
    return rows


def _text(row: dict) -> str:
    return " ".join([row["commodity"], row["specification"], row["category"], row["group"] or ""]).lower()


def search_rows(db: Database, rows: list[dict], query: str) -> list[dict]:
    groups = meaning.expand(db, query)
    if not groups:
        return rows
    found = [r for r in rows if meaning.fits(groups, _text(r))]
    return sorted(found, key=lambda r: -meaning.score(groups, r["commodity"]))


def aisles(db: Database, limit: int = 10) -> list[dict]:
    """The biggest product groups right now, so browsing follows the data."""
    counts: dict[str, int] = defaultdict(int)
    for doc in db.catalog_items.find({"status": "active"}, {"category": 1}).limit(20000):
        counts[doc["category"]] += 1
    for row in price_rows(db):
        counts[row["category"]] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"name": name, "count": count} for name, count in ranked[:limit]]


def suggestions(db: Database, query: str, island: str | None, city: str | None, limit: int) -> list[dict]:
    """What the search bar shows as the shopper types: product, picture and best price."""
    groups = meaning.expand(db, query)
    if not groups:
        return []
    rows = cached_rows(db, island)
    hits = [r for r in rows if meaning.fits(groups, _text(r))]
    hits.sort(key=lambda r: (-meaning.score(groups, r["commodity"]), r["price"]))
    reports = community.current(db, city)
    products = list(db.catalog_items.find(meaning.catalog_criteria(groups)).limit(120))
    products.sort(key=lambda p: (-meaning.score(groups, p["name"]), not p.get("image_url"), p["name"]))

    results = [{
        "id": r["id"], "kind": "official", "name": r["commodity"], "size": r["specification"], "category": r["category"],
        "image_url": image_for(db, r["commodity"]), "price": r["price"], "unit": r["unit"],
        "price_label": r["source_label"], "price_id": r["id"],
    } for r in hits[:limit // 2 + 1]]
    for product in products[:limit - len(results)]:
        name = f'{product["name"]} {product["size"]}'.strip()
        seen = community.lowest_by_query(reports, name)
        guess = None if seen or product.get("guide_price") else meaning.estimate(rows, name, product["name"])
        rough = None if seen or guess else estimates.for_doc(product)
        results.append({
            "id": product["_id"], "kind": "product", "name": product["name"], "size": product["size"],
            "category": product["category"], "image_url": product.get("image_url"), "unit": None, "price_id": None,
            "price": cmp.money(seen["price_centavos"]) if seen else guess["price"] if guess else rough["price"],
            "price_label": f'{seen["store_name"]}' if seen else "Estimate from similar items" if guess else rough["label"],
        })
    return results


def image_for(db: Database, name: str) -> str | None:
    """A picture for an official item, borrowed from a matching catalog product."""
    if name in _image_cache:
        return _image_cache[name]
    groups = [[t] for t in cmp.tokenize(name) if len(t) >= 3][:3]
    if not groups:
        return None
    criteria = meaning.catalog_criteria(groups)
    criteria["$and"].append({"image_url": {"$nin": [None, ""]}})
    found = db.catalog_items.find_one(criteria)
    _image_cache[name] = found["image_url"] if found else None
    return _image_cache[name]


def summary(db: Database) -> dict:
    rows = price_rows(db)
    movers = sorted((r for r in rows if r["change"]), key=lambda r: r["change_pct"] or 0)
    sources = []
    for name, meta in SOURCES.items():
        date = latest_date(db, name)
        doc = db.market_prices.find_one({"source": name, "report_date": date}) if date else None
        sources.append({
            "id": name, "label": meta["label"], "coverage": meta["coverage"], "report_date": date,
            "rows": sum(r["source"] == name for r in rows),
            "source_url": doc["source_url"] if doc else meta["home"],
        })
    categories = sorted({r["category"] for r in rows})
    return {
        "sources": sources, "items": len(rows), "categories": len(categories),
        "rising": sum((r["change"] or 0) > 0 for r in rows),
        "falling": sum((r["change"] or 0) < 0 for r in rows),
        "top_rising": list(reversed(movers[-5:])) if movers and movers[-1]["change"] > 0 else [],
        "top_falling": movers[:5] if movers and movers[0]["change"] < 0 else [],
        "generated_at": cmp.iso(utcnow()),
    }


def _rank(row: dict, tokens: list[str]) -> tuple:
    name = row["commodity"].lower()
    return (not all(t in name for t in tokens), row["kind"] != "srp" and len(name) > 30, len(name), row["price"])


def rough_guide(query: str, brand: list[dict]) -> dict | None:
    if brand:
        return estimates.guide(f'{brand[0]["name"]} {brand[0]["size"]}', brand[0]["category"], brand[0]["keywords"])
    return estimates.guide(query)


def basket(db: Database, rows: list[dict], items: list[dict], find_products, reports: list[dict], elsewhere: list[dict]) -> dict:
    """Cost a list. Official prices first, then the shopper's own shelf prices.

    Prices fill in by themselves from the best evidence available: an official price, a
    store price nearby, a store price elsewhere, an estimate from similar official items,
    then a rough guide. Each is labelled. An item we can't identify stays out of the total.
    """
    by_id = {r["id"]: r for r in rows}
    lines, total = [], 0
    for item in items:
        query = item["query"]
        custom = item.get("custom_price")
        matched = sorted(search_rows(db, rows, query), key=lambda r: _rank(r, cmp.tokenize(query)))
        chosen = by_id.get(item.get("price_id")) or (matched[0] if matched else None)
        brand = find_products(query) if custom is None and not chosen else []
        status = "no_match"
        unit_centavos = 0
        report = None
        label = query
        if custom is not None:
            status, unit_centavos, chosen = "custom", round(custom * 100), None
        elif chosen:
            status, unit_centavos, label = "matched", round(chosen["price"] * 100), chosen["commodity"]
        elif (seen := community.lowest_by_query(reports, query)):
            status, unit_centavos, label = "reported", seen["price_centavos"], seen["item_name"]
            report = community.report_json(seen)
        elif (seen := community.lowest_by_query(elsewhere, query)):
            status, unit_centavos, label = "reported", seen["price_centavos"], seen["item_name"]
            report = {**community.report_json(seen), "elsewhere": True}
        elif brand and brand[0]["auto_price"].get("by_admin"):
            status, unit_centavos = "estimated", round(brand[0]["auto_price"]["price"] * 100)
            label = f'{brand[0]["name"]} {brand[0]["size"]}'.strip()
            report = {"origin": brand[0]["auto_price"]["label"], "price": brand[0]["auto_price"]["price"]}
        elif (guess := meaning.estimate(rows, query, brand[0]["name"] if brand else "")):
            status, unit_centavos = "estimated", round(guess["price"] * 100)
            label = f'{brand[0]["name"]} {brand[0]["size"]}'.strip() if brand else query
            report = {"origin": f'Typical official price of {guess["count"]} similar {guess["kind"]} items', "price": guess["price"]}
        elif (rough := rough_guide(query, brand)):
            status, unit_centavos = "estimated", round(rough["price"] * 100)
            label = f'{brand[0]["name"]} {brand[0]["size"]}'.strip() if brand else query
            report = {"origin": rough["label"], "price": rough["price"], "low": rough["low"], "high": rough["high"]}
        line_total = unit_centavos * item["quantity"]
        total += line_total
        lines.append({
            "query": query, "quantity": item["quantity"], "status": status, "label": label,
            "selected": chosen, "unit_price": cmp.money(unit_centavos), "line_total": cmp.money(line_total),
            "report": report,
            "candidates": [
                {key: r[key] for key in ("id", "commodity", "specification", "unit", "price", "source_label", "region")}
                for r in matched[:12]
            ],
        })
    counted = [l for l in lines if l["status"] in ("matched", "custom", "reported", "estimated")]
    return {
        "lines": lines, "total": cmp.money(total), "currency": "PHP",
        "items_matched": len(counted),
        "items_estimated": sum(l["status"] == "estimated" for l in lines),
        "items_need_price": sum(l["status"] == "needs_price" for l in lines),
        "items_unmatched": sum(l["status"] == "no_match" for l in lines),
        "generated_at": cmp.iso(utcnow()),
    }
