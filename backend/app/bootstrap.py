"""Startup housekeeping: removes the old sample data and creates the administrator."""
import logging

from pymongo.database import Database

from .config import ADMIN_EMAIL, ADMIN_PASSWORD
from .db import new_id, utcnow
from .security import hash_password

log = logging.getLogger("grocery.bootstrap")
SAMPLE_RETAILERS = ["Sample Mart", "Demo Grocer", "Example Fresh", "Test Supermarket"]
SAMPLE_ACCOUNTS = ["admin@demo.local", "supervisor@demo.local"]


def purge_sample_data(db: Database) -> None:
    """Removes only what the old seed created. Safe to run on every start."""
    org_ids = [o["_id"] for o in db.organizations.find({"name": {"$in": SAMPLE_RETAILERS}})]
    store_ids = [s["_id"] for s in db.stores.find({"organization_id": {"$in": org_ids}})]
    listing_ids = [l["_id"] for l in db.store_products.find({"store_id": {"$in": store_ids}}, {"_id": 1})]
    integration_ids = [i["_id"] for i in db.retailer_integrations.find({"organization_id": {"$in": org_ids}})]

    db.price_history.delete_many({"store_product_id": {"$in": listing_ids}})
    db.store_products.delete_many({"_id": {"$in": listing_ids}})
    db.sync_jobs.delete_many({"integration_id": {"$in": integration_ids}})
    db.retailer_integrations.delete_many({"_id": {"$in": integration_ids}})
    db.stores.delete_many({"_id": {"$in": store_ids}})
    db.organizations.delete_many({"_id": {"$in": org_ids}})
    db.users.delete_many({"email": {"$in": SAMPLE_ACCOUNTS}})
    if org_ids:
        db.products.delete_many({"barcode": {"$regex": "^480000"}})
        db.categories.delete_many({})
        db.audit_logs.delete_many({"organization_id": {"$in": org_ids}})
        log.info("removed sample data for %d retailers", len(org_ids))


def ensure_admin(db: Database) -> None:
    if ADMIN_EMAIL and ADMIN_PASSWORD and not db.users.find_one({"email": ADMIN_EMAIL}):
        db.users.insert_one({
            "_id": new_id(), "email": ADMIN_EMAIL, "full_name": "System Administrator",
            "password_hash": hash_password(ADMIN_PASSWORD), "status": "active",
            "roles": [{"role": "system_admin", "organization_id": None}], "created_at": utcnow(),
        })
