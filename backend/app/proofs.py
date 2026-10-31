"""Crowdsourced prices with proof: a registered shopper's photo of a receipt or shelf tag.

Each submission is compared with what we already know. It is published when an
administrator approves it, or when two different shoppers agree on the same price at
the same store. Photos may show personal details, so only administrators can see them,
and they are deleted once they are no longer needed.
"""
from datetime import timedelta
from statistics import median

from fastapi import HTTPException
from pymongo.database import Database

from . import comparison as cmp
from . import community, live, market
from .db import new_id, utcnow

MAX_PHOTO_BYTES = 2 * 1024 * 1024
PHOTO_RETENTION_DAYS = 30
AGREEMENT_TOLERANCE = 0.05
CONSISTENT_RANGE = 0.25
TRUSTED_AFTER = 5
MAX_REJECTED_SHARE = 0.2
SIGNATURES = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}


def photo_type(data: bytes) -> str:
    """Trusts the file's contents, never the name or type it claims."""
    for signature, kind in SIGNATURES.items():
        if data.startswith(signature):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise HTTPException(422, "The proof must be a JPEG, PNG or WebP photo")


def compare(db: Database, name: str, store_name: str, city: str, centavos: int) -> dict:
    """Sets the submitted price beside the references we hold."""
    checks = []

    def add(label: str, reference: int) -> None:
        gap = (centavos - reference) / reference * 100
        checks.append({
            "label": label, "price": cmp.money(reference), "difference_pct": round(gap, 1),
            "ok": abs(gap) <= CONSISTENT_RANGE * 100,
        })

    official = market.search_rows(db, market.cached_rows(db, None), name)
    if official:
        add(f'{official[0]["source_label"]}: {official[0]["commodity"]}', round(official[0]["price"] * 100))
    reports = community.matching(community.current(db, city), name)
    same_store = [r for r in reports if r["store_name"] == store_name]
    if same_store:
        add(f"Last price at {store_name}", same_store[0]["price_centavos"])
    others = [r["price_centavos"] for r in reports if r["store_name"] != store_name]
    if others:
        add(f"Typical price in {city} ({len(others)} stores)", round(median(others)))

    if not checks:
        verdict = "no_reference"
    else:
        verdict = "consistent" if all(c["ok"] for c in checks) else "needs_checking"
    return {"verdict": verdict, "checks": checks}


def publish(db: Database, proof: dict, centavos: int, origin: str) -> None:
    db.shelf_reports.insert_one({
        "_id": new_id(), "item_key": proof["item_key"], "item_name": proof["item_name"],
        "store_name": proof["store_name"], "latitude": proof["latitude"], "longitude": proof["longitude"],
        "city": proof["city"], "price_centavos": centavos, "status": "visible", "origin": origin,
        "proof_id": proof["_id"], "created_at": utcnow(),
    })
    live.bump(db)


def impact(db: Database, user_id: str) -> dict:
    """What a shopper's sharing has added, and whether their prices can skip the queue."""
    approved = list(db.proofs.find({"user_id": user_id, "status": "approved"}, {"store_name": 1, "city": 1, "item_key": 1}))
    rejected = db.proofs.count_documents({"user_id": user_id, "status": "rejected"})
    trusted = len(approved) >= TRUSTED_AFTER and rejected <= len(approved) * MAX_REJECTED_SHARE
    return {
        "verified": len(approved), "items": len({p["item_key"] for p in approved}),
        "stores": len({p["store_name"] for p in approved}), "cities": len({p["city"] for p in approved}),
        "pending": db.proofs.count_documents({"user_id": user_id, "status": "pending"}), "rejected": rejected,
        "trusted": trusted, "to_trusted": max(0, TRUSTED_AFTER - len(approved)),
    }


def submit(db: Database, user: dict, name: str, store_name: str, latitude: float, longitude: float,
           city: str, price: float, photo: bytes) -> dict:
    if len(photo) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "The photo must be 2 MB or smaller")
    centavos = round(price * 100)
    doc = {
        "_id": new_id(), "user_id": user["_id"], "item_key": community.item_key(name), "item_name": name.strip(),
        "store_name": store_name.strip(), "latitude": latitude, "longitude": longitude, "city": city.strip(),
        "price_centavos": centavos, "photo": photo, "photo_type": photo_type(photo), "status": "pending",
        "comparison": compare(db, name, store_name.strip(), city.strip(), centavos), "created_at": utcnow(),
    }
    match = db.proofs.find_one({
        "item_key": doc["item_key"], "store_name": doc["store_name"], "user_id": {"$ne": user["_id"]},
        "status": {"$in": ["pending", "approved"]},
        "created_at": {"$gte": utcnow() - timedelta(days=community.MAX_AGE_DAYS)},
        "price_centavos": {"$gte": round(centavos * (1 - AGREEMENT_TOLERANCE)), "$lte": round(centavos * (1 + AGREEMENT_TOLERANCE))},
    })
    if match:
        doc["status"] = "approved"
        doc["decided_by"] = "agreement"
        doc["decided_at"] = utcnow()
    elif impact(db, user["_id"])["trusted"] and doc["comparison"]["verdict"] == "consistent":
        doc["status"] = "approved"  # Anything unusual still goes to a person.
        doc["decided_by"] = "trusted shopper"
        doc["decided_at"] = utcnow()
    db.proofs.insert_one(doc)
    if doc.get("decided_by") == "trusted shopper":
        publish(db, doc, centavos, "Verified trusted shopper")
    if match:
        if match["status"] == "pending":
            db.proofs.update_one({"_id": match["_id"]}, {"$set": {"status": "approved", "decided_by": "agreement", "decided_at": utcnow()}})
        publish(db, doc, centavos, "Verified by 2 shoppers")
    return doc


def _pending(db: Database, proof_id: str) -> dict:
    proof = db.proofs.find_one({"_id": proof_id}, {"photo": 0})
    if proof is None:
        raise HTTPException(404, "Proof not found")
    if proof["status"] != "pending":
        raise HTTPException(409, "This proof was already decided")
    return proof


def approve(db: Database, proof_id: str, admin: dict, price: float | None) -> dict:
    proof = _pending(db, proof_id)
    centavos = round(price * 100) if price is not None else proof["price_centavos"]
    db.proofs.update_one({"_id": proof_id}, {"$set": {
        "status": "approved", "price_centavos": centavos, "decided_by": admin["email"], "decided_at": utcnow(),
    }})
    publish(db, proof, centavos, "Verified with proof")
    return {**proof, "status": "approved", "price_centavos": centavos}


def reject(db: Database, proof_id: str, admin: dict, reason: str) -> dict:
    proof = _pending(db, proof_id)
    db.proofs.update_one({"_id": proof_id}, {"$set": {
        "status": "rejected", "reason": reason, "decided_by": admin["email"], "decided_at": utcnow(), "photo": None,
    }})
    return {**proof, "status": "rejected", "reason": reason}


def purge_photos(db: Database) -> int:
    """Removes photos from decided proofs after the review window."""
    cutoff = utcnow() - timedelta(days=PHOTO_RETENTION_DAYS)
    result = db.proofs.update_many(
        {"status": {"$ne": "pending"}, "decided_at": {"$lt": cutoff}, "photo": {"$ne": None}}, {"$set": {"photo": None}},
    )
    return result.modified_count


def proof_json(db: Database, proof: dict, *, for_admin: bool) -> dict:
    data = {
        "id": proof["_id"], "item_name": proof["item_name"], "store_name": proof["store_name"], "city": proof["city"],
        "price": cmp.money(proof["price_centavos"]), "status": proof["status"], "reason": proof.get("reason"),
        "created_at": cmp.iso(proof["created_at"]),
    }
    if for_admin:
        history = {s: db.proofs.count_documents({"user_id": proof["user_id"], "status": s}) for s in ("approved", "rejected")}
        data.update(comparison=proof["comparison"], submitter=history, has_photo=bool(db.proofs.find_one(
            {"_id": proof["_id"], "photo": {"$ne": None}}, {"_id": 1})))
    return data
