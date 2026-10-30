"""Official Philippine price data: DTI SRPs (nationwide) and DA prevailing prices (NCR).

Every price stored here comes from a government publication and keeps its source URL
and report date. Nothing is estimated, and a report that fails validation is discarded
so the previous good report stays in place.
"""
import logging
import re
from collections import defaultdict
from datetime import timedelta

import httpx
from pymongo.database import Database

from . import community, ingestion
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


def search(rows: list[dict], query: str) -> list[dict]:
    tokens = cmp.tokenize(query)
    return [r for r in rows if cmp.matches(tokens, _text(r))] if tokens else rows


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


def basket(rows: list[dict], items: list[dict], find_products=lambda query: [], reports: list[dict] | None = None) -> dict:
    """Cost a list. Official prices first, then the shopper's own shelf prices.

    A product in the brand catalog has no official price, so it stays out of the total
    until a shopper reports one or the shopper enters their own. Prices are never guessed.
    """
    by_id = {r["id"]: r for r in rows}
    lines, total = [], 0
    for item in items:
        query = item["query"]
        custom = item.get("custom_price")
        matched = sorted(search(rows, query), key=lambda r: _rank(r, cmp.tokenize(query)))
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
        elif (seen := community.lowest_by_query(reports or [], query)):
            status, unit_centavos, label = "reported", seen["price_centavos"], seen["item_name"]
            report = community.report_json(seen)
        elif brand:
            status, label = "needs_price", f'{brand[0]["name"]} {brand[0]["size"]}'.strip()
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
    counted = [l for l in lines if l["status"] in ("matched", "custom", "reported")]
    return {
        "lines": lines, "total": cmp.money(total), "currency": "PHP",
        "items_matched": len(counted),
        "items_need_price": sum(l["status"] == "needs_price" for l in lines),
        "items_unmatched": sum(l["status"] == "no_match" for l in lines),
        "generated_at": cmp.iso(utcnow()),
    }
