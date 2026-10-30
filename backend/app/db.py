import uuid
from datetime import UTC, datetime

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from .config import MONGODB_DB, MONGODB_URI

USING_MOCK = MONGODB_URI.startswith("mongomock")

if USING_MOCK:
    import mongomock

    client = mongomock.MongoClient()
else:
    client = MongoClient(MONGODB_URI, tz_aware=False)

database: Database = client[MONGODB_DB]


def get_db() -> Database:
    return database


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Naive UTC at millisecond precision, which is what MongoDB stores."""
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def ensure_indexes(db: Database) -> None:
    db.users.create_index("email", unique=True)
    db.categories.create_index("name", unique=True)
    db.products.create_index("barcode", unique=True, sparse=True)
    db.stores.create_index("organization_id")
    db.store_products.create_index(
        [("store_id", ASCENDING), ("retailer_product_id", ASCENDING)], unique=True,
    )
    db.store_products.create_index("product_id")
    db.price_history.create_index("store_product_id")
    db.retailer_integrations.create_index("organization_id")
    db.sync_jobs.create_index([("integration_id", ASCENDING), ("started_at", ASCENDING)])
    db.audit_logs.create_index("created_at")
    db.market_prices.create_index([("source", ASCENDING), ("report_date", ASCENDING)])
    db.market_prices.create_index("key")


def supports_transactions() -> bool:
    """Multi-document transactions need a replica set; every Atlas cluster is one."""
    if USING_MOCK:
        return False
    return "setName" in client.admin.command("hello")
