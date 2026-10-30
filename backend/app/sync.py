"""Retailer adapters and the transactional price import (spec sections 7 and 10.1)."""
import csv
import io
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from pymongo.database import Database

from .db import client, new_id, supports_transactions, utcnow

log = logging.getLogger("grocery.sync")
AVAILABILITY = {"available", "unavailable", "unknown"}
CSV_COLUMNS = {"store_id", "retailer_product_id", "price", "currency"}
MAX_STORED_REJECTIONS = 100
MAX_PRICE = Decimal("9999999")


class AdapterError(Exception):
    """A retailer connection failure. The message must be safe to store and display."""


class RetailerAdapter(ABC):
    """Every integration method yields the same standard record shape."""

    source_type = "api"

    @abstractmethod
    def fetch(self) -> list[dict]:
        ...

    def test(self) -> None:
        self.fetch()


class CsvAdapter(RetailerAdapter):
    source_type = "import"

    def __init__(self, content: bytes):
        self.content = content

    def fetch(self) -> list[dict]:
        try:
            reader = csv.DictReader(io.StringIO(self.content.decode("utf-8-sig")))
            missing = CSV_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise AdapterError(f"CSV is missing columns: {', '.join(sorted(missing))}")
            return list(reader)
        except (UnicodeDecodeError, csv.Error):
            raise AdapterError("File is not valid UTF-8 CSV")


def adapter_for(db: Database, integration: dict) -> RetailerAdapter | None:
    return None  # REST/POS connectors subclass RetailerAdapter once a retailer authorizes access.


def _parse_effective(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=None) - (parsed.utcoffset() or timedelta(0))


def _validate(row: dict, store_ids: set[str]) -> tuple[dict | None, str | None]:
    field = lambda name: (row.get(name) or "").strip()
    if field("store_id") not in store_ids:
        return None, "store_id does not belong to this organization"
    if not field("retailer_product_id"):
        return None, "retailer_product_id is required"
    try:
        price = Decimal(field("price"))
    except InvalidOperation:
        return None, "price is not a number"
    if not price.is_finite() or price < 0 or price > MAX_PRICE:
        return None, "price must be between 0 and 9,999,999"
    if field("currency").upper() != "PHP":
        return None, "currency must be PHP"
    availability = (field("availability") or "unknown").lower()
    if availability not in AVAILABILITY:
        return None, "availability must be available, unavailable or unknown"
    try:
        effective = _parse_effective(field("price_effective_at"))
    except ValueError:
        return None, "price_effective_at is not an ISO-8601 time"
    return {
        "store_id": field("store_id"),
        "retailer_product_id": field("retailer_product_id"),
        "price_centavos": int((price * 100).to_integral_value()),
        "currency": "PHP",
        "availability": availability,
        "effective_at": effective,
        "barcode": field("barcode") or None,
    }, None


def _stage(db: Database, record: dict, pending: dict, source_type: str, now: datetime, history: list):
    """Work out the change in memory. Nothing reaches the database until the batch commits."""
    key = (record["store_id"], record["retailer_product_id"])
    listing = pending.get(key) or db.store_products.find_one({
        "store_id": record["store_id"], "retailer_product_id": record["retailer_product_id"],
    })
    if listing is None:
        # New retailer IDs map only on a verified barcode; fuzzy names never auto-merge.
        product = db.products.find_one({"barcode": record["barcode"]}) if record["barcode"] else None
        if product is None:
            return False, "no verified product mapping (needs barcode or mapping review)"
        listing = {
            "_id": new_id(), "store_id": record["store_id"], "product_id": product["_id"],
            "retailer_product_id": record["retailer_product_id"], "retailer_sku": None,
            "price_centavos": None, "currency": record["currency"],
        }
    changed = listing["price_centavos"] != record["price_centavos"]
    if changed:
        listing["price_centavos"] = record["price_centavos"]
        listing["price_effective_at"] = record["effective_at"] or now
        history.append({
            "_id": new_id(), "store_product_id": listing["_id"], "price_centavos": record["price_centavos"],
            "currency": record["currency"], "effective_at": listing["price_effective_at"],
            "observed_at": now, "source_type": source_type,
        })
    listing["availability_status"] = record["availability"]
    listing["last_synced_at"] = now
    listing["updated_at"] = now
    pending[key] = listing
    return changed, None


def run_sync(db: Database, integration: dict, adapter: RetailerAdapter) -> dict:
    """All-or-nothing per batch: a failure leaves earlier prices intact and the job failed."""
    job = {
        "_id": new_id(), "integration_id": integration["_id"], "started_at": utcnow(),
        "completed_at": None, "status": "running", "records_processed": 0, "records_updated": 0,
        "records_rejected": 0, "error_summary": None, "rejections": [],
    }
    db.sync_jobs.insert_one(job)

    try:
        rows = adapter.fetch()
        store_ids = {s["_id"] for s in db.stores.find({"organization_id": integration["organization_id"]})}
        now = utcnow()
        pending: dict = {}
        history: list[dict] = []
        updated, rejections = 0, []
        for number, row in enumerate(rows, start=1):
            record, reason = _validate(row, store_ids)
            if record is not None:
                changed, reason = _stage(db, record, pending, adapter.source_type, now, history)
                updated += int(changed)
            if reason:
                rejections.append({"row": number, "reason": reason})

        job.update({
            "records_processed": len(rows), "records_updated": updated,
            "records_rejected": len(rejections), "rejections": rejections[:MAX_STORED_REJECTIONS],
            "status": "succeeded", "completed_at": utcnow(),
            "error_summary": f"{len(rejections)} record(s) rejected" if rejections else None,
        })

        def commit(session=None):
            for listing in pending.values():
                db.store_products.replace_one({"_id": listing["_id"]}, listing, upsert=True, session=session)
            if history:
                db.price_history.insert_many(history, session=session)
            db.sync_jobs.replace_one({"_id": job["_id"]}, job, session=session)
            db.retailer_integrations.update_one(
                {"_id": integration["_id"]},
                {"$set": {"status": "active", "last_successful_sync_at": now}}, session=session,
            )

        if supports_transactions():
            with client.start_session() as session:
                session.with_transaction(commit)
        else:
            commit()
        integration.update(status="active", last_successful_sync_at=now)
    except Exception as error:
        log.warning("sync failed for integration %s: %s", integration["_id"], type(error).__name__)
        job.update({
            "status": "failed", "completed_at": utcnow(),
            "error_summary": str(error) if isinstance(error, AdapterError) else "Unexpected import failure",
        })
        db.sync_jobs.replace_one({"_id": job["_id"]}, job)
        db.retailer_integrations.update_one({"_id": integration["_id"]}, {"$set": {"status": "failed"}})
        integration["status"] = "failed"
    return job
