"""A small version counter that lets open apps notice new prices without reloading."""
from pymongo.database import Database

from .comparison import iso
from .db import utcnow

KEY = "market"


def bump(db: Database) -> None:
    db.live_state.update_one({"_id": KEY}, {"$inc": {"version": 1}, "$set": {"updated_at": utcnow()}}, upsert=True)


def checked(db: Database) -> None:
    db.live_state.update_one({"_id": KEY}, {"$set": {"checked_at": utcnow()}}, upsert=True)


def state(db: Database) -> dict:
    doc = db.live_state.find_one({"_id": KEY}) or {}
    return {
        "version": doc.get("version", 0),
        "updated_at": iso(doc.get("updated_at")),
        "checked_at": iso(doc.get("checked_at")),
    }
