"""Administration endpoints (spec section 9.2). Everything is organization-scoped."""
from collections import Counter, defaultdict
from statistics import median

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from pymongo.database import Database

from . import agent, catalog, community, ingestion
from .sources import open_data
from . import comparison as cmp
from .config import MAX_CSV_BYTES
from .db import get_db, new_id, utcnow
from .security import audit, current_user, hash_password, require_org, require_system_admin, scope_filter
from .sync import AdapterError, CsvAdapter, adapter_for, run_sync

router = APIRouter(prefix="/api/v1/admin")
INTEGRATION_ROLES = {"supervisor", "integration_admin", "mall_admin"}
STATUSES = ["fresh", "aging", "stale", "unavailable", "unknown"]


def integration_or_404(db: Database, integration_id: str, user: dict) -> dict:
    integration = db.retailer_integrations.find_one({"_id": integration_id})
    if integration is None:
        raise HTTPException(404, "Integration not found")
    require_org(user, integration["organization_id"], INTEGRATION_ROLES)
    return integration


def scoped_stores(db: Database, user: dict) -> dict[str, dict]:
    return {s["_id"]: s for s in db.stores.find(scope_filter(user))}


def org_names(db: Database) -> dict[str, str]:
    return {o["_id"]: o["name"] for o in db.organizations.find()}


def integration_json(i: dict, names: dict[str, str], counts: Counter | None = None) -> dict:
    return {
        "id": i["_id"], "organization_id": i["organization_id"],
        "organization": names.get(i["organization_id"]),
        "integration_type": i["integration_type"], "provider_name": i["provider_name"],
        "sync_interval_minutes": i["sync_interval_minutes"], "fresh_minutes": i["fresh_minutes"],
        "stale_minutes": i["stale_minutes"], "status": i["status"],
        "last_successful_sync_at": cmp.iso(i.get("last_successful_sync_at")),
        "can_sync": False,
        "freshness": {s: (counts or {}).get(s, 0) for s in STATUSES},
    }


def job_json(job: dict, organization: str | None) -> dict:
    return {
        "id": job["_id"], "integration_id": job["integration_id"], "organization": organization,
        "started_at": cmp.iso(job["started_at"]), "completed_at": cmp.iso(job.get("completed_at")),
        "status": job["status"], "records_processed": job["records_processed"],
        "records_updated": job["records_updated"], "records_rejected": job["records_rejected"],
        "error_summary": job.get("error_summary"), "rejections": job.get("rejections") or [],
    }


def org_of(db: Database, integration: dict) -> str | None:
    return org_names(db).get(integration["organization_id"])


@router.get("/overview")
def overview(user: dict = Depends(current_user), db: Database = Depends(get_db)):
    stores = scoped_stores(db, user)
    thresholds, now = cmp.thresholds_by_org(db), utcnow()
    per_org: dict[str, Counter] = defaultdict(Counter)
    products, listings = set(), 0
    for listing in db.store_products.find({"store_id": {"$in": list(stores)}}):
        organization_id = stores[listing["store_id"]]["organization_id"]
        per_org[organization_id][cmp.price_status(listing, organization_id, thresholds, now)] += 1
        products.add(listing["product_id"])
        listings += 1

    integrations = list(db.retailer_integrations.find(scope_filter(user)).sort("created_at", 1))
    names = org_names(db)
    totals = Counter()
    for counts in per_org.values():
        totals.update(counts)
    return {
        "stores": len(stores),
        "products": len(products),
        "listings": listings,
        "freshness": {s: totals.get(s, 0) for s in STATUSES},
        "integrations_total": len(integrations),
        "integrations_failed": sum(i["status"] == "failed" for i in integrations),
        "retailers": [integration_json(i, names, per_org.get(i["organization_id"])) for i in integrations],
        "generated_at": cmp.iso(now),
    }


@router.get("/data-quality")
def data_quality(user: dict = Depends(current_user), db: Database = Depends(get_db)):
    """Listings priced far from the same product elsewhere, for a human to check."""
    stores = scoped_stores(db, user)
    all_prices: dict[str, list[int]] = defaultdict(list)
    listings = list(db.store_products.find({}, {"product_id": 1, "store_id": 1, "price_centavos": 1}))
    for listing in listings:
        all_prices[listing["product_id"]].append(listing["price_centavos"])
    products = {p["_id"]: p for p in db.products.find()}
    issues = []
    for listing in listings:
        prices = all_prices[listing["product_id"]]
        middle = median(prices)
        price = listing["price_centavos"]
        if listing["store_id"] in stores and len(prices) >= 3 and middle and abs(price - middle) / middle > 0.25:
            product = products[listing["product_id"]]
            issues.append({
                "store": stores[listing["store_id"]]["name"], "product": product["name"],
                "package_size": product["package_size"],
                "price": cmp.money(price), "median_price": cmp.money(round(middle)),
            })
    return {"price_discrepancies": issues}


@router.get("/sync-jobs")
def sync_jobs(limit: int = 40, user: dict = Depends(current_user), db: Database = Depends(get_db)):
    integrations = {i["_id"]: i for i in db.retailer_integrations.find(scope_filter(user))}
    names = org_names(db)
    jobs = db.sync_jobs.find({"integration_id": {"$in": list(integrations)}}).sort("started_at", -1).limit(min(limit, 200))
    return [job_json(j, names.get(integrations[j["integration_id"]]["organization_id"])) for j in jobs]


@router.get("/audit-logs")
def audit_logs(user: dict = Depends(current_user), db: Database = Depends(get_db)):
    rows = db.audit_logs.find(scope_filter(user)).sort("created_at", -1).limit(50)
    return [
        {"action": a["action"], "actor": a.get("actor_email"), "detail": a.get("detail"), "created_at": cmp.iso(a["created_at"])}
        for a in rows
    ]


@router.get("/market-reports")
def market_reports(user: dict = Depends(current_user), db: Database = Depends(get_db)):
    return [
        {
            "source": r["source"], "status": r["status"], "report_date": r.get("report_date"),
            "rows": r.get("rows", 0), "error": r.get("error"), "checked_at": cmp.iso(r["checked_at"]),
            "url": r["_id"],
        }
        for r in db.market_reports.find().sort("checked_at", -1).limit(20)
    ]


ROLES = {"system_admin", "mall_admin", "supervisor", "integration_admin"}


def account_json(user: dict, names: dict[str, str]) -> dict:
    """Everything an administrator may see. The password hash is never included."""
    return {
        "id": user["_id"], "email": user["email"], "full_name": user["full_name"], "status": user["status"],
        "roles": [
            {"role": r["role"], "organization": names.get(r.get("organization_id"))} for r in user["roles"]
        ],
        "created_at": cmp.iso(user.get("created_at")),
    }


class UserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=12, max_length=200)
    role: str
    organization_id: str | None = None


class UserUpdate(BaseModel):
    status: str | None = Field(None, pattern="^(active|suspended)$")
    password: str | None = Field(None, min_length=12, max_length=200)


@router.get("/users")
def list_users(user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    names = org_names(db)
    return [account_json(u, names) for u in db.users.find().sort("email", 1)]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(422, "Unknown role")
    if body.role != "system_admin" and db.organizations.find_one({"_id": body.organization_id}) is None:
        raise HTTPException(422, "Choose a retailer for this role")
    email = body.email.strip().lower()
    if db.users.find_one({"email": email}):
        raise HTTPException(409, "An account with this email already exists")
    account = {
        "_id": new_id(), "email": email, "full_name": body.full_name.strip(),
        "password_hash": hash_password(body.password), "status": "active", "created_at": utcnow(),
        "roles": [{"role": body.role, "organization_id": None if body.role == "system_admin" else body.organization_id}],
    }
    db.users.insert_one(account)
    audit(db, user, "user.created", account["roles"][0]["organization_id"], f"{email} as {body.role}")
    return account_json(account, org_names(db))


@router.patch("/users/{user_id}")
def update_user(
    user_id: str, body: UserUpdate, user: dict = Depends(require_system_admin), db: Database = Depends(get_db),
):
    account = db.users.find_one({"_id": user_id})
    if account is None:
        raise HTTPException(404, "User not found")
    if body.status == "suspended" and user_id == user["_id"]:
        raise HTTPException(409, "You can't suspend your own account")
    changes = {}
    if body.status:
        changes["status"] = body.status
    if body.password:
        changes["password_hash"] = hash_password(body.password)
    if changes:
        db.users.update_one({"_id": user_id}, {"$set": changes})
        account.update(changes)
    # The password itself is never written to the audit log.
    audit(db, user, "user.updated", None, f'{account["email"]}: {", ".join(sorted(k.replace("_hash", "") for k in changes))}')
    return account_json(account, org_names(db))


@router.get("/organizations")
def list_organizations(user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    return [
        {"id": o["_id"], "name": o["name"], "status": o["status"],
         "stores": db.stores.count_documents({"organization_id": o["_id"]})}
        for o in db.organizations.find().sort("name", 1)
    ]


@router.get("/shelf-prices")
def shelf_prices(user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    rows = db.shelf_reports.find().sort("created_at", -1).limit(60)
    return [
        {"id": r["_id"], "status": r["status"], **community.report_json(r)}
        for r in rows
    ]


@router.delete("/shelf-prices/{report_id}")
def delete_shelf_price(report_id: str, user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    report = db.shelf_reports.find_one({"_id": report_id})
    if report is None:
        raise HTTPException(404, "Report not found")
    db.shelf_reports.delete_one({"_id": report_id})
    audit(db, user, "shelf_price.removed", None, f'{report["item_name"]} at {report["store_name"]}')
    return {"deleted": True}


@router.post("/shelf-prices/{report_id}/approve")
def approve_shelf_price(report_id: str, user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    if db.shelf_reports.update_one({"_id": report_id}, {"$set": {"status": "visible"}}).matched_count == 0:
        raise HTTPException(404, "Report not found")
    audit(db, user, "shelf_price.approved", None, report_id)
    return {"approved": True}


class CatalogCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    brand: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=2, max_length=80)
    size: str = Field(min_length=1, max_length=40)


@router.get("/catalog")
def admin_catalog(user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    return catalog.custom_items(db)


@router.post("/catalog", status_code=201)
def add_catalog_item(body: CatalogCreate, user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    doc = {
        "_id": f"custom:{new_id()}", **body.model_dump(), "variant": "", "source": "admin", "status": "active",
        "keywords": f"{body.brand} {body.name} {body.size} {body.category}".lower(), "created_at": utcnow(),
    }
    db.catalog_items.insert_one(doc)
    audit(db, user, "catalog.added", None, f'{doc["name"]} {doc["size"]}')
    return {"id": doc["_id"]}


@router.delete("/catalog/{item_id}")
def delete_catalog_item(item_id: str, user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    doc = db.catalog_items.find_one({"_id": item_id})
    if doc is None:
        raise HTTPException(404, "Catalog item not found")
    db.catalog_items.update_one({"_id": item_id}, {"$set": {"status": "hidden"}})
    audit(db, user, "catalog.removed", None, doc["name"])
    return {"deleted": True}


class SourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: str
    terms_url: str = Field("", max_length=300)
    notes: str = Field("", max_length=500)


class SourceUpdate(BaseModel):
    permission: str | None = Field(None, pattern="^(open_license|granted|pending|refused)$")
    enabled: bool | None = None
    notes: str | None = Field(None, max_length=500)


@router.get("/sources")
def list_sources(user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    return [ingestion.source_json(db, s) for s in db.price_sources.find().sort("name", 1)]


@router.post("/sources", status_code=201)
def create_source(body: SourceCreate, user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    source = ingestion.create_source(db, body.name, body.kind, body.terms_url, body.notes)
    audit(db, user, "source.created", None, source["name"])
    return ingestion.source_json(db, source)


@router.patch("/sources/{source_id}")
def update_source(
    source_id: str, body: SourceUpdate, user: dict = Depends(require_system_admin), db: Database = Depends(get_db),
):
    source = ingestion.update_source(db, source_id, body.permission, body.enabled, body.notes)
    audit(db, user, "source.updated", None, f'{source["name"]}: {source["permission"]}, enabled={source["enabled"]}')
    return ingestion.source_json(db, source)


@router.post("/sources/{source_id}/import")
async def import_source(
    source_id: str, file: UploadFile = File(),
    user: dict = Depends(require_system_admin), db: Database = Depends(get_db),
):
    content = await file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(413, "CSV file must be 2 MB or smaller")
    result = ingestion.import_feed(db, source_id, content)
    audit(db, user, "source.imported", None, f'{source_id}: {result["imported"]} imported, {result["rejected"]} rejected')
    return result


@router.get("/data-sources")
def data_sources(user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    return open_data.status(db)


@router.get("/agent")
def agent_status(user: dict = Depends(require_system_admin), db: Database = Depends(get_db)):
    return agent.status(db)


@router.post("/agent/run", status_code=202)
def run_agent(
    tasks: BackgroundTasks, user: dict = Depends(require_system_admin), db: Database = Depends(get_db),
):
    tasks.add_task(agent.run_cycle, db)
    audit(db, user, "agent.run_requested")
    return {"started": True}


class ConnectorUpdate(BaseModel):
    url: str = Field(min_length=9, max_length=300)
    items_key: str = Field("items", max_length=40)


@router.put("/sources/{source_id}/connector")
def set_connector(
    source_id: str, body: ConnectorUpdate, user: dict = Depends(require_system_admin), db: Database = Depends(get_db),
):
    source = ingestion.set_connector(db, source_id, body.url, body.items_key)
    audit(db, user, "source.connector_set", None, source["name"])
    return ingestion.source_json(db, source)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    organization_type: str = "retailer"


@router.post("/organizations", status_code=201)
def create_organization(
    body: OrganizationCreate, user: dict = Depends(require_system_admin), db: Database = Depends(get_db),
):
    now = utcnow()
    org = {"_id": new_id(), **body.model_dump(), "status": "active", "created_at": now, "updated_at": now}
    db.organizations.insert_one(org)
    audit(db, user, "organization.created", org["_id"], org["name"])
    return {"id": org["_id"], "name": org["name"], "status": org["status"]}


class StoreCreate(BaseModel):
    organization_id: str
    name: str = Field(min_length=2, max_length=200)
    address: str = Field(min_length=2)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


@router.post("/stores", status_code=201)
def create_store(body: StoreCreate, user: dict = Depends(current_user), db: Database = Depends(get_db)):
    require_org(user, body.organization_id, {"mall_admin", "supervisor"})
    if db.organizations.find_one({"_id": body.organization_id}) is None:
        raise HTTPException(404, "Organization not found")
    store = {
        "_id": new_id(), **body.model_dump(), "status": "active", "created_at": utcnow(),
        "location": {"type": "Point", "coordinates": [body.longitude, body.latitude]},
    }
    db.stores.insert_one(store)
    audit(db, user, "store.created", store["organization_id"], store["name"])
    return {"id": store["_id"], "name": store["name"]}


class IntegrationCreate(BaseModel):
    organization_id: str
    integration_type: str = Field(pattern="^(api|webhook|database|csv|pos)$")
    provider_name: str = Field(min_length=2, max_length=120)
    configuration_reference: str | None = None
    sync_interval_minutes: int = Field(60, ge=5)
    fresh_minutes: int = Field(60, ge=1)
    stale_minutes: int = Field(1440, ge=1)

    @field_validator("configuration_reference")
    @classmethod
    def must_be_reference(cls, value):
        if value is not None and not value.startswith("secret://"):
            raise ValueError("must be a secret:// reference, never a raw credential")
        return value


class IntegrationUpdate(BaseModel):
    status: str | None = Field(None, pattern="^(active|disabled)$")
    sync_interval_minutes: int | None = Field(None, ge=5)
    fresh_minutes: int | None = Field(None, ge=1)
    stale_minutes: int | None = Field(None, ge=1)


@router.post("/integrations", status_code=201)
def create_integration(
    body: IntegrationCreate, user: dict = Depends(current_user), db: Database = Depends(get_db),
):
    require_org(user, body.organization_id, INTEGRATION_ROLES)
    if db.organizations.find_one({"_id": body.organization_id}) is None:
        raise HTTPException(404, "Organization not found")
    integration = {
        "_id": new_id(), **body.model_dump(), "status": "active",
        "last_successful_sync_at": None, "created_at": utcnow(),
    }
    db.retailer_integrations.insert_one(integration)
    audit(db, user, "integration.created", integration["organization_id"], integration["provider_name"])
    return integration_json(integration, org_names(db))


@router.get("/integrations")
def list_integrations(user: dict = Depends(current_user), db: Database = Depends(get_db)):
    names = org_names(db)
    return [integration_json(i, names) for i in db.retailer_integrations.find(scope_filter(user))]


@router.patch("/integrations/{integration_id}")
def update_integration(
    integration_id: str, body: IntegrationUpdate,
    user: dict = Depends(current_user), db: Database = Depends(get_db),
):
    integration = integration_or_404(db, integration_id, user)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if changes:
        db.retailer_integrations.update_one({"_id": integration_id}, {"$set": changes})
        integration.update(changes)
    audit(db, user, "integration.updated", integration["organization_id"], ", ".join(sorted(changes)))
    return integration_json(integration, org_names(db))


@router.post("/integrations/{integration_id}/test")
def test_integration(integration_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db)):
    integration = integration_or_404(db, integration_id, user)
    adapter = adapter_for(db, integration)
    if adapter is None:
        raise HTTPException(409, "No connector is available for this integration yet")
    try:
        adapter.test()
    except AdapterError as error:
        return {"ok": False, "detail": str(error)}
    return {"ok": True, "detail": "Connection succeeded"}


@router.post("/integrations/{integration_id}/sync")
def sync_integration(integration_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db)):
    integration = integration_or_404(db, integration_id, user)
    if integration["status"] == "disabled":
        raise HTTPException(409, "Integration is disabled")
    adapter = adapter_for(db, integration)
    if adapter is None:
        raise HTTPException(409, "No connector is available for this integration yet")
    job = run_sync(db, integration, adapter)
    audit(db, user, "integration.sync_requested", integration["organization_id"], job["status"])
    return job_json(job, org_of(db, integration))


@router.get("/integrations/{integration_id}/status")
def integration_status(integration_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db)):
    integration = integration_or_404(db, integration_id, user)
    last = db.sync_jobs.find_one({"integration_id": integration_id}, sort=[("started_at", -1)])
    names = org_names(db)
    organization = names.get(integration["organization_id"])
    return {**integration_json(integration, names), "last_job": job_json(last, organization) if last else None}


@router.post("/imports/csv")
async def import_csv(
    integration_id: str = Form(), file: UploadFile = File(),
    user: dict = Depends(current_user), db: Database = Depends(get_db),
):
    integration = integration_or_404(db, integration_id, user)
    content = await file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(413, "CSV file must be 2 MB or smaller")
    job = run_sync(db, integration, CsvAdapter(content))
    audit(db, user, "price_import.csv", integration["organization_id"], f"{job['status']}, {job['records_rejected']} rejected")
    return job_json(job, org_of(db, integration))
