"""Public and shopper endpoints (spec section 9.1)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from pymongo.database import Database

from . import comparison as cmp
from . import location, market
from .config import LOGIN_RATE_PER_MINUTE, MAX_MULTI_SEARCH_ITEMS, NEARBY_RADIUS_KM, SEARCH_RATE_PER_MINUTE
from .db import get_db, utcnow
from .security import RateLimiter, current_user, issue_token, read_token, verify_password

router = APIRouter(prefix="/api/v1")
limit_search = RateLimiter(SEARCH_RATE_PER_MINUTE)
limit_login = RateLimiter(LOGIN_RATE_PER_MINUTE)

Latitude = Query(None, ge=-90, le=90)
Longitude = Query(None, ge=-180, le=180)
Radius = Query(None, gt=0, le=200)


def need_both(latitude, longitude):
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, "latitude and longitude must be supplied together")


def store_json(db: Database, store: dict, latitude=None, longitude=None) -> dict:
    distance = None
    if latitude is not None and longitude is not None:
        distance = round(cmp.haversine_km(latitude, longitude, store["latitude"], store["longitude"]), 2)
    organization = db.organizations.find_one({"_id": store["organization_id"]}) or {}
    return {
        "store_id": store["_id"], "name": store["name"], "address": store["address"],
        "organization": organization.get("name"), "latitude": store["latitude"],
        "longitude": store["longitude"], "distance_km": distance, "status": store["status"],
    }


def product_json(product: dict) -> dict:
    return {
        "product_id": product["_id"], "name": product["name"], "brand": product["brand"],
        "category": product["category"], "package_size": product["package_size"],
        "barcode": product.get("barcode"), "image_url": product.get("image_url"),
    }


@router.get("/health")
def health():
    return {"status": "ok", "generated_at": cmp.iso(utcnow())}


@router.get("/stats")
def stats(db: Database = Depends(get_db)):
    return {
        "retailers": db.organizations.count_documents({}), "stores": db.stores.count_documents({}),
        "products": db.products.count_documents({}), "listings": db.store_products.count_documents({}),
    }


Island = Query(None, pattern="^(Luzon|Visayas|Mindanao)$")


@router.get("/market/summary")
def market_summary(db: Database = Depends(get_db)):
    return market.summary(db)


@router.get("/market/prices", dependencies=[Depends(limit_search)])
def market_prices(
    q: str = Query("", max_length=120),
    source: str | None = Query(None, pattern="^(dti_srp|da_dpi)$"),
    category: str | None = Query(None, max_length=120),
    island: str | None = Island,
    db: Database = Depends(get_db),
):
    rows = market.search(market.price_rows(db, source, island), q)
    if category:
        rows = [r for r in rows if r["category"] == category]
    return {"count": len(rows), "results": rows, "generated_at": cmp.iso(utcnow())}


class BasketItem(BaseModel):
    query: str = Field(min_length=1, max_length=120)
    quantity: int = Field(1, ge=1, le=999)
    price_id: str | None = Field(None, max_length=300)

    @field_validator("query")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class BasketRequest(BaseModel):
    items: list[BasketItem] = Field(min_length=1, max_length=MAX_MULTI_SEARCH_ITEMS)
    island: str | None = Field(None, pattern="^(Luzon|Visayas|Mindanao)$")


@router.post("/market/basket", dependencies=[Depends(limit_search)])
def market_basket(body: BasketRequest, db: Database = Depends(get_db)):
    return market.basket(market.price_rows(db, None, body.island), [i.model_dump() for i in body.items])


@router.get("/location/resolve", dependencies=[Depends(limit_search)])
def resolve_location(
    latitude: float | None = Latitude,
    longitude: float | None = Longitude,
    city: str | None = Query(None, min_length=2, max_length=80),
    db: Database = Depends(get_db),
):
    need_both(latitude, longitude)
    if latitude is None and not city:
        raise HTTPException(422, "Send a location or a city name")
    try:
        return location.resolve(db, latitude, longitude, city)
    except location.LocationError as error:
        raise HTTPException(503, str(error))


@router.get("/categories")
def categories(db: Database = Depends(get_db)):
    return [{"id": c["_id"], "name": c["name"]} for c in db.categories.find().sort("name", 1)]


@router.get("/products/search", dependencies=[Depends(limit_search)])
def search_products(
    q: str = Query("", max_length=120),
    latitude: float | None = Latitude,
    longitude: float | None = Longitude,
    radius_km: float | None = Radius,
    sort_by: str = "price_asc",
    category_id: str | None = None,
    brand: str | None = None,
    package_size: str | None = None,
    max_price: float | None = Query(None, ge=0),
    store_id: str | None = None,
    availability: str | None = None,
    price_status: str | None = None,
    include_stale: bool = False,
    db: Database = Depends(get_db),
):
    need_both(latitude, longitude)
    if sort_by not in cmp.SORTS:
        raise HTTPException(422, f"sort_by must be one of {sorted(cmp.SORTS)}")
    if sort_by == "best_nearby" and radius_km is None:
        radius_km = NEARBY_RADIUS_KM

    offers = cmp.build_offers(db, cmp.find_products(db, q, category_id), latitude, longitude)

    def keep(offer: cmp.Offer) -> bool:
        product = offer.product
        return (
            (brand is None or product["brand"].lower() == brand.lower())
            and (package_size is None or product["package_size"].lower() == package_size.lower())
            and (max_price is None or offer.price <= max_price * 100)
            and (store_id is None or offer.store_id == store_id)
            and (availability is None or offer.listing["availability_status"] == availability)
            and (price_status is None or offer.status == price_status)
        )

    eligible, stale = cmp.split_offers([o for o in offers if keep(o)], radius_km)
    cmp.apply_labels(eligible)
    return {
        "query": q, "currency": "PHP", "sort_by": sort_by,
        "results": [o.json() for o in cmp.sort_offers(eligible, sort_by)],
        "stale_results": [o.json() for o in cmp.sort_offers(stale, "price_asc")] if include_stale else [],
        "stale_hidden": 0 if include_stale else len(stale),
        "generated_at": cmp.iso(utcnow()),
    }


class MultiSearchItem(BaseModel):
    query: str = Field(min_length=1, max_length=120)
    quantity: int = Field(1, ge=1, le=999)
    product_id: str | None = None

    @field_validator("query")
    @classmethod
    def strip(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class MultiSearchRequest(BaseModel):
    items: list[MultiSearchItem] = Field(min_length=1, max_length=MAX_MULTI_SEARCH_ITEMS)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    radius_km: float | None = Field(None, gt=0, le=200)

    @model_validator(mode="after")
    def unique_queries(self):
        keys = [item.query.lower() for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("each item may appear only once; raise its quantity instead")
        return self


@router.post("/products/multi-search", dependencies=[Depends(limit_search)])
def multi_search(body: MultiSearchRequest, db: Database = Depends(get_db)):
    need_both(body.latitude, body.longitude)
    result = cmp.multi_search(
        db, [i.model_dump() for i in body.items], body.latitude, body.longitude, body.radius_km,
    )
    return {**result, "generated_at": cmp.iso(utcnow())}


@router.get("/products/{product_id}")
def get_product(product_id: str, db: Database = Depends(get_db)):
    product = db.products.find_one({"_id": product_id})
    if product is None:
        raise HTTPException(404, "Product not found")
    return product_json(product)


@router.get("/products/{product_id}/prices", dependencies=[Depends(limit_search)])
def product_prices(
    product_id: str,
    latitude: float | None = Latitude,
    longitude: float | None = Longitude,
    radius_km: float | None = Radius,
    sort_by: str = "price_asc",
    db: Database = Depends(get_db),
):
    need_both(latitude, longitude)
    product = db.products.find_one({"_id": product_id})
    if product is None:
        raise HTTPException(404, "Product not found")
    eligible, stale = cmp.split_offers(cmp.build_offers(db, [product], latitude, longitude), radius_km)
    cmp.apply_labels(eligible)
    return {
        "product": product_json(product), "currency": "PHP",
        "results": [o.json() for o in cmp.sort_offers(eligible, sort_by)],
        "stale_results": [o.json() for o in cmp.sort_offers(stale, "price_asc")],
        "generated_at": cmp.iso(utcnow()),
    }


@router.get("/stores/nearby")
def stores_nearby(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_km: float = Query(25, gt=0, le=200),
    db: Database = Depends(get_db),
):
    stores = [store_json(db, s, latitude, longitude) for s in db.stores.find({"status": "active"})]
    return sorted((s for s in stores if s["distance_km"] <= radius_km), key=lambda s: s["distance_km"])


@router.get("/stores/{store_id}")
def get_store(
    store_id: str,
    latitude: float | None = Latitude,
    longitude: float | None = Longitude,
    db: Database = Depends(get_db),
):
    need_both(latitude, longitude)
    store = db.stores.find_one({"_id": store_id})
    if store is None:
        raise HTTPException(404, "Store not found")
    return store_json(db, store, latitude, longitude)


@router.get("/stores/{store_id}/products")
def store_products(store_id: str, db: Database = Depends(get_db)):
    if db.stores.find_one({"_id": store_id}) is None:
        raise HTTPException(404, "Store not found")
    product_ids = db.store_products.distinct("product_id", {"store_id": store_id})
    products = list(db.products.find({"_id": {"$in": product_ids}}))
    offers = [o for o in cmp.build_offers(db, products) if o.store_id == store_id]
    return [o.json() for o in sorted(offers, key=lambda o: o.product["name"])]


class LoginRequest(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str


def user_json(user: dict) -> dict:
    return {
        "id": user["_id"], "email": user["email"], "full_name": user["full_name"],
        "roles": user["roles"],
    }


@router.post("/auth/login", dependencies=[Depends(limit_login)])
def login(body: LoginRequest, db: Database = Depends(get_db)):
    user = db.users.find_one({"email": body.email.strip().lower()})
    if user is None or user["status"] != "active" or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    return {
        "access_token": issue_token(user["_id"], "access"),
        "refresh_token": issue_token(user["_id"], "refresh"),
        "user": user_json(user),
    }


@router.post("/auth/refresh")
def refresh(body: RefreshRequest, db: Database = Depends(get_db)):
    user = db.users.find_one({"_id": read_token(body.refresh_token, "refresh")})
    if user is None or user["status"] != "active":
        raise HTTPException(401, "Invalid or expired token")
    return {"access_token": issue_token(user["_id"], "access")}


@router.get("/users/me")
def me(user: dict = Depends(current_user)):
    return user_json(user)
