"""Clearly identified sample data (spec Phase 2). Every name here is fictional."""
from datetime import timedelta
from decimal import Decimal

from pymongo.database import Database

from .config import DEMO_PASSWORD
from .db import new_id, utcnow
from .security import hash_password

RETAILERS = [
    # name, stores (branch, address, lat, lon), price factor, integration config
    ("Sample Mart", [
        ("Sample Mart Downtown", "12 Sample St, Downtown, Cebu City", 10.2966, 123.9020),
        ("Sample Mart Uptown", "88 Demo Ave, Lahug, Cebu City", 10.3303, 123.9007),
    ], Decimal("0.97"), dict(integration_type="api", provider_name="demo-feed",
                             sync_interval_minutes=15, fresh_minutes=30, stale_minutes=240, age=4)),
    ("Demo Grocer", [
        ("Demo Grocer Mandaue", "5 Placeholder Rd, Mandaue City", 10.3236, 123.9223),
    ], Decimal("1.00"), dict(integration_type="webhook", provider_name="demo-feed",
                             sync_interval_minutes=15, fresh_minutes=30, stale_minutes=240, age=2)),
    ("Example Fresh", [
        ("Example Fresh Banilad", "21 Example Blvd, Banilad, Cebu City", 10.3439, 123.9118),
        ("Example Fresh Talisay", "3 Fictional Hwy, Talisay City", 10.2447, 123.8494),
    ], Decimal("1.04"), dict(integration_type="csv", provider_name="demo-feed",
                             sync_interval_minutes=1440, fresh_minutes=1440, stale_minutes=2880, age=180)),
    # Permanently down: demonstrates stale handling and outage behaviour (AC-12).
    ("Test Supermarket", [
        ("Test Supermarket Lapu-Lapu", "9 Mock St, Lapu-Lapu City", 10.3103, 123.9494),
    ], Decimal("0.90"), dict(integration_type="api", provider_name="demo-feed-outage",
                             sync_interval_minutes=60, fresh_minutes=30, stale_minutes=120, age=300)),
]

CATALOG = [
    # category, name, brand, size, unit, base price, which retailers skip it
    ("Rice", "Jasmine Rice", "Bukid Gold", "5", "kg", "345", ()),
    ("Rice", "Jasmine Rice", "Bukid Gold", "1", "kg", "74", ()),
    ("Rice", "Sinandomeng Rice", "Bukid Gold", "5", "kg", "310", (1,)),
    ("Rice", "Well-Milled Rice", "Palay Select", "5", "kg", "280", ()),
    ("Rice", "Brown Rice", "Palay Select", "1", "kg", "96", (0,)),
    ("Oil", "Cooking Oil", "Brand X", "1", "L", "88", ()),
    ("Oil", "Cooking Oil", "Brand X", "500", "ml", "49", ()),
    ("Oil", "Coconut Oil", "Niyog Pure", "1", "L", "165", (2,)),
    ("Milk", "Fresh Milk", "Dairy Valley", "1", "L", "108", ()),
    ("Milk", "Evaporated Milk", "Dairy Valley", "370", "ml", "42", ()),
    ("Milk", "Powdered Milk", "Dairy Valley", "300", "g", "148", (3,)),
    ("Eggs", "Eggs Medium Tray", "Farm Hen", "30", "pieces", "235", ()),
    ("Eggs", "Eggs Large", "Farm Hen", "12", "pieces", "118", (1,)),
    ("Canned Goods", "Sardines in Tomato Sauce", "Dagat", "155", "g", "24", ()),
    ("Canned Goods", "Corned Beef", "Rancho", "150", "g", "62", ()),
    ("Canned Goods", "Tuna Flakes in Oil", "Dagat", "180", "g", "45", (2,)),
    ("Noodles", "Instant Noodles Chicken", "Mami Quick", "55", "g", "11", ()),
    ("Noodles", "Spaghetti Pasta", "Pasta Casa", "900", "g", "98", ()),
    ("Condiments", "Soy Sauce", "Toyo King", "1", "L", "58", ()),
    ("Condiments", "Cane Vinegar", "Toyo King", "1", "L", "42", ()),
    ("Condiments", "White Sugar", "Tamis", "1", "kg", "82", ()),
    ("Condiments", "Iodized Salt", "Tamis", "1", "kg", "38", (0,)),
    ("Beverages", "Instant Coffee", "Kape Uno", "200", "g", "189", ()),
    ("Beverages", "Bottled Water", "Linaw", "1", "L", "22", ()),
    ("Household", "Laundry Detergent Powder", "Linis", "1", "kg", "124", ()),
    ("Household", "Dishwashing Liquid", "Linis", "500", "ml", "86", (3,)),
]


def seed(db: Database) -> bool:
    if db.organizations.find_one():
        return False
    now = utcnow()
    categories = {name: {"_id": new_id(), "name": name} for name in sorted({row[0] for row in CATALOG})}
    db.categories.insert_many(list(categories.values()))

    products = []
    for index, (category, name, brand, size, unit, price, skipped) in enumerate(CATALOG):
        product = {
            "_id": new_id(), "name": name, "brand": brand,
            "category_id": categories[category]["_id"], "category": category,
            "package_size_value": float(size), "package_size_unit": unit,
            "package_size": f"{size} {unit}", "barcode": f"480000{index:06d}",
            "image_url": None, "status": "active", "created_at": now,
        }
        products.append((product, Decimal(price), skipped))
    db.products.insert_many([p for p, _, _ in products])

    organizations, listings, history = [], [], []
    for retailer_index, (name, branches, factor, config) in enumerate(RETAILERS):
        org = {"_id": new_id(), "name": name, "organization_type": "retailer", "status": "active",
               "created_at": now, "updated_at": now}
        db.organizations.insert_one(org)
        organizations.append(org)
        config = dict(config)
        synced_at = now - timedelta(minutes=config.pop("age"))
        integration = {
            "_id": new_id(), "organization_id": org["_id"], "configuration_reference": None,
            "last_successful_sync_at": synced_at, "created_at": now,
            "status": "failed" if config["provider_name"].endswith("outage") else "active", **config,
        }
        db.retailer_integrations.insert_one(integration)
        db.sync_jobs.insert_one({
            "_id": new_id(), "integration_id": integration["_id"], "started_at": synced_at,
            "completed_at": synced_at, "status": "succeeded",
            "records_processed": len(products) * len(branches),
            "records_updated": len(products) * len(branches),
            "records_rejected": 0, "error_summary": None, "rejections": [],
        })
        for branch_index, (branch, address, lat, lon) in enumerate(branches):
            store = {
                "_id": new_id(), "organization_id": org["_id"], "name": branch, "address": address,
                "latitude": lat, "longitude": lon,
                "location": {"type": "Point", "coordinates": [lon, lat]},
                "status": "active", "created_at": now,
            }
            db.stores.insert_one(store)
            for product_index, (product, base, skipped) in enumerate(products):
                if retailer_index in skipped:
                    continue
                # Deterministic spread so demos and tests see a stable ordering.
                wobble = Decimal((product_index * 7 + branch_index * 5 + retailer_index * 3) % 9 - 4) / 100
                centavos = int(base * (factor + wobble) * 100)
                listing = {
                    "_id": new_id(), "store_id": store["_id"], "product_id": product["_id"],
                    "retailer_product_id": f"R{retailer_index}-{product_index:04d}",
                    "retailer_sku": f"SKU-{retailer_index}{product_index:04d}",
                    "price_centavos": centavos, "currency": "PHP",
                    "availability_status": "available" if product_index % 11 else "unknown",
                    "last_synced_at": synced_at, "price_effective_at": synced_at - timedelta(days=2),
                    "updated_at": synced_at,
                }
                listings.append(listing)
                history.append({
                    "_id": new_id(), "store_product_id": listing["_id"], "price_centavos": centavos,
                    "currency": "PHP", "effective_at": listing["price_effective_at"],
                    "observed_at": synced_at, "source_type": "import",
                })
    db.store_products.insert_many(listings)
    db.price_history.insert_many(history)

    password = hash_password(DEMO_PASSWORD)
    account = lambda email, name, roles: {
        "_id": new_id(), "email": email, "full_name": name, "password_hash": password,
        "status": "active", "roles": roles, "created_at": now,
    }
    db.users.insert_many([
        account("admin@demo.local", "Demo System Admin", [{"role": "system_admin", "organization_id": None}]),
        account("supervisor@demo.local", "Demo Supervisor",
                [{"role": "supervisor", "organization_id": organizations[0]["_id"]}]),
    ])
    return True
