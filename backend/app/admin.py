"""Administration endpoints (spec section 9.2). Everything is organization-scoped."""
from collections import Counter, defaultdict
from statistics import median

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from pymongo.database import Database

from . import comparison as cmp
from .config import MAX_CSV_BYTES
from .db import get_db, new_id, utcnow
from .security import audit, current_user, require_org, require_system_admin, scope_filter
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
